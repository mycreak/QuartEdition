"""
完整长评爬取脚本（符合正式流程版）
流程：
1. 从本地HTML提取长评列表
2. 先写入 movie_review 表（状态 pending）
3. 爬取正文后写入 MongoDB 并更新 movie_review 状态为 done
4. AI分析并写入 review_summary 表
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from config.settings import settings

# -------------------------- 以下是符合规范的导入 --------------------------
# 导入新版DatabaseLayerV2和底层连接池初始化函数
from db.database_v2 import DatabaseLayerV2
from db.mysql import init_mysql, close_mysql
from db.mongodb import init_mongodb, close_mongodb
from db.redis import init_redis, close_redis
from services.review_service import init_review_service, _get_review_service
# ---------------------------------------------------------------------------

async def init_services():
    """初始化项目统一数据库和服务层，和正式环境逻辑完全一致"""
    # 1. 先初始化三个底层连接池
    try:
        await init_mysql()
    except Exception as e:
        print(f"❌ MySQL初始化失败: {e}")
        raise
    try:
        await init_redis()
    except Exception as e:
        print(f"⚠️ Redis初始化跳过: {e}")
    await init_mongodb()

    # 2. 实例化新版DatabaseLayerV2，默认类型为mysql
    db = DatabaseLayerV2()
    await db.initialize("mysql")

    # 3. 初始化ReviewService，传入新版db实例
    init_review_service(db)
    print("✅ 新版统一中间件DatabaseLayerV2初始化完成")
    return db

# 本地测试HTML文件路径
TEST_HTML_PATH = r"e:\QuartEdition\BackEnd\data\将来的事的影评 (476).html"
# 长评详情页URL模板
REVIEW_DETAIL_URL = "https://movie.douban.com/review/{review_id}/"
# 测试电影的信息（《将来的事》）
MOVIE_ID = 21
DOUBAN_ID = "26215216"

async def get_top_n_review_meta(n: int = 5) -> list:
    """从本地HTML文件提取前N条长评的元信息（包括review_id, title, author, date, useful_count）"""
    with open(TEST_HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    soup = BeautifulSoup(html, "html.parser")
    review_items = soup.select(".review-item")[:n]
    reviews = []
    for item in review_items:
        rid = item.get("id", "").split("-")[-1]
        if rid:
            # 提取标题
            title_elem = item.select_one(".review-title a")
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # 提取作者
            author_elem = item.select_one(".review-author a")
            author = author_elem.get_text(strip=True) if author_elem else ""
            
            # 提取日期
            date_elem = item.select_one(".review-header-time")
            date = date_elem.get_text(strip=True) if date_elem else ""
            
            # 提取有用数
            useful_elem = item.select_one(".review-action .action-btn")
            useful_count = 0
            if useful_elem:
                useful_text = useful_elem.get_text(strip=True)
                if "有用" in useful_text:
                    import re
                    num_match = re.search(r"\d+", useful_text)
                    if num_match:
                        useful_count = int(num_match.group())
            
            reviews.append({
                "review_id": rid,
                "title": title,
                "author": author,
                "date": date,
                "useful_count": useful_count
            })
    print(f"✅ 提取到前{len(reviews)}条长评元信息")
    for r in reviews:
        print(f"   review_id={r['review_id']} | title={r['title']}")
    return reviews

async def insert_movie_review(db, review_meta: dict) -> bool:
    """
    插入单条长评到 movie_review 表（状态 pending）
    
    输入：db: DatabaseLayerV2实例, review_meta: 长评元信息
    输出：是否成功
    """
    raw = db.raw_mysql()
    try:
        await raw.execute_insert(
            "INSERT IGNORE INTO movie_review "
            "(review_id, movie_id, subject_id, title, author, useful_count, date, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                review_meta["review_id"],
                MOVIE_ID,
                DOUBAN_ID,
                review_meta["title"],
                review_meta["author"],
                review_meta["useful_count"],
                review_meta["date"],
                "pending"
            )
        )
        print(f"✅ 已插入 movie_review 表: review_id={review_meta['review_id']}")
        return True
    except Exception as e:
        print(f"⚠️ 插入 movie_review 表失败: {str(e)}")
        return False

async def update_movie_review_status(db, review_id: str, status: str) -> bool:
    """
    更新 movie_review 表中长评的状态
    
    输入：db: DatabaseLayerV2实例, review_id: 长评ID, status: 新状态
    输出：是否成功
    """
    raw = db.raw_mysql()
    try:
        await raw.execute_update(
            "UPDATE movie_review SET status=%s WHERE review_id=%s",
            (status, review_id)
        )
        print(f"✅ 已更新 movie_review 状态: review_id={review_id} → {status}")
        return True
    except Exception as e:
        print(f"⚠️ 更新 movie_review 状态失败: {str(e)}")
        return False

async def save_ai_summary_to_db(db, ai_result: dict) -> bool:
    """
    将 AI 总结保存到 review_summary 表（完全复刻正式流程）
    
    输入：db: DatabaseLayerV2实例, ai_result: AI返回的结果
    输出：是否成功
    """
    raw = db.raw_mysql()
    try:
        print("\n" + "=" * 80)
        print("💾 步骤4：将 AI 总结保存到 review_summary 表")
        print("=" * 80)
        
        # 1. 幂等检查：已生成过则直接返回
        print("1️⃣ 幂等检查：检查是否已存在总结...")
        existing = await raw.execute_query(
            "SELECT id FROM review_summary WHERE movie_id=%s LIMIT 1",
            (MOVIE_ID,),
        )
        if existing and len(existing) > 0:
            print(f"⚠️ movie_id={MOVIE_ID} 已存在总结，跳过保存")
            return True
        
        # 2. 先插入一条pending记录，防止重复任务并发处理
        print("2️⃣ 插入 pending 记录...")
        await raw.execute_update(
            "INSERT INTO review_summary (movie_id, status, created_at, updated_at) "
            "VALUES (%s, 'pending', NOW(), NOW()) "
            "ON DUPLICATE KEY UPDATE status='pending', updated_at=NOW()",
            (MOVIE_ID,),
        )
        print("✅ pending 记录已插入")
        
        # 3. 准备数据
        full_summary = ai_result.get("full_summary", "")
        tags = json.dumps(ai_result.get("tags", []), ensure_ascii=False)
        
        # 4. 保存结果到数据库
        print("3️⃣ 保存总结和标签到数据库...")
        await raw.execute_update(
            "UPDATE review_summary "
            "SET full_summary=%s, review_tags=%s, status='done', updated_at=NOW() "
            "WHERE movie_id=%s",
            (full_summary, tags, MOVIE_ID),
        )
        
        print("✅ AI 总结已成功保存到 review_summary 表")
        print(f"   movie_id={MOVIE_ID}")
        print(f"   总结长度：{len(full_summary)} 字")
        print(f"   标签数量：{len(ai_result.get('tags', []))} 个")
        return True
        
    except Exception as e:
        print(f"❌ 保存 AI 总结失败: {str(e)}")
        # 标记为失败状态
        try:
            await raw.execute_update(
                "UPDATE review_summary SET status='failed', updated_at=NOW() WHERE movie_id=%s",
                (MOVIE_ID,),
            )
        except Exception:
            pass
        return False

async def crawl_single_review(pw, review_meta: dict, db) -> dict:
    """
    爬取单条长评，自动点击展开
    
    输入：pw: Playwright实例, review_meta: 长评元信息, db: DatabaseLayerV2实例
    输出：爬取结果
    """
    review_id = review_meta["review_id"]
    browser = await pw.chromium.launch(headless=False)
    page = await browser.new_page()
    
    try:
        url = REVIEW_DETAIL_URL.format(review_id=review_id)
        print(f"\n🔗 正在爬取: {url}")
        
        await page.goto(url, timeout=30000)

        # 睡眠后点击豆瓣验证按钮（移植自 playwright_IP_test.py）
        try:
            print("⏳ 等待15秒，确保验证按钮加载完成...") 
            await asyncio.sleep(15)
            await page.locator("#sub").click(timeout=3000)
            print("✅ 检测到验证按钮，已自动点击！")
            print("⏳ 等待45秒，伪装正常流量...")
            await asyncio.sleep(45)
            await page.wait_for_timeout(2000)
        except:
            print("ℹ️ 未触发验证，直接访问")

        await page.wait_for_selector(".review-content", timeout=10000)

        # 上下滑动页面，模拟人类浏览行为
        print("🖱️ 模拟页面滚动...")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo(0, document.querySelector('.review-content').offsetTop - 100)")
        await asyncio.sleep(0.5)

        # 尝试点击展开全文按钮
        expand_btn = await page.query_selector(".review-content .more")
        if expand_btn:
            print("👉 检测到展开按钮，点击展开...")
            await expand_btn.click()
            await asyncio.sleep(2)  # 等待展开动画完成
        
        # 等待5秒让内容完全加载
        print("⏳ 等待内容加载完成...")
        await asyncio.sleep(5)
        
        # 获取完整HTML
        full_html = await page.content()
        
        # 直接从HTML解析完整评论内容
        soup = BeautifulSoup(full_html, "html.parser")
        content_elem = soup.select_one(".review-content")
        content = content_elem.get_text(strip=False, separator="\n") if content_elem else ""
        
        print(f"\n📝 爬取结果预览（前200字）:")
        print(content[:200] + ("..." if len(content) > 200 else ""))
        print(f"\n📊 内容总长度: {len(content)} 字")
        
        # 检查是否有截断标记
        if "..." in content[-10:] or "加载中" in content:
            print("⚠️ 警告：内容可能仍有截断")
        else:
            print("✅ 内容完整，无截断")
            
        # 写入MongoDB
        review_svc = _get_review_service()
        review_data = {
            "title": review_meta["title"],
            "author": review_meta["author"],
            "date": review_meta["date"],
            "useful_count": review_meta["useful_count"],
            "votes": str(review_meta["useful_count"]),
            "text": content
        }
        success = await review_svc.upsert_review(
            review_id=review_id,
            movie_douban_id=DOUBAN_ID,
            review=review_data,
            movie_id=MOVIE_ID
        )
        if success:
            print("💾 内容已写入MongoDB数据库")
            # 更新 movie_review 状态
            await update_movie_review_status(db, review_id, "done")
        else:
            print("⚠️ 写入MongoDB失败")
            await update_movie_review_status(db, review_id, "failed")
        
        return {
            "review_id": review_id,
            "content": content,
            "success": success
        }
        
    except Exception as e:
        print(f"❌ 爬取失败: {str(e)}")
        # 更新状态为 failed
        await update_movie_review_status(db, review_id, "failed")
        return {
            "review_id": review_id,
            "error": str(e),
            "success": False
        }
    finally:
        await browser.close()

async def main():
    print("=" * 80)
    print("🎬 完整长评爬取脚本（符合正式流程版）")
    print("=" * 80)
    
    # 1. 提取前N条长评元信息
    review_metas = await get_top_n_review_meta(3)
    if not review_metas:
        print("❌ 未提取到长评信息，请检查HTML文件路径是否正确")
        return
    
    # 2. 初始化新版统一数据库中间件和服务层
    db = await init_services()
    
    # 3. 先将所有长评元信息写入 movie_review 表（状态 pending）
    print("\n" + "=" * 80)
    print("📝 步骤1：将长评元信息写入 movie_review 表")
    print("=" * 80)
    for rm in review_metas:
        await insert_movie_review(db, rm)
    
    # 4. 批量爬取正文
    print("\n" + "=" * 80)
    print("🌐 步骤2：批量爬取长评正文")
    print("=" * 80)
    results = []
    async with async_playwright() as pw:
        for idx, rm in enumerate(review_metas):
            # 除第一条外，每次爬取前等待120s
            if idx > 0:
                print(f"\n⏳ 等待120秒后爬取下一条...")
                await asyncio.sleep(120)

            res = await crawl_single_review(pw, rm, db)
            results.append(res)

    # === 5. AI分析：基于爬取到的完整长评生成总结 ===
    success_reviews = [r for r in results if r["success"] and r.get("content")]
    ai_result = None
    if success_reviews:
        print("\n" + "=" * 80)
        print("🤖 步骤3：AI分析 - 基于爬取到的完整长评生成总结")
        print("=" * 80)
        for r in success_reviews:
            print(f"   📄 review_id={r['review_id']} | {len(r['content'])}字")

        from utils.ai_client import get_ai_client
        ai_reviews = [{"content": r["content"], "useful_count": 0} for r in success_reviews]
        ai_client = get_ai_client()
        ai_result = await ai_client.generate_review_summary(ai_reviews, max_chars_per_review=1000)

        if ai_result:
            print("\n📄 综合总结：")
            print(ai_result.get("full_summary", "无"))
            print("\n🏷️ 核心标签：")
            for tag in ai_result.get("tags", []):
                print(f"  - {tag}")
            
            # === 6. 将 AI 总结保存到数据库 ===
            await save_ai_summary_to_db(db, ai_result)
        else:
            print("❌ AI总结生成失败，请检查 API Key 和网络连接")
    else:
        print("\n⚠️ 没有成功爬取的长评，跳过AI分析")

    # 7. 优雅关闭连接池（符合规范的收尾）
    await asyncio.gather(
        close_mysql(),
        close_redis(),
        close_mongodb(),
    )
    print("\n✅ 数据库连接池已关闭")
    
    # 8. 统计结果
    print("\n" + "=" * 80)
    print("📊 最终结果统计")
    print("=" * 80)
    success_count = sum(1 for r in results if r["success"])
    print(f"✅ 成功爬取: {success_count}/{len(results)} 条")
    
    for res in results:
        status = "✅ 成功" if res["success"] else "❌ 失败"
        print(f"{status} review_id={res['review_id']}")

if __name__ == "__main__":
    asyncio.run(main())