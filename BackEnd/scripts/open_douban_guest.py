"""
用 Playwright 打开豆瓣 — 游客模式 + 付费代理。

用法: python scripts/open_douban_guest.py [douban_id]
      默认 douban_id=25814705
      手动关闭浏览器窗口或 Ctrl+C 退出
"""
import sys
from playwright.sync_api import sync_playwright

# ── 付费代理（来自 .env PAID_PROXIES） ──
PROXY_HOST = "182.131.27.109"
PROXY_PORT = 2018
PROXY_USER = "ydl77404173"
PROXY_PASS = "TZKnlVbk"

PROXY_CONFIG = {
    "server": f"http://{PROXY_HOST}:{PROXY_PORT}",
    "username": PROXY_USER,
    "password": PROXY_PASS,
}

DOUBAN_ID = sys.argv[1] if len(sys.argv) > 1 else "25814705"
DOUBAN_URL = f"https://movie.douban.com/subject/{DOUBAN_ID}/"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

print(f"代理: {PROXY_USER}@{PROXY_HOST}:{PROXY_PORT}")
print(f"目标: {DOUBAN_URL}")
print("游客模式（无 Cookie），手动关闭浏览器窗口退出...")
print()

with sync_playwright() as p:
    browser = p.chromium.launch(
        proxy=PROXY_CONFIG,
        headless=False,
    )
    context = browser.new_context(
        user_agent=UA,
        viewport={"width": 1920, "height": 1080},
        ignore_https_errors=True,
        # 不传 storage_state = 游客模式
    )
    page = context.new_page()
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    """)
    page.goto(DOUBAN_URL, wait_until="networkidle")

    print("✅ 页面已加载，手动操作 / 关闭窗口退出")
    # 阻塞直到浏览器被手动关闭
    try:
        # page.pause() 会打开 Playwright Inspector，适合调试
        # 如果只想保持窗口开着，用无限循环 + 检查 browser 是否还连着
        while browser.is_connected():
            page.wait_for_timeout(1000)
    except KeyboardInterrupt:
        print("\nCtrl+C 退出")
    finally:
        if browser.is_connected():
            browser.close()
