
"""
插入20条《将来的事》测试影评到MongoDB，关联movie_id=21
"""
"""
插入20条《将来的事》测试影评到MongoDB，关联movie_id=21
"""
import os
import json
from datetime import datetime
from bs4 import BeautifulSoup
from pymongo import MongoClient

def main():
    # 读取HTML文件
    with open(r'e:\QuartEdition\BackEnd\data\将来的事的影评 (476).html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    review_items = soup.select('div.review-item')[:20]  # 取前20条
    
    # 连接MongoDB（根据你的实际配置修改）
    client = MongoClient(
        'mongodb://localhost:27017/',
        username='root',
        password='123456',
        authSource='admin'
    )
    db = client['movie_db']  # 你的库名
    collection = db['reviews']
    
    count = 0
    now = datetime.utcnow().isoformat() + 'Z'
    
    for idx, item in enumerate(review_items, 1):
        try:
            # 提取review_id
            review_id = item.get('id', '').split('-')[-1]
            if not review_id:
                continue
            
            # 提取标题
            title_elem = item.select_one('h2 a')
            title = title_elem.get_text(strip=True) if title_elem else f'影评{idx}'
            
            # 提取作者
            author_elem = item.select_one('a.name')
            author = author_elem.get_text(strip=True) if author_elem else '匿名用户'
            # 作者去敏
            if len(author) <= 2:
                masked_author = author[0] + '*'
            else:
                masked_author = author[:2] + '*' * min(len(author) - 2, 3)
            
            # 提取日期
            date_elem = item.select_one('span.main-meta')
            date = date_elem.get_text(strip=True) if date_elem else '2024-01-01'
            
            # 提取有用数
            useful_elem = item.select_one('span.useful-count')
            useful_count = int(useful_elem.get_text(strip=True) or 0) if useful_elem else 0
            
            # 提取内容
            content_elem = item.select_one('div.short-content, div.review-content')
            content = content_elem.get_text(strip=True, separator='\n') if content_elem else '无内容'
            
            # 按照项目结构构造文档
            review_doc = {
                '_id': review_id,
                'review_id': review_id,
                'movie_douban_id': '26215216',  # 《将来的事》豆瓣ID
                'movie_id': 21,  # 关联movies表id=21
                'title': title,
                'author': masked_author,
                'date': date,
                'votes': str(useful_count),
                'useful_count': useful_count,
                'text': content,
                'is_published': True,
                'crawled_at': now
            }
            
            # 插入，幂等操作，已存在则更新
            result = collection.update_one(
                {'_id': review_id},
                {'$set': review_doc},
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                count += 1
                print(f'[OK] 插入第{count}条影评：id={review_id}, 标题={title}')
                
        except Exception as e:
            print(f'[ERROR] 插入失败：{str(e)}')
            continue
    
    client.close()
    print(f'\n[DONE] 总共成功插入{count}条测试影评！请在MongoDB客户端检查reviews集合，筛选movie_id=21即可看到。')

if __name__ == "__main__":
    main()
