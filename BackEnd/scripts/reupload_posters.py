"""
reupload_posters.py

把 movies 表中所有豆瓣图床的封面重新爬取并转存到 TOS。

流程：
    1. 查 movies WHERE poster_url LIKE '%doubanio%' OR '%douban.com%'
    2. 对每部电影 Playwright 访问详情页 → parse_movie_detail 提取海报
    3. _mirror_poster 转存 TOS → UPDATE movies SET poster_url
    4. 每部电影间随机休眠 5~15s 防止反爬

用法：
    cd BackEnd
    python scripts/reupload_posters.py
"""

import asyncio
import logging
import random
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.mysql import init_mysql, close_mysql, execute_query, execute_update
from crawler.parser import parse_movie_detail
from crawler.storage import _mirror_poster
from utils.tos_client import init_tos_client, get_tos_client
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("reupload_posters")

SUBJECT_URL = "https://movie.douban.com/subject/{douban_id}/"
BATCH_SIZE = 50
SLEEP_MIN = 5
SLEEP_MAX = 15


def _random_ua() -> str:
    return random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ])


async def count_douban_posters() -> int:
    sql = (
        "SELECT COUNT(1) AS cnt FROM movies "
        "WHERE poster_url IS NOT NULL AND poster_url != '' "
        "AND (poster_url LIKE '%%doubanio%%' OR poster_url LIKE '%%douban.com%%')"
    )
    rows = await execute_query(sql)
    return rows[0]["cnt"] if rows else 0


async def fetch_douban_posters(offset: int, limit: int) -> list[dict]:
    sql = (
        "SELECT id, douban_id, poster_url FROM movies "
        "WHERE poster_url IS NOT NULL AND poster_url != '' "
        "AND (poster_url LIKE '%%doubanio%%' OR poster_url LIKE '%%douban.com%%') "
        "ORDER BY id ASC LIMIT %s OFFSET %s"
    )
    return await execute_query(sql, (limit, offset))


async def fetch_html(browser, url: str) -> str:
    ctx = await browser.new_context(
        user_agent=_random_ua(),
        viewport={"width": 1920, "height": 1080},
        ignore_https_errors=True,
    )
    page = None
    try:
        page = await ctx.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        await page.goto(url, wait_until="networkidle", timeout=30_000)

        if "sec.douban.com" in page.url:
            await page.wait_for_timeout(3000)

        await page.wait_for_timeout(random.randint(1000, 3000))

        try:
            btn = page.locator("#sub")
            if await btn.is_visible(timeout=2000):
                await btn.click(timeout=3000)
                await page.wait_for_timeout(random.randint(2000, 5000))
        except Exception:
            pass

        return await page.content()
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        try:
            await ctx.close()
        except Exception:
            pass


async def main():
    logger.info("=== 海报重新转存脚本启动 ===")

    await init_mysql()
    init_tos_client()
    tos = get_tos_client()

    if tos is None or not tos.enabled:
        logger.error("TOS 未启用，请检查 .env 中 TOS_ACCESS_KEY / TOS_SECRET_KEY 配置")
        await close_mysql()
        return

    total = await count_douban_posters()
    logger.info(f"共 {total} 部电影使用豆瓣图床封面")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        success = 0
        skipped = 0
        idx = 0
        offset = 0

        while offset < total:
            rows = await fetch_douban_posters(offset, BATCH_SIZE)
            if not rows:
                break

            for row in rows:
                idx += 1
                movie_id = row["id"]
                douban_id = row["douban_id"]
                old_url = row["poster_url"]
                logger.info(
                    f"[{idx}/{total}] movie_id={movie_id} "
                    f"douban_id={douban_id}"
                )

                try:
                    url = SUBJECT_URL.format(douban_id=douban_id)
                    html = await fetch_html(browser, url)
                    detail = parse_movie_detail(html)
                    poster_url = detail.get("poster_url", "")

                    if not poster_url:
                        logger.warning(
                            f"  ⚠️ 未提取到海报: douban_id={douban_id}"
                        )
                        skipped += 1
                    else:
                        new_url = await _mirror_poster(poster_url, douban_id)
                        if new_url and new_url != poster_url:
                            await execute_update(
                                "UPDATE movies SET poster_url = %s WHERE id = %s",
                                (new_url, movie_id),
                            )
                            logger.info(
                                f"  ✅ TOS 转存成功: {new_url[:80]}..."
                            )
                            success += 1
                        elif new_url:
                            logger.info(
                                f"  ℹ️ 已是 TOS 链接，跳过"
                            )
                            skipped += 1
                        else:
                            logger.warning(
                                f"  ❌ TOS 转存失败，保留原链接"
                            )
                            skipped += 1

                except Exception as e:
                    logger.error(f"  ❌ 处理失败: {e}")
                    skipped += 1

                sleep_s = random.uniform(SLEEP_MIN, SLEEP_MAX)
                logger.debug(f"  休眠 {sleep_s:.1f}s...")
                await asyncio.sleep(sleep_s)

            offset += len(rows)

        await browser.close()

    logger.info(f"=== 完成: 成功={success} 跳过={skipped} 总计={total} ===")
    await close_mysql()


if __name__ == "__main__":
    asyncio.run(main())
