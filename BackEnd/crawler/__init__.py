"""
crawler/__init__.py

爬虫入口模块 — 接收任务 JSON 字符串，编排 fetch → parse → store 全流程。

职责：
    1. 解析任务 JSON，按 task.type 分发到对应处理函数
    2. movie_crawl         → ApiFetcher → 榜单 douban_id → ZADD 子任务
    3. movie_detail_crawl  → BrowserFetcher → 详情页+参演人员 → MySQL（单部独立入库）
    4. review_crawl        → BrowserFetcher → 摘要列表 → movie_review 待爬表
    5. review_body_crawl   → ApiFetcher → 正文 → MongoDB reviews
    6. comment_crawl       → BrowserFetcher → parser → MongoDB comments
    7. director_crawl      → BrowserFetcher → parser → MySQL (存量补录)

架构变更（v2 — 类封装）：
    旧: init_crawler() → 模块级全局变量 _api_fetcher / _browser_fetcher / _movie_service
    新: CrawlerEngine 实例管理所有状态，通过依赖注入构造函数传入
    测试: 直接创建 CrawlerEngine(mock_fetcher, mock_service)，无需 patch 模块全局变量

对外接口：
    execute(task: str) → None           ← 兼容旧版，委托给 CrawlerEngine 单例
    init_crawler(browser, ...)          ← 工厂函数，创建 CrawlerEngine 单例
    get_crawler() → CrawlerEngine       ← 获取单例，未初始化抛 RuntimeError
    CrawlerEngine                       ← 可直接实例化（测试用）

签名约定（核心约束）：
    CrawlerEngine.execute(task) 签名必须为 async (task: str) → None
    成功不返回值，失败抛异常（异常由 BrowserPool 捕获并上报 event_queue）
"""

import asyncio
import json
import logging
import os
import random
import time
from typing import Optional

from crawler.fetcher import ApiFetcher, BrowserFetcher, FetcherError
from crawler.parser import parse_movie_list, parse_movie_detail, parse_review_list, parse_review_full, parse_comments, parse_personnel
from crawler.storage import save_movies, save_reviews, save_comments, save_movie_basic, save_crew
import crawler.storage as storage
from crawler.proxy import get_proxy_pool
from config.crawler_config import crawler_config

# P0 — Identity 管理（向后兼容，旧代码不依赖）
try:
    from crawler.identity import IdentityManager
    from crawler.cookie_manager import get_cookie_manager
except ImportError:
    IdentityManager = None  # type: ignore
    get_cookie_manager = None  # type: ignore

logger = logging.getLogger(__name__)

REVIEW_DETAIL_URL = "https://movie.douban.com/review/{review_id}/"
REVIEW_FULL_API = "https://movie.douban.com/j/review/{review_id}/full"
REVIEW_LIST_BASE = "https://movie.douban.com/subject/{douban_id}/reviews"
COMMENT_LIST_BASE = "https://movie.douban.com/subject/{douban_id}/comments"
SUBJECT_PAGE_BASE = "https://movie.douban.com/subject/{douban_id}/"



# ═══════════════════════════════════════════════════════════════
# 辅助函数（无状态，纯逻辑）
# ═══════════════════════════════════════════════════════════════


def classify_item_error(exc: Exception) -> str:
    """为 item 级失败做快速错误分类。"""
    exc_name = type(exc).__name__
    msg = str(exc).lower()

    if isinstance(exc, FetcherError):
        return "timeout" if "timeout" in msg else "network"
    if exc_name in ("PlaywrightTimeoutError", "TimeoutError"):
        return "timeout"
    if exc_name in ("ValueError", "ValidationError"):
        return "validation"
    if "abuse" in msg or "检测到有异常请求" in msg:
        return "abuse"
    if any(kw in msg for kw in ("connection", "resolve", "refused")):
        return "network"
    return "unknown"


async def _trigger_similarity_check(tag_id: int, dimension: str) -> None:
    """
    模块级辅助函数：异步触发风格标签相似度检测。

    由 _handle_ai_review_summary / _handle_ai_wordcloud 在插入新标签后
    通过 asyncio.create_task 调用，fire-and-forget，不阻塞主流程。

    输入：tag_id, dimension
    副作用：更新 movie_style_tag.review_status / merged_to_tag_id
    异常：内部捕获，不向外抛出
    """
    try:
        from services.style_tag_service import _get_style_tag_service
        svc = _get_style_tag_service()
        await svc.check_similarity(tag_id, dimension)
    except Exception:
        logger.exception(
            f"[风格标签检测] tag_id={tag_id} dimension={dimension} 异常"
        )


# ═══════════════════════════════════════════════════════════════
# CrawlerEngine — 爬虫引擎（类封装，依赖注入）
# ═══════════════════════════════════════════════════════════════

class CrawlerEngine:
    """
    爬虫执行引擎。

    管理双引擎（ApiFetcher + BrowserFetcher）和并发控制（Semaphore），
    对外暴露 execute(task) 供 Worker 回调。

    依赖通过构造函数注入，测试可直接传入 mock fetcher，无需 patch 模块变量。
    """

    def __init__(
        self,
        browser,
        movie_service=None,
        playwright=None,
        identity_manager=None,
        event_queue=None,
    ):
        try:
            proxy_pool = get_proxy_pool()
        except RuntimeError:
            proxy_pool = None

        self._api = ApiFetcher(proxy_pool=proxy_pool)
        self._browser = BrowserFetcher(
            browser=browser,
            playwright=playwright,
            proxy_pool=proxy_pool,
        )
        self._movie_service = movie_service
        self._identity_manager = identity_manager
        self._event_queue = event_queue
        self._api_sem = asyncio.Semaphore(crawler_config.api_concurrency)
        self._browser_sem = asyncio.Semaphore(crawler_config.browser_concurrency)
        logger.info("CrawlerEngine 双引擎已初始化 (ApiFetcher + BrowserFetcher)")

    # ── 公开接口 ──

    async def execute(self, task: str) -> None:
        """
        执行爬虫任务 — Worker / BrowserPool 的回调注入函数。

        输入：task: 任务 JSON 字符串
        异常：RuntimeError / ValueError / NotImplementedError / FetcherError
        """
        try:
            data = json.loads(task)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"任务 JSON 解析失败: {e}") from e

        task_type = data.get("type")
        if not task_type:
            raise ValueError("任务 JSON 缺少 type 字段")

        # 身份绑定校验 — 管理员是否有权限使用该 Cookie
        cookie_id = (data.get("cookie_id") or "").strip()
        admin_id = data.get("admin_id")
        if cookie_id and admin_id and self._identity_manager is not None:
            await self._identity_manager.check_binding(admin_id, cookie_id)

        if task_type == "movie_crawl":
            await self._handle_movie_crawl(data)
        elif task_type == "movie_scrape_task":
            await self._handle_movie_scrape_task(data)
        elif task_type == "movie_detail_crawl":
            await self._handle_movie_detail_crawl(data)
        elif task_type == "review_crawl":
            await self._handle_review_crawl(data)
        elif task_type == "review_body_crawl":
            await self._handle_review_body_crawl(data)
        elif task_type == "comment_crawl":
            await self._handle_comment_crawl(data)
        elif task_type == "director_crawl":
            await self._handle_director_crawl(data)
        elif task_type == "ai_review_summary":
            await self._handle_ai_review_summary(data)
        elif task_type == "ai_wordcloud":
            await self._handle_ai_wordcloud(data)
        else:
            raise NotImplementedError(f"未知任务类型: {task_type}")

    async def _browser_fetch(self, url: str) -> str:
        """
        信号量保护的 BrowserFetcher.fetch() — 并发上限由 browser_concurrency 控制。
        """
        async with self._browser_sem:
            return await self._browser.fetch(url)

    async def _browser_fetch_page(self, url: str, identity=None):
        """
        信号量保护的 BrowserFetcher.fetch_page() — 并发上限由 browser_concurrency 控制。
        """
        async with self._browser_sem:
            return await self._browser.fetch_page(url, identity)

    async def _emit_stage(self, task_str: str, stage: str, worker_id: int = -1):
        """
        发送进度事件给 Monitor — Crawler 内部阶段上报。

        输入：task_str（原始任务 JSON 字符串）, stage（人类可读的阶段描述）
        副作用：event_queue.put(WorkerEvent(STAGE_CHANGE))
        """
        if not self._event_queue:
            return
        from crawler.failure_service import WorkerEvent, EventType
        event = WorkerEvent(
            event_type=EventType.STAGE_CHANGE,
            worker_id=worker_id,
            task=task_str,
            timestamp=time.time(),
            stage=stage,
        )
        await self._event_queue.put(event.model_dump())

    async def verify_douban_storage(self) -> bool:
        """启动后异步验证登录态是否有效（使用 CookieManager 中 active 账号的 Cookie）。输出 True/False。"""
        try:
            result = await self._api.fetch("https://www.douban.com/mine")
        except Exception:
            logger.warning("豆瓣登录态验证失败: 网络不可达，Cookie 状态未知")
            return False

        if isinstance(result, str) and "login" in result[:200]:
            logger.warning(
                "豆瓣登录态已过期！爬虫将以游客模式运行。\n"
                "  请通过管理面板「基础设施→Cookie管理」添加新的有效 Cookie"
            )
            return False

        logger.info("豆瓣登录态验证通过 ✅")
        return True

    # ── 内部：各类型任务处理 ──

    async def _handle_movie_crawl(self, data: dict) -> None:
        """
        电影 ID 补充任务。

        ① 确保 crawl_progress 占位行存在
        ② 无 douban_total 缓存 → 请求 count API，写入 douban_total
        ③ 按 ids_fetched 计算 start 偏移（不再 COUNT douban_ids，避免手动添加的 ID 干扰分页）
        ④ 请求 top_list API 获取 ID 列表
        ⑤ 原子事务: INSERT IGNORE douban_ids + UPDATE ids_fetched
            两者在同一事务中提交/回滚，保证断点续爬的 start 偏移与实际榜单分页一致
            失败: 事务自动回滚 → ids_fetched 不变 → 下次重试从同一 start 开始
        """
        type_num = data["type_num"]
        interval_id = data["interval_id"]
        task_id = data.get("id")

        logger.info(f"[movie_crawl] task={task_id} type={type_num} interval={interval_id}")

        task_str = json.dumps(data, ensure_ascii=False)

        if self._movie_service is None:
            raise RuntimeError("MovieService 未注入，无法访问数据库")

        db = self._movie_service.db
        raw = db.raw_mysql()

        # ① 确保 crawl_progress 行存在（无论任务成功与否）
        await raw.execute_update(
            "INSERT IGNORE INTO crawl_progress (type_num, interval_id) VALUES (%s, %s)",
            (type_num, interval_id),
        )
        from config.movie_type import TYPE_MAP
        type_name = TYPE_MAP.get(type_num, "")
        if type_name:
            await raw.execute_update(
                "UPDATE crawl_progress SET type_name=%s "
                "WHERE type_num=%s AND interval_id=%s AND (type_name='' OR type_name IS NULL)",
                (type_name, type_num, interval_id),
            )

        # ② 判断是否已缓存豆瓣总量
        progress_rows = await raw.execute_query(
            "SELECT douban_total FROM crawl_progress WHERE type_num=%s AND interval_id=%s",
            (type_num, interval_id),
        )
        douban_total = progress_rows[0].get("douban_total", 0) if progress_rows else 0

        if not douban_total:
            await self._emit_stage(task_str, "📡 正在获取豆瓣榜单总量...")
            count_url = (
                "https://movie.douban.com/j/chart/top_list_count"
                f"?type={type_num}&interval_id={interval_id}&action="
            )
            count_result = await self._api.fetch(count_url)
            douban_total = count_result.get("total", 0) if isinstance(count_result, dict) else 0
            if douban_total:
                await raw.execute_update(
                    "UPDATE crawl_progress SET douban_total=%s WHERE type_num=%s AND interval_id=%s",
                    (douban_total, type_num, interval_id),
                )
                logger.info(f"[movie_crawl] total={douban_total} 已写入 crawl_progress")

        # ③ 按 ids_fetched 计算 start 偏移（不再 COUNT douban_ids，避免手动添加的 ID 干扰分页）
        progress_rows = await raw.execute_query(
            "SELECT ids_fetched FROM crawl_progress WHERE type_num=%s AND interval_id=%s",
            (type_num, interval_id),
        )
        start = progress_rows[0].get("ids_fetched", 0) if progress_rows else 0

        # ③ 请求 top_list（动态拼接 start）
        list_url = (
            "https://movie.douban.com/j/chart/top_list"
            f"?type={type_num}&interval_id={interval_id}&start={start}&limit=20"
        )
        await self._emit_stage(task_str, "📡 正在获取电影 ID 列表...")
        result = await self._api.fetch(list_url)
        if not isinstance(result, list):
            _dump_data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
            os.makedirs(_dump_data_dir, exist_ok=True)
            _dump_path = os.path.join(
                _dump_data_dir,
                f"movie_crawl_fail_t{type_num}_i{interval_id}_{int(time.time())}.txt"
            )
            with open(_dump_path, "w", encoding="utf-8") as _f:
                _f.write(result if isinstance(result, str) else repr(result))
            logger.error(
                f"[movie_crawl] API 返回非列表类型: {type(result).__name__}, "
                f"已保存至 {_dump_path}"
            )
            raise ValueError(
                f"电影 API 返回非列表类型: {type(result).__name__}, 已保存至 {_dump_path}"
            )

        id_list = parse_movie_list(result)
        logger.info(f"[movie_crawl] task={task_id} 榜单返回 {len(id_list)} 条")

        # ④ 原子事务: INSERT IGNORE douban_ids + 推进 ids_fetched
        #    两者在同一事务中提交/回滚，保证断点续爬的 start 偏移正确
        #    即使多次提交同类型-区间的 movie_crawl，ids_fetched 也始终与实际 API 分页一致
        written = 0
        await self._emit_stage(task_str, "💾 正在写入电影 ID 到数据库...")
        try:
            async with db.transaction() as tx:
                for item in id_list:
                    douban_id = item.get("douban_id", "")
                    title = item.get("title", "")
                    if not douban_id:
                        continue
                    await tx.execute_raw(
                        "INSERT IGNORE INTO douban_ids (douban_id, title, source, type_num, interval_id) "
                        "VALUES (%s, %s, 'dashboard_api', %s, %s)",
                        (douban_id, title, type_num, interval_id),
                    )
                    written += 1

                # 捆绑推进 ids_fetched（与 douban_ids 写入在同一事务中）
                if written > 0:
                    await tx.execute_raw(
                        "UPDATE crawl_progress SET ids_fetched = ids_fetched + %s "
                        "WHERE type_num = %s AND interval_id = %s",
                        (written, type_num, interval_id),
                    )
        except Exception as e:
            logger.error(
                f"[movie_crawl] task={task_id} 事务写入失败: {e}, "
                f"type={type_num} interval={interval_id} written={written}"
            )
            raise

        actual = start + written

        logger.info(
            f"[movie_crawl] task={task_id} type={type_num} interval={interval_id} "
            f"total={douban_total} written={written} progress={actual}/{douban_total}"
        )

    async def _handle_movie_scrape_task(self, data: dict) -> None:
        """
        单部电影爬取任务（P1 新增）。

        管理员显式指定 cookie_id + proxy_key → 身份构造
        → BrowserFetcher 爬详情页 + celebrities 页 → save_movies → MySQL

        输入：
            douban_id, title, cookie_id, proxy_key
        异常：
            ValueError — 身份解析失败
            FetcherError — 3 次重试全失败
        """
        douban_id = data["douban_id"]
        title = data.get("title") or data.get("movie_title", "")
        cookie_id = data.get("cookie_id", "")
        proxy_key = data.get("proxy_key", "")
        task_id = data.get("id")

        logger.info(
            f"[电影详情爬取] task={task_id} douban_id={douban_id} "
            f"title='{title}' cookie={cookie_id or '游客'} proxy={proxy_key or '直连'}"
        )

        if self._movie_service is None:
            raise RuntimeError("MovieService 未注入，无法写入数据库")

        task_str = json.dumps(data, ensure_ascii=False)

        # ① 构建身份
        await self._emit_stage(task_str, f"🔍 正在解析身份: cookie={cookie_id or '游客'} proxy={proxy_key or '直连'}")
        identity = None
        if self._identity_manager is not None and (cookie_id or proxy_key):
            identity = await self._identity_manager.resolve(cookie_id, proxy_key)
        await self._emit_stage(task_str, f"✅ 身份就绪: cookie={cookie_id or '游客'} proxy={proxy_key or '直连'}")

        # ② 爬详情页（最多 2 次重试，间隔 120s~250s 随机）
        detail_url = SUBJECT_PAGE_BASE.format(douban_id=douban_id)
        html = ""
        max_attempts = 2
        for attempt in range(max_attempts):
            await self._emit_stage(task_str, f"📡 正在请求详情页 (第{attempt+1}次): {detail_url}")
            html, ok, snapshot = await self._browser_fetch_page(detail_url, identity)
            if ok:
                await self._emit_stage(task_str, f"✅ 详情页获取成功")
                break
            logger.debug(f"[电影详情爬取] task={task_id} 详情页 attempt={attempt+1} 失败: {snapshot.get('error')}")
            if attempt < max_attempts - 1:
                delay = random.randint(120, 250)
                logger.info(
                    f"[电影详情爬取] task={task_id} 详情页第{attempt+1}次失败，"
                    f"等待 %ss 后重试第{attempt+2}次", delay,
                )
                await self._emit_stage(task_str, f"⏳ 详情页请求失败，{delay}s后重试...")
                await asyncio.sleep(delay)
        else:
            raise FetcherError(f"详情页 {max_attempts} 次重试全失败: douban_id={douban_id}")

        await self._emit_stage(task_str, "📝 正在解析电影详情...")
        detail = parse_movie_detail(html)
        detail["douban_id"] = douban_id

        # 封面提取失败 → 保存 HTML 用于诊断
        if not detail.get("poster_url"):
            _pd = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
            os.makedirs(_pd, exist_ok=True)
            _pp = os.path.join(_pd, f"movie_scrape_noposter_{douban_id}_{int(time.time())}.html")
            with open(_pp, "w", encoding="utf-8") as _f:
                _f.write(html)
            logger.warning(
                f"[movie_scrape] douban_id={douban_id} poster_url 为空, "
                f"HTML 已保存至 {_pp}"
            )

        # ③ 写入电影基础信息（原子事务：movies + genres + regions + ratings）
        await self._emit_stage(task_str, "💾 正在写入电影基础信息...")
        movie_id = await storage.save_movie_basic(self._movie_service, detail)
        if not movie_id:
            # 诊断：收集现场信息写入异常消息
            parsed_title = detail.get("title", "")
            parsed_types = detail.get("types", [])
            parsed_score = detail.get("score", 0)
            existing_check = await self._movie_service.get_movie_by_douban_id(douban_id)
            html_preview = html[:500] if html else ""
            raise ValueError(
                f"电影基础信息写入失败: douban_id={douban_id} "
                f"parsed_title='{parsed_title}' "
                f"types={parsed_types} "
                f"score={parsed_score} "
                f"already_exists={bool(existing_check)} "
                f"html[:200]={html_preview[:200]}"
            )

        # ④ 自动注入 director_crawl 子任务（继承父任务 admin_id，独立 task_history）
        #    先注入子任务，再标记 douban_ids 完成：子任务注入失败不会导致
        #    douban_id 被错误标记为终态，管理员可重新提交。
        await self._emit_stage(task_str, "📋 创建演职人员爬取子任务...")
        await self._inject_director_subtask(data, movie_id)
        await self._emit_stage(task_str, "✅ 电影基础信息入库完成，子任务已入队")

        # ⑤ 更新 douban_ids（标记已认领；is_scraped 推迟到 director_crawl 成功后标记）
        raw = self._movie_service.db.raw_mysql()
        await raw.execute_update(
            "UPDATE douban_ids SET is_acquired=1, "
            "acquired_at=NOW(), task_id=%s "
            "WHERE douban_id=%s",
            (task_id, douban_id),
        )

        if cookie_id and self._identity_manager is not None:
            try:
                await self._identity_manager._cookie_manager.report_success(cookie_id)
            except Exception:
                pass

    async def _handle_movie_detail_crawl(self, data: dict) -> None:
        douban_id = data["douban_id"]
        title = data.get("title") or data.get("movie_title", "")
        task_id = data.get("id")

        logger.info(f"[电影详情补爬] task={task_id} douban_id={douban_id} title='{title}'")

        CELEB_PAGE_BASE = "https://movie.douban.com/subject/{douban_id}/celebrities"

        page_url = SUBJECT_PAGE_BASE.format(douban_id=douban_id)
        html = await self._browser_fetch(page_url)
        detail = parse_movie_detail(html)
        detail["douban_id"] = douban_id

        # 封面提取失败 → 保存 HTML 用于诊断
        if not detail.get("poster_url"):
            _pd = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
            os.makedirs(_pd, exist_ok=True)
            _pp = os.path.join(_pd, f"movie_detail_noposter_{douban_id}_{int(time.time())}.html")
            with open(_pp, "w", encoding="utf-8") as _f:
                _f.write(html)
            logger.warning(
                f"[movie_detail] douban_id={douban_id} poster_url 为空, "
                f"HTML 已保存至 {_pp}"
            )

        try:
            celeb_url = CELEB_PAGE_BASE.format(douban_id=douban_id)
            celeb_html = await self._browser_fetch(celeb_url)
            detail["crew"] = parse_personnel(celeb_html)
        except Exception as e:
            logger.error(f"[电影详情补爬] task={task_id} douban_id={douban_id} 参演人员获取失败: {e}")
            detail["crew"] = []

        if self._movie_service is None:
            logger.warning(f"[电影详情补爬] task={task_id} MovieService 未注入，跳过写入")
            return

        stats = await save_movies(self._movie_service, [detail])
        logger.info(
            f"[电影详情补爬] task={task_id} douban_id={douban_id} 完成: "
            f"created={stats['created']} skipped={stats['skipped']}"
        )
        if stats["failures"]:
            raise RuntimeError(
                f"save_movies 失败: "
                + "; ".join(f"{f['movie_data'].get('title', '?')}: {f['error']}" for f in stats["failures"])
            )

    async def _handle_review_crawl(self, data: dict) -> None:
        """
        长评摘要采集（v3 — 顺延模式）。

        每次取5条新评论，从已采集数量处顺延。

        输入：{type, douban_id|subject_id, movie_id}
        副作用：
            ① 查询已采集数量 → 计算偏移量
            ② 睡眠 45s（反反爬）
            ③ BrowserFetcher → subject/{id}/reviews?sort=hotest&start={offset}
            ④ parse_review_list → 最多5条
            ⑤ INSERT IGNORE movie_review (status='pending')
        """
        task_id = data.get("id")
        douban_id = data.get("douban_id") or data.get("subject_id", "")
        cookie_id = data.get("cookie_id", "")
        proxy_key = data.get("proxy_key", "")

        if self._movie_service is None:
            raise RuntimeError("MovieService 未注入，无法访问 movie_review 表")

        raw = self._movie_service.db.raw_mysql()

        # 解析 movie_id：优先请求参数，未传则用 douban_id 查询
        movie_id = data.get("movie_id")
        if not movie_id:
            rows = await raw.execute_query(
                "SELECT id AS movie_id FROM movies WHERE douban_id = %s LIMIT 1",
                (douban_id,),
            )
            if not rows:
                raise ValueError(f"该豆瓣ID对应的电影不存在: douban_id={douban_id}，请先提交单部电影爬取任务获取基础信息")
            movie_id = rows[0]["movie_id"]

        cfg = crawler_config
        task_str = json.dumps(data, ensure_ascii=False)

        # 1. 查询已采集数量，计算偏移量（顺延模式）
        count_result = await raw.execute_query(
            "SELECT COUNT(1) as cnt FROM movie_review WHERE movie_id=%s",
            (movie_id,),
        )
        existing_count = count_result[0].get("cnt", 0) if count_result else 0
        start = (existing_count // cfg.page_size) * cfg.page_size
        logger.info(
            f"[review_crawl] task={task_id} movie_id={movie_id} 已有 {existing_count} 条, "
            f"对齐后 offset={start} 顺延取 {cfg.review_crawl_max_new} 条"
        )

        # 2. 随机反爬等待（浏览模拟已内嵌至 fetcher._do_fetch）
        pre_wait = random.uniform(8, 20)
        logger.info(f"[review_crawl] 反爬等待 {pre_wait:.0f}s...")
        await self._emit_stage(task_str, f"⏳ 反爬等待 {pre_wait:.0f}s...")
        await asyncio.sleep(pre_wait)

        # 3. 翻页爬取（最多两次翻页：当前页 + 下一页，每页20条中取够5条）
        total_inserted = 0
        seen_rids = set()
        offset = start
        page_count = 0

        while total_inserted < cfg.review_crawl_max_new and page_count < 2:
            page_url = f"{REVIEW_LIST_BASE.format(douban_id=douban_id)}?sort=hotest&start={offset}"
            logger.info(f"[review_crawl] 第{page_count+1}次翻页: {page_url}")
            page_count += 1

            await self._emit_stage(task_str, f"📡 正在获取长评列表 (第{page_count}页)...")
            try:
                if identity:
                    html, ok, _ = await self._browser_fetch_page(page_url, identity)
                    if not ok:
                        raise FetcherError(f"列表页请求失败: {page_url}")
                else:
                    html = await self._browser_fetch(page_url)
                meta_list = parse_review_list(html)
                if not meta_list:
                    logger.info(f"[review_crawl] offset={offset} 无更多评论，停止翻页")
                    break

                new_count = 0
                for meta in meta_list:
                    rid = meta["review_id"]
                    if rid not in seen_rids:
                        seen_rids.add(rid)
                        await raw.execute_insert(
                            "INSERT IGNORE INTO movie_review "
                            "(review_id, movie_id, subject_id, title, author, useful_count, `date`) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (rid, movie_id, douban_id,
                             meta.get("title", ""),
                             meta.get("author", ""),
                             meta.get("useful_count", 0),
                             meta.get("date", "")),
                        )
                        new_count += 1
                        total_inserted += 1
                        if total_inserted >= cfg.review_crawl_max_new:
                            break

                logger.info(
                    f"[review_crawl] offset={offset}: 解析{len(meta_list)}条, 新增{new_count}条, "
                    f"累计{total_inserted}/{cfg.review_crawl_max_new}"
                )

                if new_count > 0:
                    await self._emit_stage(task_str, f"💾 已入库 {new_count} 条长评摘要")

                if total_inserted >= cfg.review_crawl_max_new:
                    break

                offset += cfg.page_size

            except Exception as e:
                logger.error(f"[review_crawl] offset={offset} 爬取失败: {e}")
                break

        logger.info(
            f"[review_crawl] task={task_id} 完成: 顺延从{start}开始, "
            f"新增摘要 {total_inserted} 条 → movie_review (movie_id={movie_id})"
        )

        if cookie_id and self._identity_manager is not None:
            try:
                await self._identity_manager._cookie_manager.report_success(cookie_id)
            except Exception:
                pass

    async def _handle_review_body_crawl(self, data: dict) -> None:
        """
        长评正文爬取 — 单条模式（v5：API JSON 接口代替浏览器 HTML）。

        输入：{review_id, movie_id?, douban_id|subject_id, title, author, date, useful_count}
        副作用：
            ApiFetcher 拉取 /j/review/{id}/full → parse_review_full → MongoDB upsert
            → UPDATE movie_review status='done'/'failed' → 检查是否触发 AI 总结

        设计决策（v4 — 改回单条模式）：
            - 每条长评一个独立任务，间隔由 worker_rest（120~300s 随机）保证
            - 避免 batch 模式下 cumulative sleep 导致 Monitor 误判 stuck
            - AI 总结由 _check_and_trigger_ai_summary 在每条完成后检查触发
        """
        task_id = data.get("id")
        review_id = data["review_id"]
        douban_id = data.get("douban_id") or data["subject_id"]
        title = data.get("title", "")
        author = data.get("author", "")
        date_str = data.get("date", "")
        useful_count = data.get("useful_count", 0)

        logger.info(
            f"[review_body_crawl] task={task_id} review_id={review_id} "
            f"douban_id={douban_id} title='{title}' author='{author}'"
        )

        task_str = json.dumps(data, ensure_ascii=False)

        if self._movie_service is None:
            raise RuntimeError("MovieService 未注入，无法访问 movie_review 表")

        raw = self._movie_service.db.raw_mysql()

        # 解析 movie_id：优先请求参数，未传则用 douban_id 查询
        movie_id = data.get("movie_id")
        if not movie_id:
            rows = await raw.execute_query(
                "SELECT id AS movie_id FROM movies WHERE douban_id = %s LIMIT 1",
                (douban_id,),
            )
            if not rows:
                raise ValueError(f"该豆瓣ID对应的电影不存在: douban_id={douban_id}，请先提交单部电影爬取任务获取基础信息")
            movie_id = rows[0]["movie_id"]

        from services.review_service import _get_review_service
        review_svc = _get_review_service()

        # 幂等判断：MongoDB 已存在该长评 → 直接标记 done，跳过爬取
        existing = await review_svc.get_review_by_id(review_id)
        if existing:
            await raw.execute_update(
                "UPDATE movie_review SET status='done' WHERE review_id=%s",
                (review_id,),
            )
            logger.info(f"[review_body_crawl] review_id={review_id} 已存在，跳过爬取")
            await self._check_and_trigger_ai_summary(movie_id, data.get("admin_id", 0), task_id or 0)
            return

        # ① 爬取长评正文（API JSON 接口，用 ApiFetcher 拉取 dict）
        try:
            await self._emit_stage(task_str, "📡 正在获取长评正文...")
            async with self._api_sem:
                api_url = REVIEW_FULL_API.format(review_id=review_id)
                data_api = await self._api.fetch(api_url)
                if not isinstance(data_api, dict):
                    raise RuntimeError(
                        f"长评API返回非dict: review_id={review_id} "
                        f"type={type(data_api).__name__}"
                    )
        except Exception as e:
            logger.error(f"[长评正文爬取] review_id={review_id} API请求失败: {e}")
            # 不修改 movie_review.status，保持 pending——管理员可直接重新提交
            raise

        # ② 解析内容 (parse_review_full 期望 dict，现在传入的是 API JSON)
        parsed = parse_review_full(data_api)
        parsed["review_id"] = review_id
        parsed["title"] = title
        parsed["author"] = author
        parsed["date"] = date_str
        parsed["useful_count"] = useful_count
        if not parsed.get("votes"):
            parsed["votes"] = str(useful_count)

        # ③ 写入 MongoDB + 更新 MySQL 状态（先写 Mongo，成功再改 MySQL）
        await self._emit_stage(task_str, "💾 正在保存长评正文...")
        saved = await save_reviews(douban_id, [parsed], movie_id=movie_id)
        if saved > 0:
            await raw.execute_update(
                "UPDATE movie_review SET status='done' WHERE review_id=%s",
                (review_id,),
            )
            logger.info(f"[review_body_crawl] task={task_id} review_id={review_id} 完成")
            # ④ 检查是否触发 AI 总结
            await self._check_and_trigger_ai_summary(movie_id, data.get("admin_id", 0), task_id or 0)
        else:
            logger.error(f"[review_body_crawl] review_id={review_id} MongoDB 写入失败，保持 pending")
            raise RuntimeError(f"长评 MongoDB 写入失败: review_id={review_id}")

    async def _handle_comment_crawl(self, data: dict) -> None:
        task_id = data.get("id")
        douban_id = data.get("douban_id") or data.get("subject_id", "")
        cookie_id = data.get("cookie_id", "")
        proxy_key = data.get("proxy_key", "")
        task_str = json.dumps(data, ensure_ascii=False)

        if self._movie_service is None:
            raise RuntimeError("MovieService 未注入，无法执行 douban_id 查询")

        # 解析可选的 identity
        identity = None
        if self._identity_manager is not None and (cookie_id or proxy_key):
            identity = await self._identity_manager.resolve(cookie_id, proxy_key)

        raw = self._movie_service.db.raw_mysql()

        # 解析 movie_id：优先请求参数，未传则用 douban_id 查询
        movie_id = data.get("movie_id")
        if not movie_id:
            rows = await raw.execute_query(
                "SELECT id AS movie_id FROM movies WHERE douban_id = %s LIMIT 1",
                (douban_id,),
            )
            if not rows:
                raise ValueError(f"该豆瓣ID对应的电影不存在: douban_id={douban_id}，请先提交单部电影爬取任务获取基础信息")
            movie_id = rows[0]["movie_id"]

        # 兼容前端统一的 pages 参数，兼容旧字段 comment_pages
        pages = data.get("pages") or data.get("comment_pages") or crawler_config.comment_list_pages
        logger.info(
            f"[短评爬取 pages解析] data.pages=%s data.comment_pages=%s config.default=%s → 最终 pages=%s",
            data.get("pages"), data.get("comment_pages"), crawler_config.comment_list_pages, pages,
        )

        # 查询已采集数量，计算顺延偏移（参照 review_crawl 的顺延模式）
        from services.review_service import _get_review_service
        review_svc = _get_review_service()
        existing_count = await review_svc.count_comments_by_movie_id(movie_id)
        # 向下取整到 page_size 的整数倍，保证豆瓣分页对齐（58→40, 30→20, 10→0）
        start_offset = (existing_count // crawler_config.page_size) * crawler_config.page_size
        logger.info(
            f"[短评爬取 顺延偏移] MongoDB 已有 %s 条 → 对齐后 start_offset=%s → 将从豆瓣第 %s 条开始 "
            f"→ 爬 %s 页 × %s 条/页 = 最多 %s 条",
            existing_count, start_offset, start_offset, pages, crawler_config.page_size,
            pages * crawler_config.page_size,
        )

        cfg = crawler_config

        # 随机反爬等待（浏览模拟已内嵌至 fetcher._do_fetch）
        pre_wait = random.uniform(3, 10)
        logger.info(f"[短评爬取 反爬等待] 预等待 {pre_wait:.0f}s")
        await asyncio.sleep(pre_wait)

        all_comments = []
        seen_cids = set()
        parse_error_count = 0

        for page_num in range(pages):
            # 翻页间随机等待（浏览模拟已内嵌至 fetcher._do_fetch）
            if page_num > 0:
                between_wait = random.uniform(5, 15)
                logger.info(f"[短评爬取 翻页等待] 第{page_num}/{pages}页前等待 {between_wait:.0f}s")
                await asyncio.sleep(between_wait)

            start = start_offset + page_num * crawler_config.page_size
            page_url = (
                f"{COMMENT_LIST_BASE.format(douban_id=douban_id)}"
                f"?start={start}&limit={crawler_config.page_size}&status=P"
            )
            logger.info(
                f"[短评爬取 翻页请求] 第%s/%s页 start=%s URL=%s",
                page_num + 1, pages, start, page_url,
            )

            await self._emit_stage(task_str, f"📡 正在获取短评 (第{page_num+1}页)...")
            try:
                html = ""
                if identity:
                    html, ok, _ = await self._browser_fetch_page(page_url, identity)
                    if not ok:
                        raise FetcherError(f"短评列表页请求失败: {page_url}")
                else:
                    html = await self._browser_fetch(page_url)
                page_comments = parse_comments(html)
                new_count = 0
                for c in page_comments:
                    cid = c.get("comment_id", "")
                    if cid and cid not in seen_cids:
                        seen_cids.add(cid)
                        all_comments.append(c)
                        new_count += 1
                logger.info(
                    f"[短评爬取 逐页解析] 第%s/%s页: 豆瓣返回%s条, 去重后新增%s条, 累计%s条",
                    page_num + 1, pages, len(page_comments), new_count, len(all_comments),
                )
            except Exception as e:
                parse_error_count += 1
                logger.error(f"[短评爬取 翻页失败] 第%s/%s页异常: %s", page_num + 1, pages, e)
                # 保存失败页面 HTML 到本地，便于排查（反爬页面 / 结构变更 / 验证页）
                try:
                    import os as _os2
                    dump_dir = _os2.path.join(_os2.path.dirname(_os2.path.dirname(__file__)), "data")
                    _os2.makedirs(dump_dir, exist_ok=True)
                    dump_path = _os2.path.join(
                        dump_dir,
                        f"comment_fail_m{movie_id}_p{page_num+1}_{int(_time.time())}.html"
                    )
                    with open(dump_path, "w", encoding="utf-8") as f:
                        f.write(html)
                    logger.info(f"[短评爬取 翻页失败] 已保存问题 HTML: {dump_path}")
                except Exception as _dump_err:
                    logger.warning(f"[短评爬取 翻页失败] HTML 保存失败: {_dump_err}")
                await self._report_item_failure(
                    task_data=data,
                    kind=classify_item_error(e),
                    reason=str(e),
                    item_douban_id=f"page_{page_num+1}",
                    item_title=f"短评第{page_num+1}页",
                )
                continue

        if all_comments:
            await self._emit_stage(task_str, f"💾 已入库 {len(all_comments)} 条短评")
            saved = await save_comments(douban_id or "", all_comments, movie_id=movie_id)
            logger.info(
                f"[短评爬取 入库完成] 解析%s条, MongoDB入库%s条, movie_id=%s",
                len(all_comments), saved, movie_id,
            )
            if saved > 0 and movie_id:
                from db.redis import redis_delete
                await redis_delete(f"wordcloud:movie:{movie_id}")
                # ZADD ai_wordcloud 任务（正式任务，走任务生命周期）
                await self._emit_stage(task_str, "📋 已提交词云生成任务")
                await self._inject_ai_wordcloud(movie_id, parent_task_id=task_id)
                logger.debug(f"[短评爬取 词云触发] 已清除旧缓存并提交 ai_wordcloud 任务: movie_id={movie_id}")

            if cookie_id and self._identity_manager is not None:
                try:
                    await self._identity_manager._cookie_manager.report_success(cookie_id)
                except Exception:
                    pass
        elif parse_error_count > 0:
            # 解析全部失败 → 抛异常，让 Worker 标记任务为 failed
            raise RuntimeError(
                f"[短评爬取 任务失败] movie_id={movie_id} "
                f"{pages} 页全部解析失败（共 {parse_error_count} 次异常），"
                f"可能页面结构变更或被反爬，HTML 已保存至 data/ 目录"
            )
        else:
            logger.warning(f"[短评爬取 空结果] movie_id=%s 未获取到任何短评", movie_id)

    async def _handle_director_crawl(self, data: dict) -> None:
        """
        演职人员补爬任务（P0 解耦后独立调度）。

        输入：{type, douban_id, movie_id, admin_id?, cookie_id?, proxy_key?, ...}
        输出：无（成功返回，失败抛异常）
        副作用：BrowserFetcher 爬 celebrities 页 → save_crew（事务原子写入）
        """
        task_id = data.get("id")
        douban_id = data.get("douban_id", "")
        movie_id = data.get("movie_id")
        cookie_id = data.get("cookie_id", "")
        proxy_key = data.get("proxy_key", "")

        if not douban_id:
            raise ValueError("director_crawl 任务缺少 douban_id 字段")
        if not movie_id:
            raise ValueError("director_crawl 任务缺少 movie_id 字段")

        CELEB_PAGE_BASE = "https://movie.douban.com/subject/{douban_id}/celebrities"
        celeb_url = CELEB_PAGE_BASE.format(douban_id=douban_id)

        logger.info(
            f"[director_crawl] task={task_id} douban_id={douban_id} movie_id={movie_id} "
            f"cookie={cookie_id or '游客'} proxy={proxy_key or '直连'}"
        )

        if self._movie_service is None:
            raise RuntimeError("MovieService 未注入，无法写入数据库")

        # 构建身份（继承父任务 cookie + proxy，游客模式兜底）
        task_str = json.dumps(data, ensure_ascii=False)
        identity = None
        if self._identity_manager is not None and (cookie_id or proxy_key):
            await self._emit_stage(task_str, f"🔍 正在解析身份: cookie={cookie_id or '游客'} proxy={proxy_key or '直连'}")
            identity = await self._identity_manager.resolve(cookie_id, proxy_key)
            await self._emit_stage(task_str, f"✅ 身份就绪: cookie={cookie_id or '游客'} proxy={proxy_key or '直连'}")
        else:
            await self._emit_stage(task_str, "👤 未指定身份，使用游客模式")

        # 爬取 celebrities 页
        await self._emit_stage(task_str, f"📡 正在请求演职人员页: {celeb_url}")
        html, ok, _ = await self._browser_fetch_page(celeb_url, identity)
        if not ok:
            raise FetcherError(f"演职人员页获取失败: douban_id={douban_id}")

        # 解析全部角色类型（导演/演员/编剧/制片/美术/音乐/其他）
        crew = parse_personnel(html)
        if not crew:
            logger.warning(f"[director_crawl] task={task_id} 未提取到演职人员信息")
            raw = self._movie_service.db.raw_mysql()
            await raw.execute_update(
                "UPDATE douban_ids SET is_scraped=1 WHERE douban_id=%s",
                (douban_id,),
            )
            return

        # 事务原子写入 people + movie_credits
        await self._emit_stage(task_str, f"💾 正在写入 {len(crew)} 名演职人员...")
        saved = await storage.save_crew(self._movie_service, movie_id, crew)
        logger.info(
            f"[director_crawl] task={task_id} 完成: "
            f"saved={saved}/{len(crew)} 种角色"
        )

        raw = self._movie_service.db.raw_mysql()
        await raw.execute_update(
            "UPDATE douban_ids SET is_scraped=1 WHERE douban_id=%s",
            (douban_id,),
        )

    # ── 内部：子任务注入 ──

    async def _inject_director_subtask(self, parent_data: dict, movie_id: int) -> None:
        """
        movie_scrape_task 成功后自动创建 director_crawl 子任务。

        输入：
            parent_data: 父任务 JSON dict（含 admin_id, douban_id, created_at）
            movie_id:    save_movie_basic 返回的电影 ID
        副作用：
            调用 inject_subtask → ZADD Redis + INSERT task_history
        """
        from crawler.subtask import inject_subtask

        task_data: dict = {
            "douban_id": parent_data.get("douban_id", ""),
            "movie_id": movie_id,
            "movie_title": parent_data.get("movie_title", ""),
        }

        # 继承父任务的 Cookie 和代理（否则子任务会退化为游客+直连，容易被反爬）
        parent_cookie = parent_data.get("cookie_id", "")
        parent_proxy = parent_data.get("proxy_key", "")
        if parent_cookie:
            task_data["cookie_id"] = parent_cookie
        if parent_proxy:
            task_data["proxy_key"] = parent_proxy

        # 安全兜底：父任务未携带 movie_title 时从 movies 表查询
        if not task_data["movie_title"]:
            try:
                raw = self._movie_service.db.raw_mysql()
                rows = await raw.execute_query(
                    "SELECT title FROM movies WHERE id=%s LIMIT 1",
                    (movie_id,),
                )
                if rows:
                    task_data["movie_title"] = rows[0]["title"]
            except Exception:
                logger.warning("[导演子任务注入] 查询电影名失败 movie_id=%s", movie_id, exc_info=True)

        await inject_subtask(
            db=self._movie_service.db,
            task_type="director_crawl",
            task_data=task_data,
            admin_id=parent_data.get("admin_id", 0),
            parent_task_id=parent_data.get("id", 0),
        )

    async def _trigger_ai_summary_inline(self, raw, review_svc, movie_id: int) -> None:
        """
        批次完成后直接调用 AI 生成总结（v3 — 内联模式，不走 Redis ZSET）。

        输入：
            raw:        raw_mysql 实例
            review_svc: ReviewService 实例
            movie_id:   本地电影ID
        副作用：
            ① 统计 done 数量
            ② >=5 条：选 top10 by useful_count
            ③ 从 MongoDB 取全文 → 截取 800 字
            ④ 调用 AI → 写入 review_summary
        """
        cfg = crawler_config

        try:
            # 1. 幂等检查：已生成过总结则跳过
            summary_check = await raw.execute_query(
                "SELECT 1 FROM review_summary WHERE movie_id=%s AND status='done' LIMIT 1",
                (movie_id,),
            )
            if summary_check and len(summary_check) > 0:
                logger.info(f"[AI总结-内联] movie_id={movie_id} 已存在总结，跳过")
                return

            # 2. 统计已完成的长评数量
            count_result = await raw.execute_query(
                "SELECT COUNT(1) as cnt FROM movie_review WHERE movie_id=%s AND status='done'",
                (movie_id,),
            )
            done_count = count_result[0].get("cnt", 0) if count_result else 0
            logger.info(f"[AI总结-内联] movie_id={movie_id} 已完成长评: {done_count} 条")

            if done_count < cfg.ai_summary_min_reviews:
                logger.info(
                    f"[AI总结-内联] movie_id={movie_id} 长评数量不足 "
                    f"({done_count}/{cfg.ai_summary_min_reviews})，暂不生成"
                )
                return

            # 3. 选 topN by useful_count
            top_reviews = await raw.execute_query(
                "SELECT review_id, title, author, useful_count "
                "FROM movie_review "
                "WHERE movie_id=%s AND status='done' "
                "ORDER BY useful_count DESC "
                "LIMIT %s",
                (movie_id, cfg.ai_summary_max_reviews),
            )
            if not top_reviews:
                logger.warning(f"[AI总结-内联] movie_id={movie_id} 无可用长评")
                return

            logger.info(
                f"[AI总结-内联] movie_id={movie_id} 选取 top{len(top_reviews)} 条长评"
            )

            # 4. 从 MongoDB 获取每条长评的完整正文
            ai_reviews = []
            for row in top_reviews:
                rid = row["review_id"]
                mongo_doc = await review_svc.get_review_by_id(rid)
                if mongo_doc:
                    full_text = mongo_doc.get("text", "")
                    truncated = full_text[:cfg.ai_summary_max_chars]
                    ai_reviews.append({
                        "content": truncated,
                        "useful_count": row.get("useful_count", 0),
                    })
                else:
                    logger.warning(f"[AI总结-内联] review_id={rid} MongoDB 无记录")

            if len(ai_reviews) < cfg.ai_summary_min_reviews:
                logger.info(
                    f"[AI总结-内联] movie_id={movie_id} 有效长评不足 "
                    f"({len(ai_reviews)}/{cfg.ai_summary_min_reviews})，跳过"
                )
                return

            # 5. 插入 pending 记录（防重复）
            await raw.execute_update(
                "INSERT INTO review_summary (movie_id, status, created_at, updated_at) "
                "VALUES (%s, 'pending', NOW(), NOW()) "
                "ON DUPLICATE KEY UPDATE status='pending', updated_at=NOW()",
                (movie_id,),
            )

            # 6. 调用 AI
            logger.info(f"[AI总结-内联] movie_id={movie_id} 开始调用 AI ({len(ai_reviews)} 条, 每条≤{cfg.ai_summary_max_chars}字)")
            from utils.ai_client import get_ai_client
            ai_client = get_ai_client()
            result = await ai_client.generate_review_summary(
                ai_reviews,
                max_chars_per_review=cfg.ai_summary_max_chars,
            )

            if not result:
                logger.error(f"[AI总结-内联] movie_id={movie_id} AI 生成失败")
                return

            # 7. 保存结果
            full_summary = result.get("full_summary", "")
            tags = json.dumps(result.get("tags", []), ensure_ascii=False)

            await raw.execute_update(
                "UPDATE review_summary "
                "SET full_summary=%s, review_tags=%s, status='done', updated_at=NOW() "
                "WHERE movie_id=%s",
                (full_summary, tags, movie_id),
            )

            logger.info(
                f"[AI总结-内联] movie_id={movie_id} 生成成功: "
                f"总结{len(full_summary)}字, 标签{len(result.get('tags', []))}个"
            )

            # 8. 同步写入风格标签表（新增逻辑，幂等，不影响主流程）
            try:
                style_dims = result.get('style_dimensions', {})
                if not isinstance(style_dims, dict) or not style_dims:
                    logger.info(
                        f"[AI总结-内联|风格标签] movie_id={movie_id} AI 未返回 style_dimensions，跳过写入"
                    )
                    return

                _DIM_ORDER = ('overall', 'plot', 'visual', 'narrative', 'pacing')
                _DIM_CN = {'overall': '整体', 'plot': '剧情', 'visual': '画面', 'narrative': '叙事', 'pacing': '节奏'}

                total_dims = sum(1 for k in _DIM_ORDER if isinstance(style_dims.get(k), dict))
                logger.info(
                    f"[AI总结-内联|风格标签] movie_id={movie_id} 开始写入，"
                    f"AI 返回 {total_dims}/5 个维度数据"
                )

                written_tags = 0
                skipped_tags = 0
                written_links = 0

                for dim_key in _DIM_ORDER:
                    dim = style_dims.get(dim_key)
                    if not isinstance(dim, dict):
                        skipped_tags += 1
                        logger.debug(
                            f"[AI总结-内联|风格标签] movie_id={movie_id} "
                            f"{_DIM_CN.get(dim_key, dim_key)} 维度缺失数据，跳过"
                        )
                        continue

                    label = dim.get('label', '').strip()
                    confidence = float(dim.get('confidence', 1.0))

                    # 过滤无效标签
                    if not label or label == '无显著特征':
                        skipped_tags += 1
                        logger.info(
                            f"[AI总结-内联|风格标签] movie_id={movie_id} "
                            f"{_DIM_CN.get(dim_key, dim_key)} → 无显著特征，跳过"
                        )
                        continue
                    if confidence < 0.5:
                        skipped_tags += 1
                        logger.info(
                            f"[AI总结-内联|风格标签] movie_id={movie_id} "
                            f"{_DIM_CN.get(dim_key, dim_key)} → '{label}' "
                            f"可信度={confidence:.1f}（低于0.5），跳过"
                        )
                        continue

                    # 插入标签字典（幂等）
                    logger.debug(
                        f"[AI总结-内联|风格标签] movie_id={movie_id} "
                        f"{_DIM_CN.get(dim_key, dim_key)} → 写入标签 '{label}' confidence={confidence:.1f}"
                    )
                    affected = await raw.execute_update(
                        "INSERT IGNORE INTO movie_style_tag (name, dimension) VALUES (%s, %s)",
                        (label, dim_key)
                    )
                    is_new_tag = (affected > 0)

                    # 获取标签ID（新插入或已存在的）
                    tag_rows = await raw.execute_query(
                        "SELECT id FROM movie_style_tag WHERE name=%s AND dimension=%s LIMIT 1",
                        (label, dim_key)
                    )
                    if tag_rows:
                        tag_id = tag_rows[0]['id']
                        written_tags += 1
                        # 插入关联关系（幂等，保留最高置信度）
                        await raw.execute_update(
                            "INSERT INTO movie_style (movie_id, tag_id, confidence) VALUES (%s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE confidence = GREATEST(confidence, VALUES(confidence))",
                            (movie_id, tag_id, confidence)
                        )
                        written_links += 1
                        logger.info(
                            f"[AI总结-内联|风格标签] movie_id={movie_id} ✅ "
                            f"{_DIM_CN.get(dim_key, dim_key)}='{label}' "
                            f"tag_id={tag_id} confidence={confidence:.1f}"
                            f"{' (新标签，触发相似度检测)' if is_new_tag else ''}"
                        )
                        # 新标签 → 异步触发同维度相似度检测
                        if is_new_tag:
                            asyncio.create_task(
                                _trigger_similarity_check(tag_id, dim_key)
                            )
                    else:
                        logger.warning(
                            f"[AI总结-内联|风格标签] movie_id={movie_id} "
                            f"标签 '{label}'({_DIM_CN.get(dim_key, dim_key)}) "
                            f"INSERT IGNORE 后查询失败，可能被并发删除"
                        )

                logger.info(
                    f"[AI总结-内联|风格标签] movie_id={movie_id} 写入完成: "
                    f"movie_style_tag +{written_tags} 跳过{skipped_tags} | "
                    f"movie_style +{written_links}"
                )
            except Exception as e:
                logger.warning(f"[AI总结-内联|风格标签] movie_id={movie_id} 写入异常: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"[AI总结-内联] movie_id={movie_id} 异常: {e}", exc_info=True)
            raise

    async def _inject_ai_wordcloud(self, movie_id: int, parent_task_id: int = 0) -> None:
        """
        comment_crawl 完成后自动提交 ai_wordcloud 任务。

        自动从 movies 表查询 douban_id 和 title 写入 task_data，
        保证管理端历史记录和实时队列中能展示完整的电影信息。
        """
        from crawler.subtask import inject_subtask

        task_data: dict = {"movie_id": movie_id}
        try:
            raw = self._movie_service.db.raw_mysql()
            rows = await raw.execute_query(
                "SELECT douban_id, title FROM movies WHERE id=%s LIMIT 1",
                (movie_id,),
            )
            if rows:
                task_data["douban_id"] = rows[0].get("douban_id", "")
                task_data["movie_title"] = rows[0].get("title", "")
        except Exception:
            logger.warning("[AI词云注入] 查询电影元数据失败 movie_id=%s", movie_id, exc_info=True)

        await inject_subtask(
            db=self._movie_service.db,
            task_type="ai_wordcloud",
            task_data=task_data,
            parent_task_id=parent_task_id,
        )

    async def _check_and_trigger_ai_summary(
        self, 
        movie_id: int, 
        admin_id: int = 0, 
        parent_task_id: int = 0
    ) -> None:
        """
        检查电影已完成长评数量，达到阈值则触发AI总结任务（幂等，同一电影只触发一次）。
        v3: 阈值从20改为配置项 ai_summary_min_reviews（默认5）。
        
        输入：
            movie_id: 本地电影ID
            admin_id: 归属管理员ID（0=系统）
            parent_task_id: 父任务ID（0=无父任务）
        副作用：推送ai_review_summary任务到队列，写入task_history
        """
        if self._movie_service is None:
            return
        
        cfg = crawler_config
        raw = self._movie_service.db.raw_mysql()
        try:
            # 1. 先检查是否已经生成过总结，防止重复触发（只跳过 done，pending/failed 可重来）
            summary_check = await raw.execute_query(
                "SELECT 1 FROM review_summary WHERE movie_id=%s AND status='done' LIMIT 1",
                (movie_id,),
            )
            if summary_check and len(summary_check) > 0:
                # 回填检查：总结已完成但 movie_style 可能为空（旧版无风格标签写入）
                style_check = await raw.execute_query(
                    "SELECT 1 FROM movie_style WHERE movie_id=%s LIMIT 1",
                    (movie_id,),
                )
                if style_check and len(style_check) > 0:
                    logger.debug(f"[AI总结] movie_id={movie_id} 已有总结+风格标签，跳过触发")
                    return
                else:
                    logger.info(
                        f"[AI总结-回填] movie_id={movie_id} 总结存在但风格标签缺失，注入回填任务"
                    )

            # 2. 统计已完成的长评数量
            count_result = await raw.execute_query(
                "SELECT COUNT(1) as cnt FROM movie_review WHERE movie_id=%s AND status='done'",
                (movie_id,),
            )
            done_count = count_result[0].get("cnt", 0) if count_result else 0
            
            logger.debug(f"[AI总结] movie_id={movie_id} 已完成长评数量: {done_count}/{cfg.ai_summary_min_reviews}")
            
            # 3. 达到阈值则推送任务
            if done_count >= cfg.ai_summary_min_reviews:
                from crawler.subtask import inject_subtask

                task_data: dict = {"movie_id": movie_id}
                try:
                    meta_rows = await raw.execute_query(
                        "SELECT douban_id, title FROM movies WHERE id=%s LIMIT 1",
                        (movie_id,),
                    )
                    if meta_rows:
                        task_data["douban_id"] = meta_rows[0].get("douban_id", "")
                        task_data["movie_title"] = meta_rows[0].get("title", "")
                except Exception:
                    logger.warning("[AI总结触发] 查询电影元数据失败 movie_id=%s", movie_id, exc_info=True)

                await inject_subtask(
                    db=self._movie_service.db,
                    task_type="ai_review_summary",
                    task_data=task_data,
                    admin_id=admin_id,
                    parent_task_id=parent_task_id,
                )
        
        except Exception as e:
            logger.error(f"[AI总结] 检查触发逻辑异常: {e}", exc_info=True)

    async def _handle_ai_review_summary(self, data: dict) -> None:
        """
        AI评论总结任务处理。
        
        输入：{'movie_id': 电影ID, ...}
        副作用：拉取长评 → 调用AI生成总结 → 写入review_summary表
        """
        task_id = data.get("id")
        movie_id = data["movie_id"]
        
        logger.info(f"[AI总结] 开始处理 task_id={task_id}, movie_id={movie_id}")
        
        task_str = json.dumps(data, ensure_ascii=False)

        if self._movie_service is None:
            raise RuntimeError("MovieService 未注入，无法访问数据库")
        
        raw = self._movie_service.db.raw_mysql()
        from services.review_service import _get_review_service
        review_svc = _get_review_service()
        
        cfg = crawler_config

        try:
            # 1. 幂等检查：已成功生成过则跳过（pending/failed 可重来）
            existing = await raw.execute_query(
                "SELECT id FROM review_summary WHERE movie_id=%s AND status='done' LIMIT 1",
                (movie_id,),
            )
            if existing and len(existing) > 0:
                # 回填检查：summary 已存在但 movie_style 可能为空
                #   场景：旧版 AI 生成了 summary 但没写 movie_style_tag/movie_style
                #         重新爬取后需要补写风格标签
                style_check = await raw.execute_query(
                    "SELECT COUNT(1) AS cnt FROM movie_style WHERE movie_id=%s",
                    (movie_id,),
                )
                has_style = style_check and style_check[0].get("cnt", 0) > 0
                if has_style:
                    logger.info(f"[AI总结] movie_id={movie_id} 已存在总结+风格标签，跳过处理")
                    return
                else:
                    logger.info(
                        f"[AI总结-回填] movie_id={movie_id} 总结已存在但风格标签缺失，"
                        f"将重新生成以回填 movie_style_tag / movie_style"
                    )
            
            # 2. 先插入一条pending记录，防止重复任务并发处理
            await raw.execute_update(
                "INSERT INTO review_summary (movie_id, status, created_at, updated_at) "
                "VALUES (%s, 'pending', NOW(), NOW()) "
                "ON DUPLICATE KEY UPDATE status='pending', updated_at=NOW()",
                (movie_id,),
            )
            
            # 3. 拉取该电影最高赞的20条长评全文
            await self._emit_stage(task_str, "📡 正在拉取长评数据...")
            reviews = await review_svc.get_top_reviews_by_movie_id(movie_id, limit=20)
            if not reviews or len(reviews) < cfg.ai_summary_min_reviews:
                logger.warning(f"[AI总结] movie_id={movie_id} 有效长评数量不足{cfg.ai_summary_min_reviews}条，暂不生成")
                await raw.execute_update(
                    "UPDATE review_summary SET status='pending' WHERE movie_id=%s",
                    (movie_id,),
                )
                return
            
            logger.info(f"[AI总结] 拉取到{len(reviews)}条有效长评，开始生成总结")
            
            # 4. 调用AI生成总结
            from utils.ai_client import get_ai_client
            await self._emit_stage(task_str, "🤖 正在调用 AI 生成总结...")
            ai_client = get_ai_client()
            result = await ai_client.generate_review_summary(reviews)
            
            if not result:
                # 生成失败，不修改 review_summary.status
                # status 保持 pending——下次有新长评入库时会重新触发 AI 总结
                sn = getattr(ai_client, 'last_snapshot', {}) or {}
                raise RuntimeError(
                    f"AI总结生成失败 movie_id={movie_id} "
                    f"provider={sn.get('provider', '?')} "
                    f"last_status={sn.get('last_status', 'N/A')} "
                    f"attempts={sn.get('attempts', 0)}"
                )

            # ⑤ 保存结果到数据库
            full_summary = result.get("full_summary", "")
            tags = json.dumps(result.get("tags", []), ensure_ascii=False)
            
            await self._emit_stage(task_str, "💾 正在保存 AI 总结...")
            await raw.execute_update(
                "UPDATE review_summary "
                "SET full_summary=%s, review_tags=%s, status='done', updated_at=NOW() "
                "WHERE movie_id=%s",
                (full_summary, tags, movie_id),
            )

            # ⑥ 同步写入风格标签表（新增逻辑，幂等，不影响主流程）
            await self._emit_stage(task_str, "🎨 正在写入风格标签...")
            try:
                style_dims = result.get('style_dimensions', {})
                if not isinstance(style_dims, dict) or not style_dims:
                    logger.info(
                        f"[AI总结|风格标签] movie_id={movie_id} AI 未返回 style_dimensions，跳过写入"
                    )
                    return

                _DIM_ORDER = ('overall', 'plot', 'visual', 'narrative', 'pacing')
                _DIM_CN = {'overall': '整体', 'plot': '剧情', 'visual': '画面', 'narrative': '叙事', 'pacing': '节奏'}

                total_dims = sum(1 for k in _DIM_ORDER if isinstance(style_dims.get(k), dict))
                await self._emit_stage(
                    task_str,
                    f"🎨 AI 返回 {total_dims}/5 个维度，开始写入 movie_style_tag / movie_style"
                )
                logger.info(
                    f"[AI总结|风格标签] movie_id={movie_id} 开始写入，"
                    f"AI 返回 {total_dims}/5 个维度数据"
                )

                written_tags = 0
                skipped_tags = 0
                written_links = 0

                for dim_key in _DIM_ORDER:
                    dim = style_dims.get(dim_key)
                    if not isinstance(dim, dict):
                        skipped_tags += 1
                        logger.debug(
                            f"[AI总结|风格标签] movie_id={movie_id} "
                            f"{_DIM_CN.get(dim_key, dim_key)} 维度缺失数据，跳过"
                        )
                        continue

                    label = dim.get('label', '').strip()
                    confidence = float(dim.get('confidence', 1.0))

                    # 过滤无效标签
                    if not label or label == '无显著特征':
                        skipped_tags += 1
                        logger.info(
                            f"[AI总结|风格标签] movie_id={movie_id} "
                            f"{_DIM_CN.get(dim_key, dim_key)} → 无显著特征，跳过"
                        )
                        continue
                    if confidence < 0.5:
                        skipped_tags += 1
                        logger.info(
                            f"[AI总结|风格标签] movie_id={movie_id} "
                            f"{_DIM_CN.get(dim_key, dim_key)} → '{label}' "
                            f"可信度={confidence:.1f}（低于0.5），跳过"
                        )
                        continue

                    # 插入标签字典（幂等）
                    logger.debug(
                        f"[AI总结|风格标签] movie_id={movie_id} "
                        f"{_DIM_CN.get(dim_key, dim_key)} → 写入标签 '{label}' confidence={confidence:.1f}"
                    )
                    affected = await raw.execute_update(
                        "INSERT IGNORE INTO movie_style_tag (name, dimension) VALUES (%s, %s)",
                        (label, dim_key)
                    )
                    is_new_tag = (affected > 0)

                    # 获取标签ID（新插入或已存在的）
                    tag_rows = await raw.execute_query(
                        "SELECT id FROM movie_style_tag WHERE name=%s AND dimension=%s LIMIT 1",
                        (label, dim_key)
                    )
                    if tag_rows:
                        tag_id = tag_rows[0]['id']
                        written_tags += 1
                        # 插入关联关系（幂等，保留最高置信度）
                        await raw.execute_update(
                            "INSERT INTO movie_style (movie_id, tag_id, confidence) VALUES (%s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE confidence = GREATEST(confidence, VALUES(confidence))",
                            (movie_id, tag_id, confidence)
                        )
                        written_links += 1
                        logger.info(
                            f"[AI总结|风格标签] movie_id={movie_id} ✅ "
                            f"{_DIM_CN.get(dim_key, dim_key)}='{label}' "
                            f"tag_id={tag_id} confidence={confidence:.1f}"
                            f"{' (新标签，触发相似度检测)' if is_new_tag else ''}"
                        )
                        # 新标签 → 异步触发同维度相似度检测
                        if is_new_tag:
                            asyncio.create_task(
                                _trigger_similarity_check(tag_id, dim_key)
                            )
                    else:
                        logger.warning(
                            f"[AI总结|风格标签] movie_id={movie_id} "
                            f"标签 '{label}'({_DIM_CN.get(dim_key, dim_key)}) "
                            f"INSERT IGNORE 后查询失败，可能被并发删除"
                        )

                await self._emit_stage(
                    task_str,
                    f"🎨 风格标签写入完成: movie_style_tag +{written_tags} 跳过{skipped_tags} | movie_style +{written_links}"
                )
                logger.info(
                    f"[AI总结|风格标签] movie_id={movie_id} 写入完成: "
                    f"movie_style_tag +{written_tags} 跳过{skipped_tags} | "
                    f"movie_style +{written_links}"
                )
            except Exception as e:
                logger.warning(f"[AI总结|风格标签] movie_id={movie_id} 写入异常: {e}", exc_info=True)
            
            logger.info(f"[AI总结] movie_id={movie_id} 生成成功，已保存到数据库")
            
        except Exception as e:
            logger.error(f"[AI总结] 处理失败 task_id={task_id}, movie_id={movie_id}: {e}", exc_info=True)
            # 不修改 review_summary.status——保持 pending，下次有新长评入库时会重新触发
            raise

    # ── AI 词云生成任务 ──

    async def _handle_ai_wordcloud(self, data: dict) -> None:
        """
        AI 短评词云生成任务。

        输入：{'movie_id': 电影ID, ...}
        副作用：MongoDB 查询 → DeepSeek AI 生成 → Redis 缓存
        """
        task_id = data.get("id")
        movie_id = data["movie_id"]

        logger.info(f"[AI词云] 开始处理 task_id=%s movie_id=%s", task_id, movie_id)

        task_str = json.dumps(data, ensure_ascii=False)

        try:
            from services.review_service import _get_review_service
            from utils.ai_client import get_ai_client
            from db.redis import redis_set

            review_svc = _get_review_service()
            await self._emit_stage(task_str, "📡 正在拉取短评数据...")
            comments = await review_svc.get_comments_text_by_movie_id(movie_id, limit=100)
            if len(comments) < 10:
                logger.info("[AI词云] movie_id=%s 短评不足 10 条，跳过", movie_id)
                return

            ai_client = get_ai_client()
            await self._emit_stage(task_str, "🤖 正在调用 AI 生成词云...")
            words = await ai_client.generate_comment_wordcloud(comments)
            if not words:
                sn = getattr(ai_client, 'last_snapshot', {}) or {}
                raise RuntimeError(
                    f"AI 词云生成失败 movie_id={movie_id} "
                    f"provider={sn.get('provider', '?')} "
                    f"last_status={sn.get('last_status', 'N/A')} "
                    f"attempts={sn.get('attempts', 0)}"
                )

            import json as _json
            from datetime import datetime
            data_wc = {
                "words": words,
                "total_words": len(words),
                "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            }
            await self._emit_stage(task_str, "💾 正在缓存词云...")
            await redis_set(
                f"wordcloud:movie:{movie_id}",
                _json.dumps(data_wc, ensure_ascii=False),
            )
            logger.info("[AI词云] movie_id=%s 完成，%s 个关键词已缓存", movie_id, len(words))

        except Exception as e:
            logger.error("[AI词云] 失败 task_id=%s movie_id=%s: %s", task_id, movie_id, e)
            raise

    # ── 内部：失败上报 ──

    async def _report_item_failure(
        self,
        task_data: dict,
        kind: str,
        reason: str,
        item_douban_id: str,
        item_title: str,
    ) -> None:
        """
        上报单部电影级失败到 task_failures。
        写入失败只记日志，不中断主流程。
        """
        try:
            from services.task_failure_service import _get_failure_service
            svc = _get_failure_service()

            await svc.insert_failure(
                task_id=task_data.get("id", 0),
                admin_id=task_data.get("admin_id", 0),
                kind=kind,
                reason=reason,
                scope="item",
                item_douban_id=item_douban_id,
                item_title=item_title,
            )
        except Exception:
            logger.exception("上报 item 级失败异常（不影响主流程）")


# ═══════════════════════════════════════════════════════════════
# 模块级单例管理（与 Puller/BrowserPool 一致）
# ═══════════════════════════════════════════════════════════════

_engine: Optional[CrawlerEngine] = None


def init_crawler(browser, movie_service=None, playwright=None, event_queue=None):
    """
    初始化 CrawlerEngine 单例。

    输入：
        browser:       Playwright Chromium 浏览器实例
        movie_service: MovieService 实例（用于 MySQL 写入，可选）
        playwright:    Playwright 入口对象（用于浏览器崩溃后自动重启）
        event_queue:   Worker 事件队列（用于 Crawler 异步上报进度/阶段变更）
    输出：CrawlerEngine 实例
    副作用：设置模块级 _engine 单例 + 初始化 CookieManager/IdentityManager
    """
    global _engine

    # P0 — 初始化 Identity 管理（向后兼容，失败不影响旧行为）
    identity_manager = None
    if IdentityManager is not None and get_cookie_manager is not None:
        try:
            cookie_mgr = get_cookie_manager()
            proxy_pool = get_proxy_pool()
            identity_manager = IdentityManager(cookie_mgr, proxy_pool)
            logger.info("IdentityManager 已就绪")
        except Exception:
            logger.warning("IdentityManager 初始化失败（不影响旧行为）", exc_info=True)

    _engine = CrawlerEngine(
        browser=browser,
        movie_service=movie_service,
        playwright=playwright,
        identity_manager=identity_manager,
        event_queue=event_queue,
    )
    return _engine


def get_crawler() -> CrawlerEngine:
    """获取 CrawlerEngine 单例。未初始化时抛出 RuntimeError。"""
    if _engine is None:
        raise RuntimeError("CrawlerEngine 未初始化，请先调用 init_crawler()")
    return _engine


# ── 向后兼容的模块级入口（app.py 直接引用） ──

async def execute(task: str) -> None:
    """执行爬虫任务（委托给单例 CrawlerEngine）。"""
    return await get_crawler().execute(task)


async def _verify_douban_storage() -> bool:
    """验证豆瓣登录态（委托给单例 CrawlerEngine）。"""
    return await get_crawler().verify_douban_storage()
