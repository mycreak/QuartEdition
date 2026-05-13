"""
scripts/douban_login.py

豆瓣登录脚本 — headful 模式，手动完成验证码后保存登录态。

用法（本地 — 推荐用 save_cookies.py 更简单）：
    # 如果 Chrome 已经登录 → 推荐直接复制 Cookie 值
    cd BackEnd
    python scripts/save_cookies.py --dbcl2 "你的dbcl2值" --bid "你的bid值"

    # 如果 Chrome 没登录 → 用本脚本打开浏览器手动登录
    python scripts/douban_login.py

服务器部署流程：
    1. 本地运行本脚本，完成登录 → 生成 data/douban_storage.json
    2. 将文件传到服务器：
       scp BackEnd/data/douban_storage.json user@server:/path/to/QuartEdition/BackEnd/data/
    3. 启动 app.py → 自动加载并校验
    4. Cookie 过期时日志会明确提示，重新执行步骤 1-2

Cookie 生命周期：
    - dbcl2 有效期约 3-30 天（豆瓣未公开）
    - 启动时 app.py 会访问个人主页验证有效性
    - 过期后爬虫仍可运行（游客模式），但部分功能受限：
      不登录可用的功能有限

预期输出文件 data/douban_storage.json：
    {
      "saved_at": "2026-05-04T12:00:00",
      "verified": true,
      "playwright_state": {
        "cookies": [{name, value, domain, path, ...}, ...],
        "origins": [{...}]
      }
    }
"""

import asyncio
import json
import os
from datetime import datetime, timezone, timedelta

# 东八区时区常量
CST = timezone(timedelta(hours=8))

from playwright.async_api import async_playwright

STORAGE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "douban_storage.json")

LOGIN_URL = "https://accounts.douban.com/passport/login"
VERIFY_URL = "https://www.douban.com/mine"  # 个人主页，登录后才有内容，否则跳登录页

SUCCESS_COOKIE_NAME = "dbcl2"
WAIT_TIMEOUT = 120


def _has_login_cookie(storage_state: dict) -> bool:
    for c in storage_state.get("cookies", []):
        if c.get("name") == SUCCESS_COOKIE_NAME:
            return True
    return False


async def _verify_login_in_page(page) -> bool:
    """
    导航到个人主页验证登录态是否真的生效。

    输入：已注入 storage_state 的 page
    输出：True=已登录（页面白名单/确认属于用户）
    判断：URL 不包含 "login" → 确实是个人主页
    """
    try:
        await page.goto(VERIFY_URL, wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        current_url = page.url
        if "login" not in current_url and "passport" not in current_url:
            return True
    except Exception:
        pass
    return False


async def main():
    print("=" * 60)
    print("  豆瓣登录脚本 — headful 模式")
    print("=" * 60)
    print()
    print(f"  登录页: {LOGIN_URL}")
    print(f"  存储路径: {STORAGE_FILE}")
    print()
    print("  📋 操作步骤：")
    print("    1. 在打开的浏览器中输入手机号/邮箱 + 密码")
    print("    2. 完成滑块验证码")
    print("    3. 等待页面跳转（成功后窗口自动关闭）")
    print()
    print("  🖥️  服务器部署：")
    print("    本地登录后，将 douban_storage.json 传到服务器")
    print("    scp data/douban_storage.json user@server:BackEnd/data/")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        print("  🔗 正在打开登录页...")
        await page.goto(LOGIN_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        current_state = await context.storage_state()
        if _has_login_cookie(current_state):
            already_logged_in = await _verify_login_in_page(page)
            if already_logged_in:
                print("  ✅ 浏览器已有有效登录态，直接保存")
                await _save_state(context, verified=True)
                await browser.close()
                return
            else:
                print("  ⚠️  检测到旧 Cookie 但已失效，请重新登录")

        try:
            password_tab = page.locator("li.account-tab-account")
            if await password_tab.count() > 0:
                await password_tab.click()
                await page.wait_for_timeout(500)
                print("  ✅ 已切换到「密码登录」tab")
        except Exception:
            pass

        print()
        print(f"  ⏳ 请在浏览器中完成登录（最长 {WAIT_TIMEOUT} 秒）...")
        print()

        for elapsed in range(WAIT_TIMEOUT):
            await page.wait_for_timeout(1000)
            current_state = await context.storage_state()
            if _has_login_cookie(current_state):
                verified = await _verify_login_in_page(page)
                if verified:
                    print(f"  ✅ 登录成功！（耗时约 {elapsed + 1} 秒）")
                    await _save_state(context, verified=True)
                    await browser.close()
                    return

            if (elapsed + 1) % 10 == 0:
                print(f"  ... 已等待 {elapsed + 1} 秒，继续等待中")

        print(f"  ❌ 超时（{WAIT_TIMEOUT} 秒）未检测到有效登录态")
        await browser.close()


async def _save_state(context, verified: bool = False):
    """保存 storage_state 到文件，附带元数据。"""
    playwright_state = await context.storage_state()
    wrapper = {
        "saved_at": datetime.now(CST).isoformat(),
        "verified": verified,
        "playwright_state": playwright_state,
    }
    os.makedirs(os.path.dirname(STORAGE_FILE), exist_ok=True)
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(wrapper, f, ensure_ascii=False, indent=2)

    cookie_count = len(playwright_state.get("cookies", []))
    print(f"  💾 登录态已保存: {STORAGE_FILE}")
    print(f"     共 {cookie_count} 条 cookie")
    print(f"     保存时间: {wrapper['saved_at']}")
    if not verified:
        print(f"     ⚠️  未验证（请检查是否真正登录成功）")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
