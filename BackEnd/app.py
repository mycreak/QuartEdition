# app.py
# 核心作用：项目**主应用入口文件**
# 负责：创建Web服务、启动前初始化所有资源、关闭时释放所有资源、编排后台任务
import os
import sys
import logging
import asyncio   # Python异步协程核心库，用于任务队列/后台任务

# 确保工作目录为 app.py 所在目录，使 .env / logs/ 等相对路径正确
os.chdir(os.path.dirname(os.path.abspath(__file__)))
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Flask 3.1+ 新增了 PROVIDE_AUTOMATIC_OPTIONS 配置键检查，
# Quart 0.19.x 未跟随更新，通过 patch add_url_rule 注入默认值。
# ⚠️ 此 patch 依赖 Flask/Quart 内部实现，升级时需验证兼容性：
#   - Flask 2.x/3.x: hasattr(config, "PROVIDE_AUTOMATIC_OPTIONS") 可用
#   - Quart 0.19.x: 当前已验证
import flask.sansio.app as _flask_app
_original_add_url_rule = _flask_app.App.add_url_rule

def _patched_add_url_rule(self, rule, endpoint=None, view_func=None, **options):
    self.config.setdefault("PROVIDE_AUTOMATIC_OPTIONS", True)
    return _original_add_url_rule(self, rule, endpoint, view_func, **options)

_flask_app.App.add_url_rule = _patched_add_url_rule

from quart import Quart, g, request  # 异步Web框架（类似FastAPI/Flask，支持高并发异步）
# 导入三大数据库 初始化/关闭 方法（连接池管理）
from db import init_mysql, close_mysql, init_redis, close_redis, init_mongodb, close_mongodb
# 导入统一数据库中间层：封装MySQL/MongoDB/Redis，业务层统一调用
from db.database_v2 import DatabaseLayerV2
# 导入后台任务模块：Puller拉取延迟任务、Worker执行任务、Monitor服务监控
from background.puller import init_puller, start_puller, stop_puller
from background.worker import init_browser_pool, start_browser_pool, stop_browser_pool
from background.monitor import init_monitor, start_monitor, stop_monitor
# 导入爬虫入口模块：接收任务，编排 fetch → parse → store
from crawler import init_crawler
from crawler import execute as crawler_execute
from services.movie_service import MovieService
from services.app_services import AppServices
# 导入 Playwright：管理 Chromium 浏览器生命周期
from playwright.async_api import async_playwright
# 导入雪花算法：生成分布式唯一ID（用户ID/订单ID/任务ID）
from utils.snowflake import init_snowflake
# 导入 WebSocket 管理器和路由
from utils.websocket import init_ws_manager
from routes.websocket import register_websocket_routes
from routes.admin import admin_bp, init_task_failure_service
from routes.admin.poster_routes import poster_bp
from routes.public import auth_bp
from routes.user import user_bp
from services.auth_service import init_auth_service
from services.review_service import init_review_service
from services.task_history_service import init_task_history_service
# 导入 OpenAPI 文档自动生成（quart-schema）
from quart_schema import QuartSchema
from config.openapi import DOC_INFO, DOC_TAGS
# 导入 CORS 中间件（quart-cors）
from quart_cors import cors
# 导入结构化 JSON 日志
from utils.logging_config import setup_json_logging


def create_app():
    """
    应用工厂函数
    作用：标准化创建Quart应用实例，统一管理服务生命周期
    优点：支持多环境部署、方便测试、解耦实例创建与配置
    """
    app = Quart(__name__)

    # ── CORS 跨域（生产环境应改为前端具体域名 + supports_credentials=True） ──
    app = cors(app, allow_origin="*")

    # ── HTTP 访问日志（记录到 routes.access logger → access.log） ──
    _access_logger = logging.getLogger("routes.access")
    _SENSITIVE_KEYS = frozenset({"password", "password_hash", "token", "secret"})

    def _sanitize_body(raw: bytes) -> str:
        """从原始请求体中提取可读文本，对敏感字段递归脱敏（最大深度 3）。"""
        import json as _json
        try:
            data = _json.loads(raw)
        except (_json.JSONDecodeError, UnicodeDecodeError, TypeError):
            text = raw.decode("utf-8", errors="replace")
            return text[:200] if len(text) > 200 else text

        def _mask(obj, depth: int = 0):
            if depth > 3:
                return "[嵌套过深,已截断]"
            if isinstance(obj, dict):
                result = {}
                for k, v in obj.items():
                    if any(s in str(k).lower() for s in _SENSITIVE_KEYS):
                        result[k] = "***"
                    elif isinstance(v, (dict, list)):
                        result[k] = _mask(v, depth + 1)
                    elif isinstance(v, str) and len(v) > 100:
                        result[k] = v[:100] + "..."
                    else:
                        result[k] = v
                return result
            if isinstance(obj, list):
                if len(obj) > 20:
                    return [_mask(obj[0], depth + 1), f"...({len(obj) - 1} more)"]
                return [_mask(v, depth + 1) for v in obj]
            if isinstance(obj, str) and len(obj) > 200:
                return obj[:200] + "..."
            return obj

        masked = _mask(data)
        return _json.dumps(masked, ensure_ascii=False)

    @app.before_request
    async def _capture_request_info():
        from quart import request as _req
        g._start_time = asyncio.get_event_loop().time()
        g._method = _req.method
        g._path = _req.path
        g._query = _req.query_string.decode("utf-8") if _req.query_string else None
        g._remote_addr = _req.remote_addr or "-"
        # 延迟读取 body — 仅在 4xx/5xx 时读取（after_request 中按需获取）

    @app.after_request
    async def _log_access(response):
        start = getattr(g, "_start_time", 0)
        duration = round((asyncio.get_event_loop().time() - start) * 1000, 1)
        method = getattr(g, "_method", request.method)
        path = getattr(g, "_path", request.path)
        remote = getattr(g, "_remote_addr", request.remote_addr or "-")

        if response.status_code >= 400:
            detail_parts = [f"query={getattr(g, '_query', '') or '-'}"]
            raw_body = await request.get_data()
            if raw_body:
                detail_parts.append(f"body={_sanitize_body(raw_body)}")
            log_fn = _access_logger.error if 500 <= response.status_code < 600 else _access_logger.info
            log_fn(
                "%s %s → %s | %sms | IP=%s | %s",
                method, path, response.status_code, duration, remote,
                " ".join(detail_parts),
            )
        else:
            _access_logger.info(
                "%s %s → %s | %sms | IP=%s",
                method, path, response.status_code, duration, remote,
            )
        return response

    # ── 提前注册蓝图（使 quart-schema 能扫描到所有路由） ──
    # 在 QuartSchema() 之前注册，确保 OpenAPI 文档能捕获所有端点
    # 蓝图注册不需要数据库就绪，纯 URL 映射
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(poster_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(user_bp, url_prefix="/user")

    # ==================== 0. 注册 OpenAPI 文档自动生成 ====================
    # quart-schema 自动解析路由和 Pydantic 模型，生成 OpenAPI 3.0 规范
    # 访问 /openapi.json 查看原始规范，/docs 查看 Swagger UI，/redocs 查看 ReDoc
    # WebSocket 路由（/ws/notifications）会自动排除（OpenAPI 不支持 WebSocket 标准）
    QuartSchema(app, info=DOC_INFO, tags=DOC_TAGS)

    # ==================== 0b. 启用结构化 JSON 日志 ====================
    # 所有业务模块的 logger.info/error/warning 输出单行 JSON
    # 切回文本格式：设置环境变量 LOG_FORMAT=txt
    setup_json_logging()

    @app.before_serving
    async def startup():
        """
        服务启动前置钩子
        执行时机：Web服务接收请求前，一次性初始化所有核心资源
        作用：避免运行中重复创建连接/实例，保证服务启动即就绪
        """
        logger = logging.getLogger(__name__)
        # ==================== 1. 初始化数据库连接池 ====================
        await init_mysql()
        await init_redis()
        await init_mongodb()

        # ==================== 2. 创建全局异步任务队列 ====================
        app.task_queue = asyncio.Queue(maxsize=45)

        # ==================== 3. 初始化雪花算法ID生成器 ====================
        from config.settings import settings
        if not settings.JWT_SECRET:
            raise RuntimeError(
                "JWT_SECRET 未设置！请在 .env 文件中添加:\n"
                "  JWT_SECRET=<your-random-secret-string>"
            )
        init_snowflake(machine_id=settings.SNOWFLAKE_MACHINE_ID)

        # ==================== 4. 初始化统一数据库中间层 ====================
        db = DatabaseLayerV2()
        await db.initialize("mysql")

        # ==================== 4b. 初始化类型化服务容器 ====================
        movie_service = MovieService(db)
        app.services = AppServices(db=db, movie_service=movie_service)

        # ==================== 5. 初始化并启动延迟任务拉取器(Puller) ====================
        await init_puller(task_queue=app.task_queue, db_layer=app.services.db)
        app.add_background_task(start_puller)

        # ==================== 5a. 初始化 TOS 图床客户端 ====================
        from utils.tos_client import init_tos_client
        init_tos_client()

        # ==================== 5a2. 注入付费代理种子（从 .env PAID_PROXIES 加载） ====================
        from config.settings import settings
        from crawler.proxy import init_proxy_pool, SourceType
        proxy_pool = init_proxy_pool()
        await proxy_pool.load_persisted()

        paid_proxies = settings.PAID_PROXIES
        if not paid_proxies:
            # 兼容旧格式: PAID_PROXY_HOST=ip PAID_PROXY_PORT=port ...
            old_host = getattr(settings, 'PAID_PROXY_HOST', '')
            if old_host:
                old_port = getattr(settings, 'PAID_PROXY_PORT', 0)
                old_user = getattr(settings, 'PAID_PROXY_USER', '')
                old_pass = getattr(settings, 'PAID_PROXY_PASS', '')
                paid_proxies = f"{old_host}:{old_port}:{old_user}:{old_pass}"

        for entry in paid_proxies.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            host = parts[0].strip()
            port = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else 0
            user = parts[2].strip() if len(parts) > 2 else ""
            passwd = parts[3].strip() if len(parts) > 3 else ""
            if host and port:
                ok = await proxy_pool.add_proxy(
                    host=host, port=port,
                    username=user, password=passwd,
                    source=SourceType.ADMIN,
                    remark=host,
                    prefer=True,
                )
                if ok:
                    logger.info(f"付费代理已注入: {host}:{port}")
                else:
                    logger.warning(f"付费代理注入失败（可能已在池中）: {host}:{port}")

        # ==================== 5b. 初始化 CookieManager（多账号管理） ====================
        from crawler.cookie_manager import init_cookie_manager as _init_cm
        await _init_cm()

        # ==================== 6. 启动 Chromium 浏览器并初始化 Crawler ====================
        # Playwright 生命周期：start → launch → (运行中) → close → stop
        # 启动失败时 try/finally 保证之前已初始化的连接池不受影响
        app.playwright = await async_playwright().start()
        try:
            app.browser = await app.playwright.chromium.launch(headless=True)
        except Exception:
            await app.playwright.stop()
            raise
        app.worker_event_queue = asyncio.Queue(maxsize=1000)
        init_crawler(
            app.browser,
            movie_service=app.services.movie_service,
            playwright=app.playwright,
            event_queue=app.worker_event_queue,
        )

        # ==================== 7. 初始化并启动 BrowserPool ====================
        # 固定 5 个 Worker 协程（默认值），共享 1 个浏览器实例
        await init_browser_pool(
            task_queue=app.task_queue,
            execute_func=crawler_execute,
            event_queue=app.worker_event_queue,
        )
        app.add_background_task(start_browser_pool)

        # ==================== 8. 初始化 WebSocket 管理器 ====================
        app.ws_manager = init_ws_manager()
        register_websocket_routes(app, app.ws_manager)

        # ==================== 8b. 初始化失败任务管理服务 + 评论管理服务 ====================
        init_task_failure_service(app.services.db)
        init_task_history_service(app.services.db)
        init_review_service(app.services.db)

        # ==================== 8c. 初始化认证服务 ====================
        init_auth_service(app.services.db)

        # ==================== 9. 初始化并启动系统状态监视器(Monitor) ====================
        await init_monitor(
            task_queue=app.task_queue,
            worker_event_queue=app.worker_event_queue,
            db_layer=app.services.db,
            ws_manager=app.ws_manager,
        )
        app.add_background_task(start_monitor)

    @app.after_serving
    async def shutdown():
        """
        服务关闭后置钩子
        执行时机：Web服务停止后，释放所有资源
        作用：防止数据库连接泄漏、浏览器进程残留、任务丢失

        关闭顺序（严格）：
            1. 停止 Puller — 禁止新任务流入 asyncio.Queue
            2. 停止 BrowserPool — 等待 in-flight 任务完成（超时 30s）
            3. Drain 任务队列 — 将 Queue 中剩余任务写回 Redis ZSET
            4. 停止 Monitor
            5. 释放浏览器 / 数据库连接池
        """
        import time as _time

        # ── 1. 停止 Puller（禁止新任务进入队列） ──
        logger = logging.getLogger(__name__)
        logger.info("开始优雅关闭: 1/6 停止 Puller")
        await stop_puller()

        # ── 2. 停止 BrowserPool（取消所有 Worker，超时 30s） ──
        logger.info("开始优雅关闭: 2/6 停止 BrowserPool（等待 in-flight 任务）")
        await stop_browser_pool()

        # ── 3. Drain 任务队列：剩余任务写回 Redis ZSET ──
        logger.info(f"开始优雅关闭: 3/6 Drain 任务队列（当前队列剩余: {app.task_queue.qsize()}）")
        drained_count = 0
        while not app.task_queue.empty():
            try:
                task = app.task_queue.get_nowait()
                # 原始执行时间已不可知，用当前时间 + 5s 作为延迟时间
                # 避免服务重启后 Puller 立即拉取导致重复执行
                execute_at = _time.time() + 5
                await app.services.db.add_delayed_task(
                    task_json=task,
                    execute_at=execute_at,
                )
                drained_count += 1
            except Exception as e:
                logger.error(f"Drain 任务失败（丢弃）: {e}")
        logger.info(
            f"任务队列 Drain 完成: {drained_count} 个任务已写回 Redis ZSET"
        )

        # ── 4. 停止 Monitor ──
        logger.info("开始优雅关闭: 4/6 停止 Monitor")
        await stop_monitor()

        # ── 5. 关闭浏览器（先关页面，再关进程） ──
        logger.info("开始优雅关闭: 5/6 关闭浏览器")
        try:
            await app.browser.close()
        except Exception:
            pass  # 浏览器进程可能已退出（被 Worker cancel 触发），忽略
        try:
            await app.playwright.stop()
        except Exception:
            pass  # Playwright 进程可能已退出，忽略；不能因为 stop 失败跳过 DB 关闭

        # ── 6. 优雅关闭三大数据库连接池（并行关闭） ──
        logger.info("开始优雅关闭: 6/6 关闭数据库连接池")
        await asyncio.gather(
            close_mysql(),
            close_redis(),
            close_mongodb(),
        )
        logger.info("优雅关闭完成")

    return app


# 模块级 app 实例：供 hypercorn app:app 直接引用
# ⚠️ 此实例在 import 阶段创建，会触发 QuartSchema / CORS / 日志初始化。
# pytest 收集阶段会导入此模块，但不会启动服务，不影响测试。
app = create_app()


if __name__ == "__main__":
    """直接 python app.py 启动（调试用）。"""
    import hypercorn.asyncio
    import hypercorn.config as hc_config

    config = hc_config.Config()
    from config.settings import settings
    config.bind = [settings.BIND or "0.0.0.0:8000"]
    config.use_reloader = False
    asyncio.run(hypercorn.asyncio.serve(app, config))
