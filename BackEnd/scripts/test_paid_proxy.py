"""
付费静态代理测试脚本。

测试流程：
    1. 访问 httpbin.org/ip → 确认出口 IP 为代理 IP（非本机）
    2. sleep 30s → 访问豆瓣电影详情页 → 验证页面能否正常加载
    3. 检测验证按钮 → 自动点击
    4. 保存 HTML 到本地

设计要点：
    - 静态代理 IP 固定，测试后不可频繁请求同一 IP（会被豆瓣封）
    - 两次请求之间 sleep 30s，模拟正常人类间隔
"""

import time
import os
from playwright.sync_api import sync_playwright

# ═══════════════════════════════════════════
# 配置（接入 IP 服务商后迁移到 .env）
# ═══════════════════════════════════════════
PROXY_HOST = "182.131.27.109"
PROXY_PORT = 2018
PROXY_USER = "ydl77404173"
PROXY_PASS = "TZKnlVbk"

PROXY_CONFIG = {
    "server": f"http://{PROXY_HOST}:{PROXY_PORT}",
    "username": PROXY_USER,
    "password": PROXY_PASS,
}

TEST_MOVIE_ID = "25814705"
TEST_DOUBAN_URL = f"https://movie.douban.com/subject/{TEST_MOVIE_ID}/"
HTML_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def main():
    print("=" * 60)
    print(f"付费静态代理测试")
    print(f"代理: {PROXY_USER}@{PROXY_HOST}:{PROXY_PORT}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(proxy=PROXY_CONFIG, headless=False)
        page = browser.new_page()
        page.set_default_timeout(30000)

        try:
            # ── Step 1: 验证出口 IP ──
            print("\n[Step 1/3] 验证代理出口 IP...")
            page.goto("https://httpbin.org/ip")
            ip_text = page.content()
            print(f"   出口 IP 信息: {ip_text}")
            print("   ✅ 代理已生效")

            # ── Step 2: sleep 后访问豆瓣 ──
            print(f"\n[Step 2/3] 等待 30s（保护静态 IP 不被限流）...")
            time.sleep(30)

            print(f"   访问豆瓣: {TEST_DOUBAN_URL}")
            page.goto(TEST_DOUBAN_URL)
            print(f"   页面标题: {page.title()}")
            print("   ✅ 豆瓣页面加载成功")

            # 检测并点击验证按钮
            print(f"\n[Step 3/3] 检测验证按钮 + 提取页面")
            try:
                print("   等待 15s，确保验证按钮加载完成...")
                time.sleep(15)
                page.locator("#sub").click(timeout=3000)
                print("   ✅ 检测到验证按钮，已自动点击")
                print("   等待 45s，伪装正常流量...")
                time.sleep(45)
            except Exception:
                print("   ℹ️ 未触发验证，跳过")

            # 保存 HTML
            html = page.content()
            output_path = os.path.join(HTML_OUTPUT_DIR, f"movie_{TEST_MOVIE_ID}_proxy.html")
            os.makedirs(HTML_OUTPUT_DIR, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)

            print(f"   HTML 已保存: {output_path} ({len(html)} 字节)")
            print("\n" + "=" * 60)
            print("✅ 付费静态代理测试通过")
            print("=" * 60)

        except Exception as e:
            print("\n" + "=" * 60)
            print(f"❌ 代理测试失败: {e}")
            print("=" * 60)

        finally:
            browser.close()


if __name__ == "__main__":
    main()
