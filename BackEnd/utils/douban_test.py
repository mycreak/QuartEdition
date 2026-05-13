"""
utils/douban_test.py

豆瓣代理可用性测试工具 — 给定一个 IP，测试是否能爬取豆瓣。

用法（在文件底部 __main__ 块直接改参数运行）：
    python utils/douban_test.py
"""

import asyncio
import time


async def test_douban_proxy(host: str = None, port: int = None, timeout: int = 10) -> dict:
    """
    测试一个代理 IP 是否可用于爬取豆瓣。

    输入：
        host:    代理 IP，如 "47.96.12.38"。传 None 为直连模式
        port:    代理端口，如 3128
        timeout: 超时秒数，默认 10

    输出：dict
        {"ok": True/False, "status": 200/..., "elapsed": 1.2, "length": 12345}
    """
    import aiohttp

    url = "https://movie.douban.com/subject/1292052/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
    }
    kwargs = {"headers": headers, "timeout": aiohttp.ClientTimeout(total=timeout)}
    if host and port:
        kwargs["proxy"] = f"http://{host}:{port}"

    start = time.time()
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, **kwargs) as resp:
                body = await resp.text()
                elapsed = time.time() - start
                ok = resp.status == 200 and "检测到有异常请求" not in body
                return {
                    "ok": ok,
                    "status": resp.status,
                    "elapsed": round(elapsed, 2),
                    "length": len(body),
                }
    except Exception as e:
        return {
            "ok": False,
            "status": None,
            "elapsed": round(time.time() - start, 2),
            "length": 0,
            "error": str(e),
        }


async def main():
    # ─── 在这里填入你要测试的 IP（都为 None 则直连）───
    host = "139.159.118.14"
    port = 5678
    # ──────────────────────────────────────────────

    mode = f"{host}:{port}" if host else "直连"
    print(f"测试: {mode}")
    result = await test_douban_proxy(host, port)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
