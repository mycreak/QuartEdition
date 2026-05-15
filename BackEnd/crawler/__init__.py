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
        else:
            raise NotImplementedError(f"未知任务类型: {task_type}")

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
        result = await self._api.fetch(list_url)
        if not isinstance(result, list):
            raise ValueError(f"电影 API 返回非列表类型: {type(result).__name__}")

        id_list = parse_movie_list(result)
        logger.info(f"[movie_crawl] task={task_id} 榜单返回 {len(id_list)} 条")

        # ④ 原子事务: INSERT IGNORE douban_ids + 推进 ids_fetched
        #    两者在同一事务中提交/回滚，保证断点续爬的 start 偏移正确
        #    即使多次提交同类型-区间的 movie_crawl，ids_fetched 也始终与实际 API 分页一致
        written = 0
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
        title = data.get("title", "")
        cookie_id = data.get("cookie_id", "")
        proxy_key = data.get("proxy_key", "")
        task_id = data.get("id")

        logger.info(
            f"[movie_scrape] task={task_id} douban_id={douban_id} "
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

        # ② 爬详情页（最多 3 次重试）
        detail_url = SUBJECT_PAGE_BASE.format(douban_id=douban_id)
        html = ""
        for attempt in range(3):
            await self._emit_stage(task_str, f"📡 正在请求详情页 (第{attempt+1}次): {detail_url}")
            html, ok, snapshot = await self._browser.fetch_page(detail_url, identity)
            if ok:
                await self._emit_stage(task_str, f"✅ 详情页获取成功")
                break
            logger.debug(f"[movie_scrape] task={task_id} 详情页 attempt={attempt+1} 失败: {snapshot.get('error')}")
        else:
            raise FetcherError(f"详情页 3 次重试全失败: douban_id={douban_id}")

        await self._emit_stage(task_str, "📝 正在解析电影详情...")
        detail = parse_movie_detail(html)
        detail["douban_id"] = douban_id

        # ③ 写入电影基础信息（原子事务：movies + genres + regions + ratings）
        await self._emit_stage(task_str, "💾 正在写入电影基础信息...")
        movie_id = await storage.save_movie_basic(self._movie_service, detail)
        if not movie_id:
            raise ValueError(f"电影基础信息写入失败: douban_id={douban_id}")

        # ④ 更新 douban_ids（标记已认领 + 已爬取完成）
        raw = self._movie_service.db.raw_mysql()
        await raw.execute_update(
            "UPDATE douban_ids SET is_acquired=1, is_scraped=1, "
            "acquired_at=NOW(), task_id=%s "
            "WHERE douban_id=%s",
            (task_id, douban_id),
        )

        # ⑤ 自动注入 director_crawl 子任务（继承父任务 admin_id，独立 task_history）
        await self._emit_stage(task_str, "📋 创建演职人员爬取子任务...")
        await self._inject_director_subtask(data, movie_id)
        await self._emit_stage(task_str, "✅ 电影基础信息入库完成，子任务已入队")

        if cookie_id and self._identity_manager is not None:
            try:
                await self._identity_manager._cookie_manager.report_success(cookie_id)
            except Exception:
                pass

    async def _handle_movie_detail_crawl(self, data: dict) -> None:
        douban_id = data["douban_id"]
        title = data.get("title", "")
        task_id = data.get("id")

        logger.info(f"[movie_detail] task={task_id} douban_id={douban_id} title='{title}'")

        CELEB_PAGE_BASE = "https://movie.douban.com/subject/{douban_id}/celebrities"

        page_url = SUBJECT_PAGE_BASE.format(douban_id=douban_id)
        html = await self._browser.fetch(page_url)
        detail = parse_movie_detail(html)
        detail["douban_id"] = douban_id

        try:
            celeb_url = CELEB_PAGE_BASE.format(douban_id=douban_id)
            celeb_html = await self._browser.fetch(celeb_url)
            detail["crew"] = parse_personnel(celeb_html)
        except Exception as e:
            logger.error(f"[movie_detail] task={task_id} douban_id={douban_id} 参演人员获取失败: {e}")
            detail["crew"] = []

        if self._movie_service is None:
            logger.warning(f"[movie_detail] task={task_id} MovieService 未注入，跳过写入")
            return

        stats = await save_movies(self._movie_service, [detail])
        logger.info(
            f"[movie_detail] task={task_id} douban_id={douban_id} 完成: "
            f"created={stats['created']} skipped={stats['skipped']}"
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

        cfg = crawler_config

        # 1. 查询已采集数量，计算偏移量（顺延模式）
        count_result = await raw.execute_query(
            "SELECT COUNT(1) as cnt FROM movie_review WHERE movie_id=%s",
            (movie_id,),
        )
        existing_count = count_result[0].get("cnt", 0) if count_result else 0
        start = existing_count
        logger.info(
            f"[review_crawl] task={task_id} movie_id={movie_id} 已有 {existing_count} 条, "
            f"将从 offset={start} 顺延取 {cfg.review_crawl_max_new} 条"
        )

        # 2. 睡眠 45s，反反爬
        logger.info(f"[review_crawl] 等待 {cfg.review_crawl_pre_sleep}s（反反爬）...")
        await asyncio.sleep(cfg.review_crawl_pre_sleep)

        # 3. 翻页爬取（最多两次翻页：当前页 + 下一页，每页20条中取够5条）
        total_inserted = 0
        seen_rids = set()
        offset = start
        page_count = 0

        while total_inserted < cfg.review_crawl_max_new and page_count < 2:
            page_url = f"{REVIEW_LIST_BASE.format(douban_id=douban_id)}?sort=hotest&start={offset}"
            logger.info(f"[review_crawl] 第{page_count+1}次翻页: {page_url}")
            page_count += 1

            try:
                if identity:
                    html, ok, _ = await self._browser.fetch_page(page_url, identity)
                    if not ok:
                        raise FetcherError(f"列表页请求失败: {page_url}")
                else:
                    html = await self._browser.fetch(page_url)
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
        长评正文爬取 — 单条模式。

        输入：{review_id, movie_id?, douban_id|subject_id, title, author, date, useful_count, cookie_id?, proxy_key?}
        副作用：
            BrowserFetcher 爬取详情页 → parse → MongoDB upsert → UPDATE movie_review status='done'/'failed'
            → 检查是否触发 AI 总结

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
        cookie_id = data.get("cookie_id", "")
        proxy_key = data.get("proxy_key", "")

        logger.info(
            f"[review_body_crawl] task={task_id} review_id={review_id} "
            f"douban_id={douban_id} title='{title}' author='{author}'"
        )

        if self._movie_service is None:
            raise RuntimeError("MovieService 未注入，无法访问 movie_review 表")

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
            await self._check_and_trigger_ai_summary(movie_id)
            return

        # ① 爬取长评详情页（增强版：等待加载 + 展开全文）
        try:
            async with self._browser_sem:
                detail_url = REVIEW_DETAIL_URL.format(review_id=review_id)
                html = await self._browser.fetch_review_body(detail_url, identity=identity)
                if not html or len(html) < 500:
                    raise RuntimeError(f"长评页面内容过短: review_id={review_id}")

        except Exception as e:
            logger.error(f"[review_body_crawl] review_id={review_id} 页面请求失败: {e}")
            await raw.execute_update(
                "UPDATE movie_review SET status='failed' WHERE review_id=%s",
                (review_id,),
            )
            raise

        # ② 解析内容
        parsed = parse_review_full(html)
        parsed["review_id"] = review_id
        parsed["title"] = title
        parsed["author"] = author
        parsed["date"] = date_str
        parsed["useful_count"] = useful_count
        if not parsed.get("votes"):
            parsed["votes"] = str(useful_count)

        # ③ 写入 MongoDB + 更新 MySQL 状态（先写 Mongo，成功再改 MySQL）
        saved = await save_reviews(douban_id, [parsed], movie_id=movie_id)
        if saved > 0:
            await raw.execute_update(
                "UPDATE movie_review SET status='done' WHERE review_id=%s",
                (review_id,),
            )
            logger.info(f"[review_body_crawl] task={task_id} review_id={review_id} 完成")
            # ④ 检查是否触发 AI 总结
            await self._check_and_trigger_ai_summary(movie_id)
        else:
            logger.error(f"[review_body_crawl] review_id={review_id} MongoDB 写入失败，保持 pending")
            raise RuntimeError(f"长评 MongoDB 写入失败: review_id={review_id}")

        if cookie_id and self._identity_manager is not None:
            try:
                await self._identity_manager._cookie_manager.report_success(cookie_id)
            except Exception:
                pass

    async def _handle_comment_crawl(self, data: dict) -> None:
        task_id = data.get("id")
        douban_id = data.get("douban_id") or data.get("subject_id", "")
        cookie_id = data.get("cookie_id", "")
        proxy_key = data.get("proxy_key", "")

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
        logger.info(f"[comment_crawl] task={task_id} douban_id={douban_id} movie_id={movie_id} 开始抓取 {pages} 页短评")

        all_comments = []
        seen_cids = set()

        for page_num in range(pages):
            start = page_num * crawler_config.page_size
            page_url = (
                f"{COMMENT_LIST_BASE.format(douban_id=douban_id)}"
                f"?start={start}&limit={crawler_config.page_size}&status=P"
            )

            try:
                if identity:
                    html, ok, _ = await self._browser.fetch_page(page_url, identity)
                    if not ok:
                        raise FetcherError(f"短评列表页请求失败: {page_url}")
                else:
                    html = await self._browser.fetch(page_url)
                page_comments = parse_comments(html)
                new_count = 0
                for c in page_comments:
                    cid = c.get("comment_id", "")
                    if cid and cid not in seen_cids:
                        seen_cids.add(cid)
                        all_comments.append(c)
                        new_count += 1
                logger.info(
                    f"[comment_crawl] task={task_id} 第{page_num+1}/{pages}页: "
                    f"解析{len(page_comments)}条, 新增{new_count}条"
                )
            except Exception as e:
                logger.error(f"[comment_crawl] task={task_id} 第{page_num+1}/{pages}页失败: {e}")
                await self._report_item_failure(
                    task_data=data,
                    kind=classify_item_error(e),
                    reason=str(e),
                    item_douban_id=f"page_{page_num+1}",
                    item_title=f"短评第{page_num+1}页",
                )
                continue

        if all_comments:
            saved = await save_comments(douban_id or "", all_comments, movie_id=movie_id)
            logger.info(
                f"[comment_crawl] task={task_id} 完成: "
                f"{len(all_comments)}条, 入库{saved}条"
            )
            if saved > 0 and movie_id:
                from db.redis import redis_delete
                await redis_delete(f"wordcloud:movie:{movie_id}")
                logger.debug(f"[comment_crawl] 已清除词云缓存: movie_id={movie_id}")

            if cookie_id and self._identity_manager is not None:
                try:
                    await self._identity_manager._cookie_manager.report_success(cookie_id)
                except Exception:
                    pass
        else:
            logger.warning(f"[comment_crawl] task={task_id} 无可用短评")

    async def _handle_director_crawl(self, data: dict) -> None:
        """
        演职人员补爬任务（P0 解耦后独立调度）。

        输入：{type, douban_id, movie_id, admin_id?, ...}
        输出：无（成功返回，失败抛异常）
        副作用：BrowserFetcher 爬 celebrities 页 → save_crew（事务原子写入）
        """
        task_id = data.get("id")
        douban_id = data.get("douban_id", "")
        movie_id = data.get("movie_id")

        if not douban_id:
            raise ValueError("director_crawl 任务缺少 douban_id 字段")
        if not movie_id:
            raise ValueError("director_crawl 任务缺少 movie_id 字段")

        CELEB_PAGE_BASE = "https://movie.douban.com/subject/{douban_id}/celebrities"
        celeb_url = CELEB_PAGE_BASE.format(douban_id=douban_id)

        logger.info(f"[director_crawl] task={task_id} douban_id={douban_id} movie_id={movie_id}")

        if self._movie_service is None:
            raise RuntimeError("MovieService 未注入，无法写入数据库")

        # 爬取 celebrities 页
        task_str = json.dumps(data, ensure_ascii=False)
        await self._emit_stage(task_str, f"📡 正在请求演职人员页: {celeb_url}")
        html, ok, _ = await self._browser.fetch_page(celeb_url)
        if not ok:
            raise FetcherError(f"演职人员页获取失败: douban_id={douban_id}")

        # 解析全部角色类型（导演/演员/编剧/制片/美术/音乐/其他）
        crew = parse_personnel(html)
        if not crew:
            logger.warning(f"[director_crawl] task={task_id} 未提取到演职人员信息")
            return

        # 事务原子写入 people + movie_credits
        await self._emit_stage(task_str, f"💾 正在写入 {len(crew)} 名演职人员...")
        saved = await storage.save_crew(self._movie_service, movie_id, crew)
        logger.info(
            f"[director_crawl] task={task_id} 完成: "
            f"saved={saved}/{len(crew)} 种角色"
        )

    # ── 内部：子任务注入 ──

    async def _inject_director_subtask(self, parent_data: dict, movie_id: int) -> None:
        """
        movie_scrape_task 成功后自动创建 director_crawl 子任务。

        输入：
            parent_data: 父任务 JSON dict（含 admin_id）
            movie_id:    save_movie_basic 返回的电影 ID
        副作用：
            ZADD Redis ZSET + INSERT task_history（父任务 admin_id 为子任务归属人）
        """
        from utils.snowflake import generate_id
        import json as _json

        admin_id = parent_data.get("admin_id", 0)
        douban_id = parent_data.get("douban_id", "")
        parent_task_id = parent_data.get("id", 0)

        sub_task = {
            "id": generate_id(),
            "type": "director_crawl",
            "douban_id": douban_id,
            "movie_id": movie_id,
            "admin_id": admin_id,
            "parent_task_id": parent_task_id,
            "created_at": parent_data.get("created_at", 0),
        }
        sub_json = _json.dumps(sub_task, ensure_ascii=False)

        # 写入 Redis ZSET（限速队列）
        from config.puller_config import puller_config
        await self._movie_service.db.add_delayed_task_with_limit(
            task_json=sub_json,
            cooldown_seconds=puller_config.task_cooldown_seconds,
        )

        # 写入 task_history（归属父任务管理员）
        try:
            from services.task_history_service import _get_history_service
            await _get_history_service().create(
                task_id=sub_task["id"],
                admin_id=admin_id,
                task_type="director_crawl",
                task_params=sub_task,
                status="submitted",
            )
        except Exception:
            logger.exception("director_crawl 子任务 history 写入失败（不影响主流程）")

        logger.info(
            f"[movie_scrape] 自动创建子任务: director_crawl sub_id={sub_task['id']} "
            f"douban_id={douban_id} movie_id={movie_id} admin_id={admin_id}"
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
                await raw.execute_update(
                    "UPDATE review_summary SET status='failed', updated_at=NOW() WHERE movie_id=%s",
                    (movie_id,),
                )
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

        except Exception as e:
            logger.error(f"[AI总结-内联] movie_id={movie_id} 异常: {e}", exc_info=True)
            try:
                await raw.execute_update(
                    "UPDATE review_summary SET status='failed', updated_at=NOW() WHERE movie_id=%s",
                    (movie_id,),
                )
            except Exception:
                pass

    async def _check_and_trigger_ai_summary(self, movie_id: int) -> None:
        """
        检查电影已完成长评数量，达到阈值则触发AI总结任务（幂等，同一电影只触发一次）。
        v3: 阈值从20改为配置项 ai_summary_min_reviews（默认5）。
        
        输入：movie_id: 本地电影ID
        副作用：推送ai_review_summary任务到队列，写入task_history
        """
        if self._movie_service is None:
            return
        
        cfg = crawler_config
        raw = self._movie_service.db.raw_mysql()
        try:
            # 1. 先检查是否已经生成过总结，防止重复触发
            summary_check = await raw.execute_query(
                "SELECT 1 FROM review_summary WHERE movie_id=%s LIMIT 1",
                (movie_id,),
            )
            if summary_check and len(summary_check) > 0:
                logger.debug(f"[AI总结] movie_id={movie_id} 已生成过总结，跳过触发")
                return

            # 2. 统计已完成的长评数量
            count_result = await raw.execute_query(
                "SELECT COUNT(1) as cnt FROM movie_review WHERE movie_id=%s AND status='done'",
                (movie_id,),
            )
            done_count = count_result[0].get("cnt", 0) if count_result else 0
            
            logger.debug(f"[AI总结] movie_id={movie_id} 已完成长评数量: {done_count}/{cfg.ai_summary_min_reviews}")
            
            # 3. 达到阈值则推送任务
            if done_count >= cfg.ai_summary_min_reviews:
                from utils.snowflake import generate_id
                import json as _json
                from config.puller_config import puller_config
                
                summary_task = {
                    "id": generate_id(),
                    "type": "ai_review_summary",
                    "movie_id": movie_id,
                    "admin_id": 0,
                    "created_at": int(time.time()),
                }
                sub_json = _json.dumps(summary_task, ensure_ascii=False)

                # 写入 Redis ZSET（限速队列）
                await self._movie_service.db.add_delayed_task_with_limit(
                    task_json=sub_json,
                    cooldown_seconds=puller_config.task_cooldown_seconds,
                )

                # 写入 task_history
                try:
                    from services.task_history_service import _get_history_service
                    await _get_history_service().create(
                        task_id=summary_task["id"],
                        admin_id=0,
                        task_type="ai_review_summary",
                        task_params=summary_task,
                        status="submitted",
                    )
                except Exception:
                    logger.exception("AI总结任务 history 写入失败（不影响主流程）")

                logger.info(f"[AI总结] movie_id={movie_id} 已达20条长评，总结任务已推送 task_id={summary_task['id']}")
        
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
        
        if self._movie_service is None:
            raise RuntimeError("MovieService 未注入，无法访问数据库")
        
        raw = self._movie_service.db.raw_mysql()
        from services.review_service import _get_review_service
        review_svc = _get_review_service()
        
        try:
            # 1. 幂等检查：已生成过则直接返回
            existing = await raw.execute_query(
                "SELECT id FROM review_summary WHERE movie_id=%s LIMIT 1",
                (movie_id,),
            )
            if existing and len(existing) > 0:
                logger.info(f"[AI总结] movie_id={movie_id} 已存在总结，跳过处理")
                return
            
            # 2. 先插入一条pending记录，防止重复任务并发处理
            await raw.execute_update(
                "INSERT INTO review_summary (movie_id, status, created_at, updated_at) "
                "VALUES (%s, 'pending', NOW(), NOW()) "
                "ON DUPLICATE KEY UPDATE status='pending', updated_at=NOW()",
                (movie_id,),
            )
            
            # 3. 拉取该电影最高赞的20条长评全文
            reviews = await review_svc.get_top_reviews_by_movie_id(movie_id, limit=20)
            if not reviews or len(reviews) < 10:
                # 长评数量不足10条，暂时不生成，标记为pending，可后续手动触发
                logger.warning(f"[AI总结] movie_id={movie_id} 有效长评数量不足10条，暂不生成")
                await raw.execute_update(
                    "UPDATE review_summary SET status='pending' WHERE movie_id=%s",
                    (movie_id,),
                )
                return
            
            logger.info(f"[AI总结] 拉取到{len(reviews)}条有效长评，开始生成总结")
            
            # 4. 调用AI生成总结
            from utils.ai_client import get_ai_client
            ai_client = get_ai_client()
            result = await ai_client.generate_review_summary(reviews)
            
            if not result:
                # 生成失败，标记为failed
                await raw.execute_update(
                    "UPDATE review_summary SET status='failed', updated_at=NOW() WHERE movie_id=%s",
                    (movie_id,),
                )
                raise RuntimeError(f"AI总结生成失败 movie_id={movie_id}")
            
            # 5. 保存结果到数据库
            full_summary = result.get("full_summary", "")
            tags = json.dumps(result.get("tags", []), ensure_ascii=False)
            
            await raw.execute_update(
                "UPDATE review_summary "
                "SET full_summary=%s, review_tags=%s, status='done', updated_at=NOW() "
                "WHERE movie_id=%s",
                (full_summary, tags, movie_id),
            )
            
            logger.info(f"[AI总结] movie_id={movie_id} 生成成功，已保存到数据库")
            
        except Exception as e:
            logger.error(f"[AI总结] 处理失败 task_id={task_id}, movie_id={movie_id}: {e}", exc_info=True)
            # 标记为失败状态
            try:
                await raw.execute_update(
                    "UPDATE review_summary SET status='failed', updated_at=NOW() WHERE movie_id=%s",
                    (movie_id,),
                )
            except Exception:
                pass
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
            task_json = json.dumps(task_data, ensure_ascii=False)

            await svc.insert_failure(
                task=task_json,
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
