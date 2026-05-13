import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from pathlib import Path
from crawler.fetcher import Fetcher, FetcherError

OUTPUT = Path(__file__).parent.parent / "data" / "douban_sample.html"

async def main():
    fetcher = Fetcher(
        proxy_pool=None,
        timeout=15,
        cookies={"bid": "UAZmWwgAFrQ"},
    )
    url = "https://movie.douban.com/subject/1292052/"
    print(f"抓取: {url}")
    try:
        html = await fetcher.fetch(url)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(html, encoding="utf-8")
        print(f"OK → {OUTPUT} ({len(html):,} 字符)")

        if "载入中" in html:
            print("⚠️ 仍然返回验证页，Cookie 可能已过期或格式不对")
        else:
            print("✅ 正常电影页面")

    except FetcherError as e:
        print(f"失败: {e}")

asyncio.run(main())
