"""
crawler/identity.py

爬取身份定义与管理。

Identity:
    由管理员在创建任务时显式指定 Cookie + IP 的不可变组合。
    设计理由：
        - 解耦 Fetcher：Fetcher 不再做身份选择，只负责"用给定的身份去请求"
        - 解耦 ProxyPool：Fetcher 不再持有 ProxyPool 引用
        - 全局替换友好：不同爬虫场景可定义不同的 Identity 构建方式

IdentityManager:
    聚合 CookieManager + ProxyPool，提供 resolve() 和 list_available()
    供 CrawlerEngine 和管理 API 使用。

约束检查在 resolve() 中完成：
    ① account.allowed_regions 是否包含 proxy.region
    ② proxy 是否当前可用（在 ProxyPool._alive 中）
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Identity:
    """
    爬取身份 — Cookie + IP 的不可变组合。

    字段：
        cookie_id:     账号 ID（如 "main"），空字符串 = 游客
        proxy_key:     代理 key（如 "1.2.3.4:3128"），空字符串 = 直连
        storage_state:  Playwright storage_state dict（来自 CookieManager.Account.storage_state）
        proxy_config:   Playwright proxy 参数 dict，如 {"server": "http://1.2.3.4:3128"}
    """
    cookie_id: str
    proxy_key: str
    storage_state: dict
    proxy_config: dict

    @property
    def is_guest(self) -> bool:
        """是否为游客模式（无 Cookie 且无代理）。"""
        return not self.cookie_id and not self.proxy_key


class IdentityManager:
    """
    身份管理器。

    职责：
        1. resolve(cookie_id, proxy_key) → Identity（含约束校验）
        2. 从 CookieManager 加载 storage_state
        3. 从 ProxyPool 查询代理并构造 proxy_config
        4. list_available() 供管理 API 展示可用身份组合
    """

    def __init__(self, cookie_manager, proxy_pool):
        """
        Args:
            cookie_manager: CookieManager 单例
            proxy_pool:     ProxyPool 单例
        """
        self._cookie_manager = cookie_manager
        self._proxy_pool = proxy_pool

    async def resolve(self, cookie_id: str, proxy_key: str) -> Identity:
        """
        根据指定的 cookie_id + proxy_key 构造 Identity。

        输入：
            cookie_id:  账号 ID，空字符串 = 游客
            proxy_key:  代理 key，空字符串 = 直连
        输出：
            Identity — 不可变，可直接传给 BrowserFetcher.fetch_page()

        校验：
            ① 如果 cookie_id 非空 → 查 CookieManager.Account
               → 如果 account.allowed_regions 不包含 proxy.region → ValueError
            ② 如果 proxy_key 非空 → 需要从 ProxyPool 查 proxy 是否 alive
               → 找到则构造 proxy_config，找不到则 Warning 但不报错（直连兜底）

        异常：
            ValueError — cookie_id 与 proxy.region 不匹配
        """
        storage_state = {}
        proxy_config = {}

        if cookie_id:
            account = self._cookie_manager.get(cookie_id)
            if account is None:
                raise ValueError(f"Cookie 账号不存在: {cookie_id}")
            storage_state = account.storage_state

        if proxy_key:
            proxy = self._find_proxy(proxy_key)
            if proxy is None:
                logger.warning(
                    f"代理不可用或不存在: {proxy_key}，降级为直连"
                )
            else:
                proxy_config = {"server": f"http://{proxy.host}:{proxy.port}"}
                # 约束检查：cookie 的 allowed_regions 必须包含 proxy.region
                if cookie_id:
                    account = self._cookie_manager.get(cookie_id)
                    if account and account.allowed_regions:
                        region = proxy.region if hasattr(proxy, 'region') else ""
                        if region and region not in account.allowed_regions:
                            raise ValueError(
                                f"Cookie '{cookie_id}' 不允许使用地区 '{region}' 的代理 "
                                f"(allowed_regions={account.allowed_regions})"
                            )

        return Identity(
            cookie_id=cookie_id,
            proxy_key=proxy_key,
            storage_state=storage_state,
            proxy_config=proxy_config,
        )

    def _find_proxy(self, proxy_key: str):
        """从 ProxyPool 中按 key 查找代理。"""
        return self._proxy_pool.get_by_key(proxy_key)

    def list_available(self) -> dict:
        """
        供管理 API — 返回当前所有可用身份组合的摘要。

        输出：
            {
                "cookies": [{id, label, region, state}, ...],
                "proxies": [{key, region, state}, ...],
            }
        """
        cookies = self._cookie_manager.list_all()
        proxies = self._proxy_pool.list_all()
        return {"cookies": cookies, "proxies": proxies}
