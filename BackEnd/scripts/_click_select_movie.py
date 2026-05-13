"""选电影点击交互 — 观察点击前后 DOM 变化"""
import asyncio, sys
sys.path.insert(0, sys.path[0].replace("\\scripts", ""))
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()

        await page.goto("https://movie.douban.com/explore", wait_until="load", timeout=30000)
        print(f"页面标题: {await page.title()}")
        print(f"初始 <a> 标签数: {await page.locator('a').count()}")
        print(f"URL: {page.url}\n")

        # ── 点击前 ──
        print("=" * 55)
        print("【点击前】body 文字摘要")
        body_pre = await page.locator("body").inner_text()
        print(body_pre[:300].replace("\n", " │ "))

        # ── 点击 `选电影` ──
        print("\n" + "=" * 55)
        print("【点击 `选电影` 链接】")
        link = page.locator("a[href='https://movie.douban.com/explore']:has-text('选电影')")
        await link.click()
        await page.wait_for_timeout(1000)  # 等 1 秒让 AJAX 响应

        # ── 点击后 ──
        print(f"\nURL (未跳转): {page.url}")
        print(f"<a> 标签数: {await page.locator('a').count()}")
        print()

        body_post = await page.locator("body").inner_text()

        # 找变化：对比前后 body 文本
        pre_lines = set(body_pre.splitlines())
        post_lines = set(body_post.splitlines())
        new_lines = post_lines - pre_lines

        print(f"【点击后】新增文本行 ({len(new_lines)} 行):")
        for line in sorted(new_lines):
            line = line.strip()
            if line:
                print(f"  + {line[:80]}")

        # 顺便检查是否有新的卡片/列表出现
        print(f"\n【统计】")
        print(f"  a 标签: {await page.locator('a').count()}")
        print(f"  img 标签: {await page.locator('img').count()}")
        print(f"  div 标签: {await page.locator('div').count()}")

        # ── 定位 div.subject-list-main ──
        print("\n" + "=" * 55)
        print("【定位 div.subject-list-main】")
        subject_lists = page.locator("div.subject-list-main")
        count = await subject_lists.count()
        print(f"  匹配数量: {count}")

        if count > 0:
            for i in range(count):
                visible = await subject_lists.nth(i).is_visible()
                inner = (await subject_lists.nth(i).inner_text())[:400]
                print(f"  [{i}] visible={visible}")
                print(f"      内容: {inner.replace(chr(10), ' | ')[:300]}")
                print()
        else:
            print("  未找到 div.subject-list-main，尝试放宽搜索...")
            # 回退：找 class 含 subject-list 的 div
            fallback = page.locator("div[class*='subject-list']")
            fb_count = await fallback.count()
            print(f"  div[class*='subject-list'] 数量: {fb_count}")
            for i in range(min(fb_count, 3)):
                cls = await fallback.nth(i).get_attribute("class")
                visible = await fallback.nth(i).is_visible()
                inner = (await fallback.nth(i).inner_text())[:200]
                print(f"  [{i}] class='{cls}' visible={visible}")
                print(f"      {inner[:150]}")

        await page.close()
        await ctx.close()
        await browser.close()

asyncio.run(main())
