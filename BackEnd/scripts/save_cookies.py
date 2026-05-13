"""
scripts/save_cookies.py

从手动复制的 Cookie 生成 douban_storage.json（无需打开浏览器）。

最轻量方案 — 适用于浏览器已登录的场景。

用法：
    # 方式一：命令行传参
    python scripts/save_cookies.py --dbcl2 "abc123..." --bid "xyz789..."

    # 方式二：交互式输入
    python scripts/save_cookies.py
    # 按提示粘贴 dbcl2 和 bid 的值

如何从 Chrome 获取 Cookie 值：
    1. Chrome 打开 https://movie.douban.com
    2. F12 → Application → Cookies → ".douban.com" 或 "movie.douban.com"
    3. 复制 dbcl2 的值（Name: dbcl2, Value 列）
    4. 复制 bid 的值

最少只需 dbcl2，bid 有助于提高信用分。

输出文件：
    data/douban_storage.json — Playwright storage_state 兼容格式
      {
        "saved_at": "2026-05-04T12:00:00",
        "playwright_state": {
          "cookies": [
            {"name":"dbcl2", "value":"...", "domain":".douban.com", ...},
            {"name":"bid", "value":"...", ...}
          ]
        }
      }
"""

import argparse
import json
import os
from datetime import datetime, timezone, timedelta

# 东八区时区常量
CST = timezone(timedelta(hours=8))

STORAGE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "douban_storage.json")


def build_cookie(name: str, value: str, domain: str, http_only: bool = True, secure: bool = True) -> dict:
    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": "/",
        "httpOnly": http_only,
        "secure": secure,
        "sameSite": "None",
    }


def main():
    parser = argparse.ArgumentParser(description="从手动复制的 Cookie 生成 douban_storage.json")
    parser.add_argument("--dbcl2", help="豆瓣登录令牌 (dbcl2 cookie value)")
    parser.add_argument("--bid", help="浏览器标识 (bid cookie value)，可选但推荐提供")
    args = parser.parse_args()

    dbcl2 = args.dbcl2
    bid = args.bid

    if not dbcl2:
        print("=" * 50)
        print("  Cookie 保存脚本")
        print("=" * 50)
        print()
        print("  📋 如何获取 Cookie：")
        print("     Chrome → F12 → Application → Cookies → .douban.com")
        print("     找到 dbcl2 行，复制 Value 列")
        print()
        dbcl2 = input("  粘贴 dbcl2 的值: ").strip()

    if not dbcl2:
        print("  ❌ dbcl2 为空，取消操作")
        return

    if not bid:
        bid = input("  粘贴 bid 的值 (可选，直接回车跳过): ").strip()

    cookies = [
        build_cookie("dbcl2", dbcl2, ".douban.com"),
    ]
    if bid:
        cookies.insert(0, build_cookie("bid", bid, ".douban.com", http_only=False, secure=False))

    wrapper = {
        "saved_at": datetime.now(CST).isoformat(),
        "playwright_state": {
            "cookies": cookies,
            "origins": [],
        },
    }

    os.makedirs(os.path.dirname(STORAGE_FILE), exist_ok=True)
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(wrapper, f, ensure_ascii=False, indent=2)

    print(f"  💾 登录态已保存: {STORAGE_FILE}")
    print(f"     dbcl2: {dbcl2[:8]}...")
    if bid:
        print(f"     bid:   {bid[:8]}...")
    print(f"     保存时间: {wrapper['saved_at']}")
    print()
    print(f"  🖥️  服务器部署：")
    print(f"     scp {STORAGE_FILE} user@server:{STORAGE_FILE}")
    print("=" * 50)


if __name__ == "__main__":
    main()
