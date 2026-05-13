"""
执行迁移: crawl_progress 表增加 ids_fetched 字段
用法: python scripts/run_migration.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.db_config import get_mysql_config
import pymysql

cfg = get_mysql_config()

print("=" * 60)
print(f"目标数据库: {cfg.host}:{cfg.port}/{cfg.database}")
print("=" * 60)

conn = pymysql.connect(
    host=cfg.host,
    port=cfg.port,
    user=cfg.user,
    password=cfg.password or None,
    database=cfg.database,
    charset=cfg.charset,
    autocommit=True,
)

try:
    with conn.cursor() as cur:
        # 1. 检查字段是否已存在
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='crawl_progress' AND COLUMN_NAME='ids_fetched'",
            (cfg.database,),
        )
        if cur.fetchone()[0]:
            print("[SKIP] ids_fetched 字段已存在，跳过 ADD COLUMN")
        else:
            cur.execute(
                "ALTER TABLE crawl_progress "
                "ADD COLUMN ids_fetched INT NOT NULL DEFAULT 0 COMMENT '已从榜单获取的 douban_id 数量, 用于分页偏移计算' "
                "AFTER douban_total"
            )
            print("[OK] ADD COLUMN ids_fetched 成功")

        # 2. 回填
        cur.execute("SELECT COUNT(*) FROM crawl_progress WHERE ids_fetched = 0 AND douban_total > 0")
        need_backfill = cur.fetchone()[0]
        print(f"  需要回填的行数: {need_backfill}")

        if need_backfill > 0:
            cur.execute("""
                UPDATE crawl_progress cp
                SET cp.ids_fetched = (
                    SELECT COUNT(*)
                    FROM douban_ids d
                    WHERE d.type_num = cp.type_num AND d.interval_id = cp.interval_id
                )
                WHERE cp.ids_fetched = 0 AND cp.douban_total > 0
            """)
            print(f"[OK] 回填完成，影响 {cur.rowcount} 行")

        # 3. 验证
        cur.execute("SELECT type_num, interval_id, douban_total, ids_fetched FROM crawl_progress")
        rows = cur.fetchall()
        if rows:
            print("\n迁移后 crawl_progress 数据:")
            print(f"  {'type_num':<8} {'interval_id':<12} {'total':<6} {'fetched':<8}")
            print(f"  {'-'*8} {'-'*12} {'-'*6} {'-'*8}")
            for r in rows:
                print(f"  {r[0]:<8} {r[1]:<12} {r[2]:<6} {r[3]:<8}")
        else:
            print("  crawl_progress 表为空（暂无数据）")

except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
finally:
    conn.close()

print("=" * 60)
print("迁移完成")
