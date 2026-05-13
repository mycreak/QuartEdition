from playwright.sync_api import sync_playwright
import time
import os

# 要测试的代理
LOCAL_IP = "172.28.0.1"

IP = "112.36.239.144"
PORT = 20858
PROXY = f"http://{IP}:{PORT}"

MOVIE_ID = "25814705"
TEST_URL = f"https://movie.douban.com/subject/{MOVIE_ID}/"
HTML_OUTPUT_DIR = r"e:\QuartEdition\BackEnd\data"

def test_proxy():
    print(f"开始测试代理：{PROXY}")
    print(f"测试目标：{TEST_URL}")

    try:
        with sync_playwright() as p:
            # # 配置浏览器代理
            # browser = p.chromium.launch(
            #     proxy={
            #         "server": f"http://{PROXY}"  # 固定格式，不用改
            #     },
            #     headless=False  # False=显示浏览器，True=后台运行
            # )
            # 不写proxy配置 = 本机IP直连
            browser = p.chromium.launch(headless=False)


            # 新建页面
            page = browser.new_page()
            # 设置超时时间
            page.set_default_timeout(15000)

            # 访问豆瓣电影
            page.goto(TEST_URL)

            # ==============================================
            # 点击验证按钮（如果有），确保页面完全展示
            # ==============================================
            try:
                time.sleep(15)
                page.locator("#sub").click(timeout=3000)
                print("✅ 检测到验证按钮，已自动点击！")
                page.wait_for_timeout(2000)
            except:
                print("ℹ️ 未触发验证，直接访问")

            # ==============================================
            # 将页面保存到本地HTML，后续再慢慢解析
            # ==============================================
            time.sleep(10)
            html_content = page.content()

            output_path = os.path.join(HTML_OUTPUT_DIR, f"movie_{MOVIE_ID}.html")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            print("-" * 50)
            print("✅ 代理已生效，页面加载成功！")
            print(f"HTML已保存至：{output_path}")
            print(f"文件大小：{len(html_content)} 字节")
            print("-" * 50)

            browser.close()

    except Exception as e:
        print("-" * 50)
        print("❌ 代理测试失败！")
        print(f"失败原因：{str(e)}")
        print("代理不可用 / 已失效 / 网络不通")
        print("-" * 50)

if __name__ == "__main__":
    test_proxy()