
"""
导入测试影评数据到MongoDB，关联movie_id=21
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from bs4 import BeautifulSoup
from db.database import init_db
from services.review_service import _get_review_service, init_review_service

# 豆瓣电影ID（电影《将来的事》）
DOUBAN_MOVIE_ID = "26215216"
# 关联movies表id=21
MOVIE_ID = 21

def parse_reviews_from_html(html_path: str) -> list:
    """从豆瓣影评列表页解析出20条影评"""
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, "html.parser")
    review_items = soup.select(".review-item")
    reviews = []
    
    for i, item in enumerate(review_items[:20]):
        # 提取review_id
        review_id = item.get("id", f"test_review_{i+1}")
        if not review_id:
            review_id = f"test_review_{i+1}"
        
        # 提取标题
        title_elem = item.select_one("h2 a")
        title = title_elem.get_text(strip=True) if title_elem else f"测试影评{i+1}"
        
        # 提取作者
        author_elem = item.select_one(".name a")
        author = author_elem.get_text(strip=True) if author_elem else "匿名用户"
        
        # 提取点赞数
        useful_elem = item.select_one(".useful_count")
        useful_count = 0
        if useful_elem:
            useful_text = useful_elem.get_text(strip=True)
            if useful_text.isdigit():
                useful_count = int(useful_text)
        
        # 提取摘要，作为正文的一部分
        abstract_elem = item.select_one(".short-content")
        abstract = abstract_elem.get_text(strip=True) if abstract_elem else ""
        
        # 生成模拟的完整长评正文
        full_content = f"""
{title}

{abstract}

这是一部非常优秀的法国电影，于佩尔的表演非常细腻，把一个中年女性面临生活变故时的从容和自由展现得淋漓尽致。电影探讨了哲学、婚姻、自由等多个主题，叙事平淡但充满力量，是值得反复回味的佳作。
很多观众看完后都被女主的生活态度所感染，即使人生遭遇各种意外和失去，依然可以保持精神上的独立和自由。
        """.strip()
        
        reviews.append({
            "review_id": review_id,
            "title": title,
            "author": author,
            "useful_count": useful_count,
            "content": full_content
        })
    
    return reviews

async def import_reviews(reviews: list):
    """导入影评到MongoDB"""
    review_service = _get_review_service()
    success_count = 0
    
    for review in reviews:
        try:
            # 调用upsert_review写入数据库
            result = await review_service.upsert_review(
                review_id=review["review_id"],
                movie_douban_id=DOUBAN_MOVIE_ID,
                review={
                    "title": review["title"],
                    "author": review["author"],
                    "text": review["content"],
                    "useful_count": review["useful_count"]
                },
                movie_id=MOVIE_ID
            )
            if result:
                success_count += 1
                print(f"成功导入影评：{review['title']}（点赞数：{review['useful_count']}）")
            else:
                print(f"导入失败：{review['title']}")
        except Exception as e:
            print(f"导入异常：{review['title']}，错误：{e}")
    
    print(f"\n导入完成，共成功导入 {success_count}/{len(reviews)} 条影评！")
    return success_count

async def main():
    """主函数，统一初始化和执行"""
    # 初始化数据库和ReviewService
    await init_db()
    init_review_service()
    
    html_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "将来的事的影评 (476).html")
    if not os.path.exists(html_path):
        print(f"找不到HTML文件：{html_path}")
        sys.exit(1)
    
    print("正在解析影评数据...")
    reviews = parse_reviews_from_html(html_path)
    if not reviews:
        print("没有解析到任何影评")
        sys.exit(1)
    
    print(f"解析到 {len(reviews)} 条影评，开始导入MongoDB...")
    await import_reviews(reviews)

if __name__ == "__main__":
    asyncio.run(main())
