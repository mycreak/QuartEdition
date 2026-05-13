
"""
AI总结提示词测试脚本
测试目标：验证DeepSeek V4 Flash根据影评生成的总结和标签是否符合要求
"""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import aiomysql
from pymongo import MongoClient
from utils.ai_client import get_ai_client
from config.settings import settings

async def main():
    print('=' * 80)
    print('🎬 AI电影长评总结提示词测试')
    print('=' * 80)
    
    # 1. 从MongoDB读取movie_id=21的20条长评
    print('\n📥 1. 读取测试影评数据...')
    # 动态适配MongoDB认证：有用户名密码才加认证信息
    if settings.MONGO_USER and settings.MONGO_PASSWORD:
        client = MongoClient(
            f'mongodb://{settings.MONGO_USER}:{settings.MONGO_PASSWORD}@{settings.MONGO_HOST}:{settings.MONGO_PORT}/',
            authSource='admin'
        )
    else:
        # 无认证连接
        client = MongoClient(f'mongodb://{settings.MONGO_HOST}:{settings.MONGO_PORT}/')
    
    db = client[settings.MONGO_DATABASE]
    collection = db['reviews']
    
    reviews = list(collection.find(
        {'movie_id': 21, 'is_published': True},
        {'text': 1, 'useful_count': 1, '_id': 0}
    ).sort([('useful_count', -1)]).limit(20))
    
    if not reviews:
        print('❌ 未找到测试影评数据，请先运行insert_test_reviews.py插入测试数据')
        client.close()
        return
    
    # 适配AI客户端需要的content字段
    for r in reviews:
        r['content'] = r.pop('text', '')
    
    print(f'✅ 成功读取{len(reviews)}条测试影评')
    print(f'📝 第一条影评预览：{reviews[0]["content"][:100]}...' if reviews else '')
    
    # 2. 调用AI生成总结
    print('\n🤖 2. 调用DeepSeek V4 Flash生成总结...')
    ai_client = get_ai_client()
    result = await ai_client.generate_review_summary(reviews)
    
    if not result:
        print('❌ AI总结生成失败，请查看日志')
        client.close()
        return
    
    # 3. 输出结果
    print('\n✅ AI总结生成成功！结果如下：')
    print('-' * 80)
    
    summary = result.get('full_summary', '无')
    tags = result.get('tags', [])
    
    print('📄 综合总结：')
    print(summary)
    print()
    
    print('🏷️ 核心标签：')
    for tag in tags:
        print(f'  - {tag}')
    print()
    
    # 4. 格式校验
    print('🔍 格式校验结果：')
    has_summary = 'full_summary' in result and result['full_summary']
    has_tags = 'tags' in result and isinstance(result['tags'], list) and len(result['tags']) <=5
    all_ok = has_summary and has_tags
    
    if all_ok:
        print('✅ 格式完全符合要求！')
        if len(result['tags']) > 5:
            print(f'⚠️ 注意：标签数量{len(result["tags"])}超过5个，已自动截取前5个')
    else:
        print('❌ 格式不符合要求：')
        if not has_summary:
            print('  - 缺少full_summary字段或内容为空')
        if not has_tags:
            print('  - 缺少tags字段或不是列表/超过5个')
    
    # 5. 写入MySQL数据库review_summary表
    if all_ok:
        print('\n💾 5. 写入MySQL数据库...')
        try:
            # 连接MySQL
            mysql_conn = await aiomysql.connect(
                host=settings.MYSQL_HOST,
                port=settings.MYSQL_PORT,
                user=settings.MYSQL_USER,
                password=settings.MYSQL_PASSWORD,
                db=settings.MYSQL_DATABASE,
                charset='utf8mb4'
            )
            
            async with mysql_conn.cursor() as cursor:
                # 标签转JSON字符串
                tags_json = json.dumps(tags, ensure_ascii=False)
                
                # 插入或更新（movie_id唯一键，幂等操作）
                sql = """
                INSERT INTO review_summary (movie_id, full_summary, review_tags, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'done', NOW(), NOW())
                ON DUPLICATE KEY UPDATE 
                    full_summary = VALUES(full_summary),
                    review_tags = VALUES(review_tags),
                    status = 'done',
                    updated_at = NOW()
                """
                await cursor.execute(sql, (21, summary, tags_json))
                await mysql_conn.commit()
                
                affected_rows = cursor.rowcount
                if affected_rows == 1:
                    print('✅ 数据已成功插入数据库！')
                elif affected_rows == 2:
                    print('✅ 数据库中已有记录，已更新为最新结果！')
            
            mysql_conn.close()
        except Exception as e:
            print(f'❌ 写入数据库失败：{str(e)}')
    
    print('\n' + '=' * 80)
    print('🎉 测试完成！请根据输出结果调整提示词')
    client.close()

if __name__ == '__main__':
    asyncio.run(main())
