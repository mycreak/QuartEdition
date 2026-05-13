import requests
from pathlib import Path

url = "https://movie.douban.com/subject/1292052/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
cookies = {"bid": "UAZmWwgAFrQ"}

print(f"请求: {url}")
resp = requests.get(url, headers=headers, cookies=cookies, timeout=15)
print(f"状态: {resp.status_code}, 长度: {len(resp.text):,}")

out = Path(__file__).parent.parent / "data" / "douban_sample.html"
out.write_text(resp.text, encoding="utf-8")

if "载入中" in resp.text:
    print(f"⚠️ 验证页 → {out}")
elif "检测到有异常请求" in resp.text:
    print(f"⚠️ 被拦截 → {out}")
else:
    print(f"✅ 正常电影页 → {out}")
