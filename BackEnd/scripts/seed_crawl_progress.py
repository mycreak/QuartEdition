"""
scripts/seed_crawl_progress.py

crawl_progress 表种子数据填充脚本。

作用：
    根据 config/movie_type.py 中的 TYPE_MAP 和 ACTIVE_INTERVALS，
    向 crawl_progress 表插入所有 (type_num, interval_id) 组合。
    28 种类型 × 4 个区间 = 112 条记录。

设计要点：
    1. ON DUPLICATE KEY UPDATE — 幂等运行，重复执行不报错不重复插入
    2. 只更新 type_name 和 is_published — 不覆盖运行时爬取的 douban_total
    3. 判断是否爬完：douban_ids 表 COUNT 与 douban_total 对比得出进度

用法：
    cd BackEnd
    python scripts/seed_crawl_progress.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from db import init_mysql, close_mysql
from db.mysql import get_mysql_pool
from config.movie_type import TYPE_MAP, ACTIVE_INTERVALS


INSERT_SQL = """
    INSERT INTO crawl_progress (type_num, type_name, interval_id, is_published)
    VALUES (%s, %s, %s, 1) AS new
    ON DUPLICATE KEY UPDATE
        type_name = new.type_name,
        is_published = 1
"""


async def main():
    await init_mysql()
    pool = get_mysql_pool()

    inserted = 0
    updated = 0
    errors = []

    for type_num, type_name in TYPE_MAP.items():
        for interval_id in ACTIVE_INTERVALS:
            try:
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(INSERT_SQL, (type_num, type_name, interval_id))
                        if cur.rowcount == 1:
                            inserted += 1
                        else:
                            updated += 1
            except Exception as e:
                errors.append(f"  type_num={type_num} interval_id={interval_id}: {e}")

    await close_mysql()

    total = len(TYPE_MAP) * len(ACTIVE_INTERVALS)
    print(f"\n{'=' * 60}")
    print(f"  crawl_progress 种子数据填充完成")
    print(f"  类型数: {len(TYPE_MAP)}  区间数: {len(ACTIVE_INTERVALS)}")
    print(f"  预期总数: {total}")
    print(f"  本次 INSERT: {inserted}  已有更新: {updated}  失败: {len(errors)}")
    if errors:
        print(f"\n  失败明细:")
        for e in errors:
            print(e)
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
