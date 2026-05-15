"""
神龙IP代理拉取+测试脚本
自动从API拉取IP，批量测试可用性，输出可用代理
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import aiohttp
import random
from config.settings import settings

# 神龙IP API地址（你提供的）
SHENLONG_API = "http://api.shenlongip.com/ip?key=8906ubvv&protocol=2&mr=1&pattern=json&need=1001&count=2&sign=0305c015b37edbf8eed83345f080fa39"
# 测试目标URL
TEST_URL = "https://www.douban.com/"
TIMEOUT = 15

# 内置UA列表，不需要额外依赖
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15"
]

def get_random_user_agent() -> str:
    """内置UA随机生成函数，不需要依赖utils.http"""
    return random.choice(USER_AGENTS)

async def fetch_proxies() -> list:
    """从神龙IP API拉取代理列表"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SHENLONG_API, timeout=10) as resp:
                if resp.status != 200:
                    print(f"❌ 拉取IP失败，API状态码: {resp.status}")
                    return []
                
                # 先读取原始响应内容打印出来排查问题
                raw_content = await resp.text()
                print(f"📝 API原始返回内容:\n{raw_content}\n")
                
                # 尝试解析JSON
                try:
                    data = await resp.json(content_type=None)  # 忽略mimetype强制解析
                except:
                    print("❌ API返回不是JSON格式，上面是原始返回内容，请根据提示排查：")
                    print("👉 常见原因：签名sign过期、key无效、配额用完、白名单IP不对")
                    return []
                
                if data.get("code") != 200:
                    print(f"❌ API返回错误: {data.get('msg', '未知错误')}")
                    return []
                
                # 解析返回的IP列表（白名单模式，无用户名密码）
                proxies = []
                for item in data["data"]:
                    proxy_url = f"http://{item['ip']}:{item['port']}"
                    proxies.append({
                        "url": proxy_url,
                        "username": None,
                        "password": None,
                        "expire_time": item.get("expire_time", "未知")
                    })
                print(f"✅ 成功拉取到 {len(proxies)} 个代理IP（白名单模式，无认证）")
                return proxies
    except Exception as e:
        print(f"❌ 拉取IP异常: {str(e)}")
        return []

async def test_single_proxy(proxy_info: dict) -> dict:
    """测试单个代理可用性"""
    proxy_url = proxy_info["url"]
    username = proxy_info["username"]
    password = proxy_info["password"]
    expire_time = proxy_info["expire_time"]
    
    print(f"\n🔍 测试代理: {proxy_url} (过期时间: {expire_time})")
    
    # 白名单模式不需要认证
    proxy_args = {}
    if username and password:
        proxy_args["proxy_auth"] = aiohttp.BasicAuth(username, password)
    start_time = asyncio.get_event_loop().time()
    
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            headers = {"User-Agent": get_random_user_agent()}
            async with session.get(
                TEST_URL,
                proxy=proxy_url,
                headers=headers,
                verify_ssl=False,
                **proxy_args
            ) as resp:
                status = resp.status
                content = await resp.text()
                cost = round((asyncio.get_event_loop().time() - start_time) * 1000, 2)
                
                if status == 200 and "豆瓣" in content:
                    # 获取出口IP验证匿名度
                    async with session.get(
                        "https://api.ipify.org?format=json",
                        proxy=proxy_url,
                        **proxy_args
                    ) as ip_resp:
                        ip_data = await ip_resp.json()
                        proxy_ip = ip_data["ip"]
                    
                    print(f"✅ 可用 | 延迟: {cost}ms | 出口IP: {proxy_ip}")
                    return {
                        **proxy_info,
                        "available": True,
                        "delay_ms": cost,
                        "proxy_ip": proxy_ip
                    }
                else:
                    print(f"❌ 不可用 | 状态码: {status} | 无法访问豆瓣")
                    return {**proxy_info, "available": False, "error": f"状态码{status}"}
                    
    except Exception as e:
        cost = round((asyncio.get_event_loop().time() - start_time) * 1000, 2)
        print(f"❌ 不可用 | 耗时: {cost}ms | 错误: {str(e)}")
        return {**proxy_info, "available": False, "error": str(e)}

async def main():
    print("=" * 80)
    print("🐉 神龙IP代理拉取+测试工具")
    print("=" * 80)
    
    # 1. 拉取IP
    proxies = await fetch_proxies()
    if not proxies:
        return
    
    # 2. 批量测试
    print("\n🚀 开始批量测试代理可用性...")
    tasks = [test_single_proxy(p) for p in proxies]
    results = await asyncio.gather(*tasks)
    
    # 3. 统计结果
    available = [r for r in results if r["available"]]
    print("\n" + "=" * 80)
    print(f"📊 测试结果：共 {len(proxies)} 个，可用 {len(available)} 个")
    print("=" * 80)
    
    if available:
        print("\n✅ 可用代理列表：")
        for idx, p in enumerate(available, 1):
            print(f"{idx}. {p['url']}")
            print(f"   用户名：{p['username']}")
            print(f"   密码：{p['password']}")
            print(f"   延迟：{p['delay_ms']}ms")
            print(f"   出口IP：{p['proxy_ip']}")
            print(f"   过期时间：{p['expire_time']}\n")
        
        # 输出可以直接复制到.env的配置
        first = available[0]
        print("💡 可直接复制到.env的代理配置：")
        print(f"PROXY_ENABLED=true")
        print(f"PROXY_URL={first['url']}")
        print(f"PROXY_USERNAME={first['username']}")
        print(f"PROXY_PASSWORD={first['password']}")
    else:
        print("\n❌ 没有可用的代理IP，请检查API配额或IP白名单配置")

if __name__ == "__main__":
    asyncio.run(main())