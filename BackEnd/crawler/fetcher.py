"""
crawler/fetcher.py

核心下载器 — 双引擎架构。

BrowserFetcher (Playwright):
    用于受 SHA-512 保护的 HTML 页面（详情页、评论列表、短评列表）。
    networkidle + 条件 3s 等待自动绕过反爬。

ApiFetcher (aiohttp):
    用于 JSON API 和非受限页面（电影列表 API、评论正文 API、探索页）。
    轻量异步 HTTP 客户端，支持 Cookie 注入和 gzip/brotli 解压。

职责：
    1. 下载目标页面/数据
    2. 代理轮换 + 状态上报（浏览器/API 通用）
    3. 资源释放（finally 保证）

不负责：
    1. 代理池管理（由 proxy.py 负责）
    2. HTML 解析（由 parser.py 负责）
    3. 浏览器生命周期（由 app.py / BrowserPool 负责）
"""

import asyncio
import gzip
import json
import logging
import time as _time
from typing import Optional, Union

import aiohttp
from playwright.async_api import Browser, TimeoutError as PlaywrightTimeoutError

import random

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _random_user_agent() -> str:
    """从 UA 池随机选取 User-Agent，降低浏览器指纹识别风险。"""
    return random.choice(_UA_POOL)

from crawler.proxy import Proxy, ProxyPool

logger = logging.getLogger(__name__)

DOUBAN_ABUSE_MARKER = "检测到有异常请求"


def _build_proxy_config(proxy: Proxy) -> dict:
    """
    根据 Proxy 对象构建 Playwright 的 proxy 参数字典。

    输入：Proxy 对象
    输出：{server, username?, password?}
    """
    config = {"server": f"http://{proxy.host}:{proxy.port}"}
    if proxy.username:
        config["username"] = proxy.username
    if proxy.password:
        config["password"] = proxy.password
    return config


class FetcherError(Exception):
    """爬取失败 — 所有方式（代理 / 直连）均不可用。"""

    def __init__(self, message: str, attempts: int = 0):
        super().__init__(message)
        self.attempts = attempts


class BrowserFetcher:
    """
    Playwright 浏览器页面下载器。

    每个 fetch() 调用创建一个独立的浏览器上下文（BrowserContext），
    在上下文中注入代理（如有），创建页面，导航到目标 URL，
    获取完整 HTML 后立即释放页面和上下文。

    崩溃自愈：
        _do_fetch 中检测到浏览器进程崩溃（browser.is_connected() == False），
        自动重启浏览器进程，重新注入 self.browser。
        asyncio.Lock 保证多个 Worker 同时检测到崩溃时只有第一个重启。

    使用方式：
        browser = await p.chromium.launch(headless=True)
        fetcher = BrowserFetcher(browser=browser, playwright=p, proxy_pool=pool)
        html = await fetcher.fetch("https://movie.douban.com/subject/1292052/")

    资源保证：
        page 和 context 在 finally 中关闭，无论成功还是失败。

    代理注入：
        通过 browser.new_context(proxy={"server": "http://host:port"})。
        Playwright 的 proxy 参数支持 HTTP/HTTPS 代理协议。
        代理失败报告时机：context 已关闭后（避免 context 泄漏导致的资源累积）。
    """

    def __init__(
        self,
        browser: Browser,
        playwright=None,
        proxy_pool: Optional[ProxyPool] = None,
        storage_state: Optional[str] = None,
        timeout: int = 15,
        max_retries: int = 3,
        direct_fallback: bool = True,
    ):
        """
        Args:
            browser:         Playwright Chromium 浏览器实例（由上层创建并注入）
            playwright:      Playwright 入口对象（用于重启浏览器）
            proxy_pool:      代理池实例，None 表示永远直连
            storage_state:   Playwright storage state — 文件路径(str) 或 {cookies, origins}(dict)
                             传给 new_context(storage_state=...) 自动恢复登录态
            timeout:         页面导航超时（秒）
            max_retries:     最多换几次代理
            direct_fallback: 代理全失败后是否直连兜底
        """
        self.browser = browser
        self._playwright = playwright
        self.proxy_pool = proxy_pool
        self.storage_state = storage_state
        self.timeout = timeout * 1000  # Playwright 使用毫秒
        self.max_retries = max_retries
        self.direct_fallback = direct_fallback
        self._restart_lock = asyncio.Lock()

    async def _restart_browser(self):
        """
        自动重启浏览器进程（带锁，防并发重入）。

        输入：无
        输出：无
        副作用：
            1. 关闭旧浏览器
            2. 启动新浏览器
            3. 重新注入 self.browser
            4. 日志记录重启事件
        """
        async with self._restart_lock:
            if self.browser.is_connected():
                return

            logger.warning("检测到浏览器进程崩溃，正在自动重启...")
            try:
                await self.browser.close()
            except Exception:
                pass

            if self._playwright is None:
                raise RuntimeError("BrowserFetcher 没有 playwright 引用，无法重启浏览器")

            self.browser = await self._playwright.chromium.launch(headless=True)
            logger.info("浏览器已自动重启完成")

    async def fetch(self, url: str) -> str:
        """
        下载指定 URL 的 HTML（v4 简化版：不再内部做代理轮换+直连兜底）。

        代理/Cookie 由上层通过 fetch_page(url, identity) 或 fetch_review_body(url, identity) 精确指定。
        本方法仅用于游客/无代理场景，单次直连请求。

        输入：
            url: 目标页面 URL
        输出：
            HTML 文本字符串
        异常：
            FetcherError — 直连失败
        """
        html, ok = await self._fetch_direct(url)
        if ok:
            return html
        raise FetcherError(f"直连返回异常: {url}")

    async def _fetch_direct(self, url: str) -> tuple[str, bool]:
        """
        直连获取页面（不通过代理）。

        输入：
            url: 目标 URL
        输出：
            (html, ok)
        副作用：
            创建/关闭 browser context 和 page
        """
        return await self._do_fetch(url, proxy_config=None)

    async def fetch_page(
        self,
        url: str,
        identity=None,
    ) -> tuple[str, bool, dict]:
        """
        用指定的身份下载 HTML — P0 新增接口。

        与旧版 fetch() 的区别：
            - 代理和 Cookie 由外部传入的 identity 决定，不在 Fetcher 内部选取
            - 不做重试（重试由调用方自行控制）
            - 返回三元组 (html, ok, snapshot)，调用方可不依赖异常流判断成功/失败

        输入：
            url:      目标页面 URL
            identity: Identity 实例（None=游客直连，无 Cookie 无代理）
        输出：
            (html, ok, snapshot)
            snapshot = {url, cookie_id, proxy_key, html_preview, error, timestamp}

        副作用：
            创建/关闭 browser context 和 page（在 finally 中确保释放）
        """
        cookie_id = ""
        proxy_key = ""
        storage_state = None
        proxy_config = None

        if identity is not None:
            if not hasattr(identity, "cookie_id"):
                import traceback
                logger.warning(
                    f"fetch_page 收到非法的 identity 对象（已降级为游客）: "
                    f"type={type(identity).__name__} "
                    f"module={getattr(identity, '__name__', 'N/A')} "
                    f"url={url}"
                )
                logger.warning(
                    f"fetch_page 非法 identity 调用栈:\n"
                    + "".join(traceback.format_stack()[-8:-1])
                )
                identity = None
            else:
                cookie_id = identity.cookie_id
                proxy_key = identity.proxy_key
                storage_state = identity.storage_state or None
                proxy_config = identity.proxy_config or None

        snapshot = {
            "url": url,
            "cookie_id": cookie_id,
            "proxy_key": proxy_key,
            "html_preview": "",
            "error": "",
            "timestamp": _time.time(),
        }

        try:
            html, ok = await self._do_fetch(
                url, proxy_config=proxy_config, storage_state=storage_state,
            )
            snapshot["html_preview"] = html[:500] if html else ""
            if not ok:
                snapshot["error"] = "页面异常（空内容或反爬标记）" if html else "空响应"
            return html, ok, snapshot
        except Exception as e:
            snapshot["error"] = str(e)
            logger.debug(f"fetch_page 失败: url={url} cookie={cookie_id} proxy={proxy_key} err={e}")
            return "", False, snapshot

    async def _do_fetch(
        self,
        url: str,
        proxy_config: Optional[dict],
        storage_state=None,
    ) -> tuple[str, bool]:
        """
        执行单次浏览器页面导航并返回 HTML。

        输入：
            url:           导航目标 URL
            proxy_config:  Playwright proxy 参数，如 {"server": "http://1.2.3.4:8080"}
                           None 表示直连
            storage_state: Playwright storage_state dict，None=使用 self.storage_state
        输出：
            (html, ok)
            html — HTTP 响应正文（page.content()）
            ok   — True 表示页面正常加载（非空白、非反爬挑战页）

        资源管理（关键）：
            context 和 page 在 finally 块中关闭。
            这是资源泄漏防护的核心点 — Playwright 的 BrowserContext
            不关闭会累积在浏览器实例中，导致内存持续增长。

        异常处理（边界条件）：
            PlaywrightTimeoutError — 页面导航超时（目标站太慢或代理不可达）
            此时 page.content() 可能返回部分 HTML，标记为失败但上报代理

        豆瓣反爬策略（SHA-512 挑战）：
            networkidle 等待浏览器自动完成 JS 计算 + 表单提交 + 重定向。
            实测 networkidle 后 wait 3s 即可获得完整 HTML（压缩前需要 10s）。
            如果未触发挑战则不必等待（如 httpbin 等非豆瓣站点）。
        """
        context = None
        page = None
        try:
            context_kwargs = {
                "proxy": proxy_config,
                "ignore_https_errors": True,
                "user_agent": _random_user_agent(),
                "viewport": {"width": 1920, "height": 1080},
            }
            effective_storage = storage_state if storage_state is not None else self.storage_state
            if effective_storage:
                context_kwargs["storage_state"] = effective_storage
            context = await self.browser.new_context(**context_kwargs)
            page = await context.new_page()
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            await page.goto(url, timeout=self.timeout, wait_until="networkidle")

            if "sec.douban.com" in page.url:
                await page.wait_for_timeout(3000)

            await self._simulate_human_browsing(page)

            html = await page.content()

            if not html or len(html) < 200:
                return html, False
            if DOUBAN_ABUSE_MARKER in html:
                return html, False
            return html, True

        except PlaywrightTimeoutError:
            html = ""
            if page is not None:
                try:
                    html = await page.content()
                except Exception:
                    pass
            return html, False

        except asyncio.CancelledError:
            raise
        except Exception:
            if not self.browser.is_connected():
                await self._restart_browser()
            return "", False

        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass

    async def _simulate_human_browsing(self, page) -> None:
        """
        模拟人类浏览行为：随机滚动 + 随机等待 + 豆瓣验证按钮点击。

        目的：
            1. 触发懒加载内容（滚动后新 DOM 被渲染）
            2. 发出类人行为信号，降低反爬检测风险
            3. 自动点击豆瓣验证按钮 #sub

        调用时机：_do_fetch 内部，networkidle + SHA-512 等待之后，page.content() 之前。
        失败不抛异常，不影响主流程。
        """
        try:
            # 1. 随机初始等待（模拟打开页面后阅读 1~3 秒）
            await page.wait_for_timeout(int(random.uniform(1.0, 3.0) * 1000))

            # 2. 检测并点击豆瓣验证按钮（如果出现）
            try:
                btn = page.locator("#sub")
                if await btn.is_visible(timeout=2000):
                    await btn.click(timeout=3000)
                    await page.wait_for_timeout(int(random.uniform(2.0, 5.0) * 1000))
            except Exception:
                pass

            # 3. 向下滚动到底部（smooth 行为更像真人）
            await page.evaluate(
                "window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})"
            )
            await page.wait_for_timeout(int(random.uniform(1.5, 3.0) * 1000))

            # 4. 向上回滚一段（模拟回看）
            await page.evaluate(f"window.scrollBy(0, -{random.randint(400, 900)})")
            await page.wait_for_timeout(int(random.uniform(0.8, 1.8) * 1000))

            # 5. 再向上回滚一段
            await page.evaluate(f"window.scrollBy(0, -{random.randint(200, 600)})")
            await page.wait_for_timeout(int(random.uniform(0.5, 1.5) * 1000))

            # 6. 向下滚回中间位置（停在页面中间而非底部）
            await page.evaluate(f"window.scrollBy(0, {random.randint(200, 500)})")
            await page.wait_for_timeout(int(random.uniform(0.5, 1.0) * 1000))

        except Exception:
            pass

    async def fetch_review_body(self, url: str, identity=None) -> str:
        """
        专用于长评详情页的获取（v3 增强版）。

        支持两种代理模式：
            - identity 非空 → 使用精确的 cookie + proxy（不走池轮转）
            - identity 为空 → ProxyPool 代理轮转（与 fetch() 一致）

        游客模式（无 Cookie），除非 identity 携带 storage_state。

        增强行为：
            - 页面加载后等待动态内容渲染（15s）
            - 检测并点击豆瓣验证按钮 + 等待挑战完成（45s）
            - 上下滚动页面模拟人类浏览行为
            - 检测并点击"展开阅读全文"按钮
            - 最终等待内容完全加载后返回完整 HTML

        输入：url: 长评详情页 URL, identity: 可选的身份对象
        输出：完整 HTML 字符串
        异常：FetcherError — 页面请求失败
        副作用：
            创建/关闭 browser context 和 page（在 finally 中确保释放）
            对页面执行点击、滚动等交互操作
        """
        from config.crawler_config import crawler_config as cfg

        if identity is not None:
            proxy_config = identity.proxy_config or None
            return await self._do_fetch_review_body(
                url, proxy_config=proxy_config,
                storage_state=identity.storage_state or None, cfg=cfg,
            )

        # 无 identity → 单次直连（v4 简化：不再内部做代理轮换+直连兜底）
        return await self._fetch_review_body_direct(url, cfg)

    async def _fetch_review_body_direct(self, url: str, cfg) -> str:
        """直连获取长评（代理池为空或代理全部不可用时）。"""
        return await self._do_fetch_review_body(url, proxy_config=None, cfg=cfg)

    async def _do_fetch_review_body(self, url: str, proxy_config, cfg, storage_state=None) -> str:

        context = None
        page = None
        try:
            context_kwargs = {
                "proxy": proxy_config,
                "ignore_https_errors": True,
                "user_agent": _random_user_agent(),
                "viewport": {"width": 1920, "height": 1080},
            }
            if storage_state:
                context_kwargs["storage_state"] = storage_state
            context = await self.browser.new_context(**context_kwargs)
            page = await context.new_page()
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            await page.goto(url, timeout=self.timeout, wait_until="networkidle")

            # 1. 等待动态内容渲染
            logger.debug(f"[fetch_review_body] 等待 {cfg.review_body_page_wait}s 动态内容加载...")
            await page.wait_for_timeout(int(cfg.review_body_page_wait * 1000))

            # 2. 检测并点击豆瓣验证按钮
            try:
                await page.locator("#sub").click(timeout=3000)
                logger.debug(f"[fetch_review_body] 检测到验证按钮，已点击，等待 {cfg.review_body_verify_wait}s")
                await page.wait_for_timeout(int(cfg.review_body_verify_wait * 1000))
            except Exception:
                logger.debug("[fetch_review_body] 未触发验证")

            # 3. 上下滚动页面模拟人类浏览行为
            logger.debug("[fetch_review_body] 模拟页面滚动...")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(1000)
            await page.evaluate("window.scrollTo(0, document.querySelector('.review-content')?.offsetTop - 100 || 400)")
            await page.wait_for_timeout(500)

            # 4. 检测并点击"展开阅读全文"按钮
            try:
                expand_btn = await page.query_selector(".review-content .more")
                if expand_btn:
                    logger.debug("[fetch_review_body] 检测到展开按钮，点击...")
                    await expand_btn.click()
                    await page.wait_for_timeout(2000)
                else:
                    logger.debug("[fetch_review_body] 未检测到展开按钮")
            except Exception as e:
                logger.debug(f"[fetch_review_body] 展开按钮点击失败（不影响主流程）: {e}")

            # 5. 最终等待内容完全加载
            logger.debug(f"[fetch_review_body] 等待 {cfg.review_body_content_wait}s 内容完全加载...")
            await page.wait_for_timeout(int(cfg.review_body_content_wait * 1000))

            html = await page.content()

            if not html or len(html) < 200:
                raise FetcherError(f"长评页面内容过短或为空: {url}")
            if DOUBAN_ABUSE_MARKER in html:
                raise FetcherError(f"长评页面被反爬拦截: {url}")

            return html

        except PlaywrightTimeoutError:
            html = ""
            if page is not None:
                try:
                    html = await page.content()
                except Exception:
                    pass
            if not html or len(html) < 200:
                raise FetcherError(f"长评页面超时且无有效内容: {url}")
            return html

        except asyncio.CancelledError:
            raise
        except FetcherError:
            raise
        except Exception:
            if not self.browser.is_connected():
                await self._restart_browser()
            raise FetcherError(f"长评页面请求异常: {url}")

        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass


class ApiFetcher:
    """
    aiohttp 轻量下载器 — 用于 JSON API 和非受限页面。

    适用场景：
        - /j/chart/top_list  (电影列表 JSON API)
        - /j/review/{id}/full (长评正文 JSON API)
        - movie.douban.com/explore (非受限 HTML 页面)

    与 BrowserFetcher 的互补关系：
        ApiFetcher → JSON/简单页面（轻量，高并发，0.5s/次）
        BrowserFetcher → 受 SHA-512 保护的页面（重量，3.7s/次）

    使用方式：
        fetcher = ApiFetcher(cookies={"bid": "..."})
        data = await fetcher.fetch("https://movie.douban.com/j/chart/top_list?...")
        # data 是解析好的 dict/list

    压缩支持：
        自动处理 gzip 和 brotli (br) 压缩。aiohttp 自带 gzip 但 br 需要手动。
    """

    def __init__(
        self,
        cookies: Optional[dict] = None,
        timeout: int = 15,
        proxy_pool: Optional[ProxyPool] = None,
        max_retries: int = 3,
        direct_fallback: bool = True,
    ):
        """
        Args:
            cookies:        Cookie 字典，如 {"bid": "xxx", "ll": "118331"}
            timeout:        请求超时（秒）
            proxy_pool:     代理池实例，None 表示永远直连
            max_retries:    最多换几次代理
            direct_fallback: 代理全失败后是否直连兜底
        """
        self.cookies = cookies or {}
        self.timeout = timeout
        self.proxy_pool = proxy_pool
        self.max_retries = max_retries
        self.direct_fallback = direct_fallback
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """懒初始化 aiohttp session（复用连接）。"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookies=self.cookies,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                auto_decompress=False,
            )
        return self._session

    async def close(self):
        """关闭 aiohttp session。"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch(self, url: str) -> Union[dict, list, str]:
        """
        获取 URL 内容，自动判断 JSON 或 HTML（v4 简化版：单次直连）。

        代理由上层在任务配置阶段指定，本方法不再做内部代理轮换+直连兜底。

        输入：
            url: 目标 URL
        输出：
            dict | list — JSON API 响应
            str       — HTML 或其他文本
        异常：
            FetcherError — 请求失败
            json.JSONDecodeError — Content-Type 声明为 JSON 但解析失败
        """
        try:
            return await self._request(url, proxy=None)
        except asyncio.CancelledError:
            raise
        except FetcherError:
            raise
        except Exception as e:
            raise FetcherError(f"请求失败: {e}") from e

    async def _request(
        self,
        url: str,
        proxy: Optional[Proxy],
    ) -> Union[dict, list, str]:
        """
        执行单次 HTTP GET。

        输入：
            url:   目标 URL
            proxy: 代理对象，None 为直连
        输出：
            dict | list | str — 根据 Content-Type 自动选择
        """
        proxy_url = f"http://{proxy.host}:{proxy.port}" if proxy else None
        session = await self._get_session()

        async with session.get(url, proxy=proxy_url) as resp:
            raw = await resp.read()
            raw = self._decompress(raw, resp.headers.get("Content-Encoding", ""))

            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type or raw.strip().startswith((b"{", b"[")):
                return json.loads(raw.decode("utf-8"))

            return raw.decode("utf-8")

    @staticmethod
    def _decompress(raw: bytes, encoding: str) -> bytes:
        """
        解压响应体。

        输入：
            raw:      压缩的字节数据
            encoding: Content-Encoding 头的值
        输出：
            解压后的字节数据
        边界条件：
            - aiohttp auto_decompress 默认开启时会处理 gzip，
              但 br (brotli) 和某些边缘场景需要手动。
            - 由于我们复用 ClientSession，设置 auto_decompress=False
              由本方法统一处理，避免 session 级别配置冲突。
        """
        if "br" in encoding:
            import brotli
            return brotli.decompress(raw)
        if "gzip" in encoding:
            return gzip.decompress(raw)
        return raw
