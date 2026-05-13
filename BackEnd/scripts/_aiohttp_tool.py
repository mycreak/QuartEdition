"""
aiohttp 请求小工具 — 快速测试任意 HTTP 接口
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp
import brotli


async def request(url, **kwargs):
    print(f"请求: {kwargs.get('method', 'GET')} {url}")
    if "params" in kwargs:
        print(f"查询参数: {kwargs['params']}")
    if "headers" in kwargs:
        print(f"请求头: {json.dumps(kwargs['headers'], ensure_ascii=False, indent=2)}")
    if "cookies" in kwargs:
        print(f"Cookie 条目: {len(kwargs['cookies'])} 个")

    timeout = aiohttp.ClientTimeout(total=30)
    kwargs["timeout"] = timeout

    async with aiohttp.ClientSession(auto_decompress=False) as session:
        async with session.request(**kwargs, url=url, ssl=False) as resp:
            print(f"\nHTTP 状态码: {resp.status} {resp.reason}")
            print(f"Content-Type: {resp.headers.get('Content-Type', '-')}")
            print(f"Content-Encoding: {resp.headers.get('Content-Encoding', '-')}")

            raw = await resp.read()
            encoding = resp.headers.get("Content-Encoding", "")
            if "br" in encoding:
                raw = brotli.decompress(raw)
                encoding = encoding.replace("br", "").strip()
            body = raw.decode("utf-8")
            content_type = resp.headers.get("Content-Type", "")
            print(f"\n响应体: {len(body):,} 字符")

            if "json" in content_type or body.strip().startswith(("{", "[")):
                try:
                    data = json.loads(body)
                    if isinstance(data, list):
                        print(f"JSON 列表长度: {len(data)}")
                        for i, item in enumerate(data[:2]):
                            if isinstance(item, dict):
                                print(f"\n  [{i}] 字段:")
                                for k, v in item.items():
                                    s = str(v)
                                    print(f"    {k}: {s[:120]}")
                            else:
                                print(f"  [{i}]: {str(item)[:200]}")
                        if len(data) > 2:
                            print(f"  ... 共 {len(data)} 条")
                    elif isinstance(data, dict):
                        print(f"JSON 对象, 键: {list(data.keys())[:15]}")
                        for k in list(data.keys())[:10]:
                            v = data[k]
                            if isinstance(v, (dict, list)):
                                print(f"  {k}: {type(v).__name__} (len={len(v)})")
                            else:
                                print(f"  {k}: {str(v)[:100]}")
                    print(f"\n原始 JSON (前 3000 字符):")
                    print(body[:3000])
                except json.JSONDecodeError:
                    print(f"原始文本 (前 1000 字符):")
                    print(body[:1000])
            else:
                print(f"原始文本 (前 1000 字符):")
                print(body[:1000])

            return resp.status, body


if __name__ == "__main__":
    url = "https://movie.douban.com/j/chart/top_list_count"
    kwargs = {
        "method": "GET",
        "params": {"type": "24", "interval_id": "100:90", "action": ""},
        "headers": {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9",
            "referer": "https://movie.douban.com/typerank?type_name=%E5%96%9C%E5%89%A7&type=24&interval_id=100:90&action=",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "x-requested-with": "XMLHttpRequest",
        },
        "cookies": {
            "bid": "UAZmWwgAFrQ", "ll": "118331", "ct": "y",
            "_pk_id.100001.4cf6": "968fc7fe69ed79d3.1774933956.",
            "ap_v": "0,6.0", "push_noty_num": "0", "push_doumail_num": "0",
            "dbsawcv1": "MTc3Nzg0Mjk0N0AwOWM2OGRhNGEzNzJkZmQ0MGYwYjc4ZjgyZGMyYTA3ODA4NjU1NmJlZDEzYzUyYmUyMDI1YjVjZTYwYWUzNjAzQGU3NWFkMmQzNTBjODk5ZWJAZTQzYzA0ZmY0Y2Qy",
        },
    }

    try:
        asyncio.run(request(url, **kwargs))
    except KeyboardInterrupt:
        print("\n中断")
    except Exception as e:
        print(f"\n❌ 请求失败: {type(e).__name__}: {e}")
