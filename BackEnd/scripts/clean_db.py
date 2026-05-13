"""
scripts/clean_db.py

清理所有电影、评论、人员相关数据（MySQL + MongoDB），
为 E2E 测试提供干净的数据库环境。

MySQL 删除顺序（遵守外键依赖）：
    1. movie_ratings
    2. movie_regions / movie_genres / movie_credits
    3. movies_history / people_history
    4. movies / people

MongoDB：
    reviews / comments 全量删除

保留数据：
    auth 三表（users / permissions / user_permissions）
    crawl_progress（种子数据）
    task_failures（失败日志）
"""

import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.mysql import init_mysql, close_mysql, execute_update as mysql_execute
from db.mongodb import init_mongodb, close_mongodb, get_mongodb

logger = logging.getLogger(__name__)

MYSQL_TABLES_IN_ORDER = [
    "movie_ratings",
    "movie_regions",
    "movie_genres",
    "movie_credits",
    "movies_history",
    "people_history",
    "movies",
    "people",
    "regions",
]


async def clean_mysql():
    await init_mysql()
    deleted = {}
    for table in MYSQL_TABLES_IN_ORDER:
        try:
            affected = await mysql_execute(f"DELETE FROM `{table}`", ())
            deleted[table] = affected
            logger.info(f"  MySQL {table}: 清除 {affected} 行")
        except Exception as e:
            logger.warning(f"  MySQL {table}: 跳过 ({e})")
    await close_mysql()
    return deleted


async def clean_mongodb():
    await init_mongodb()
    db = get_mongodb()
    for coll in ["reviews", "comments"]:
        result = await db[coll].delete_many({})
        logger.info(f"  MongoDB {coll}: 清除 {result.deleted_count} 条")
    await close_mongodb()


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger.info("=" * 50)
    logger.info("开始清理数据库脏数据")
    logger.info("=" * 50)

    logger.info("\n[MySQL]")
    await clean_mysql()

    logger.info("\n[MongoDB]")
    await clean_mongodb()

    logger.info("\n" + "=" * 50)
    logger.info("清理完成")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
