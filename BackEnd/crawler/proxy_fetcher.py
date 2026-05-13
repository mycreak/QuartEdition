"""
crawler/proxy_fetcher.py

代理供给源 — 从付费 IP 服务商 API 获取代理，验证后喂入 ProxyPool。

职责：
    1. 调用付费代理 API 获取代理列表
    2. 并发验证代理可用性
    3. 将可用代理喂入 ProxyPool

不负责：
    1. 代理池内部管理（由 proxy.py 负责）
    2. HTTP 请求封装（由 fetcher.py 负责）

v2 — 移除免费代理源（已全部不可用），仅保留付费 API 入口。
"""

import asyncio
import logging
import os

from crawler.proxy import ProxyPool, SourceType

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 10
DEFAULT_VERIFY_TIMEOUT = 5.0


async def fetch_from_paid_api(
    pool: ProxyPool,
    concurrency: int = DEFAULT_CONCURRENCY,
    verify_timeout: float = DEFAULT_VERIFY_TIMEOUT,
) -> dict:
    """
    从付费代理 API 导入代理。

    输入：
        pool:          ProxyPool 实例
        concurrency:   并发验证数
        verify_timeout: 单代理验证超时

    输出：{"fetched": N, "verified": M, "added": K}

    开发阶段行为：
        环境变量 PAID_PROXY_API_KEY 未设置 → 返回空，由调用方降级为直连

    生产阶段行为：
        从配置的付费 API 拉取代理列表 → 并发验证 → 喂入 ProxyPool
    """
    api_key = os.getenv("PAID_PROXY_API_KEY", "")
    if not api_key:
        return {"fetched": 0, "verified": 0, "added": 0}

    logger.info("fetch_from_paid_api: 开始从付费代理 API 拉取...")

    raw = await _fetch_paid_proxy_list(api_key)
    if not raw:
        logger.info("fetch_from_paid_api: 未获取到任何代理")
        return {"fetched": 0, "verified": 0, "added": 0}

    result = {"fetched": len(raw), "verified": 0, "added": 0}
    semaphore = asyncio.Semaphore(concurrency)

    async def _verify_and_add(host: str, port: int):
        nonlocal result
        async with semaphore:
            ok = await pool.verify_proxy(host, port, timeout=verify_timeout)
            if ok:
                result["verified"] += 1
                added = await pool.add_proxy(host, port, source=SourceType.ADMIN)
                if added:
                    result["added"] += 1

    tasks = [_verify_and_add(host, port) for host, port in raw]
    await asyncio.gather(*tasks)

    logger.info(
        f"fetch_from_paid_api: fetched={result['fetched']}, "
        f"verified={result['verified']}, added={result['added']}"
    )
    return result


async def _fetch_paid_proxy_list(api_key: str) -> list[tuple[str, int]]:
    """
    从付费代理 API 获取 IP 列表。

    输入：api_key — 服务商 API Key
    输出：[(host, port), ...]

    TODO: 接入实际付费 IP 服务商 API（如芝麻/快代理/神龙IP）
    示例请求格式（神龙IP）：
        GET http://api.shenlongip.com/ip?key={api_key}&protocol=2&mr=1&pattern=json&count=10
    示例返回：
        {"code":200,"msg":"ok","data":[{"ip":"1.2.3.4","port":8080}, ...]}
    """
    try:
        import aiohttp
    except ImportError:
        logger.error("aiohttp 未安装，无法获取付费代理")
        return []

    # 预留骨架，接入时替换 url 和解析逻辑
    url = os.getenv("PAID_PROXY_API_URL", "")
    if not url:
        logger.info("_fetch_paid_proxy_list: PAID_PROXY_API_URL 未配置")
        return []

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"付费代理 API 返回状态 {resp.status}")
                    return []
                data = await resp.json()
    except Exception as e:
        logger.warning(f"付费代理 API 请求失败: {e}")
        return []

    proxies = []
    for item in data.get("data", []):
        host = item.get("ip", "")
        port = item.get("port", 0)
        if host and port:
            proxies.append((host, port))

    logger.info(f"付费代理 API 获取到 {len(proxies)} 个代理")
    return proxies
