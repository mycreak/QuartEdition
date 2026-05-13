import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from db import init_mysql, close_mysql
from db.database import DatabaseLayer

TABLES = [
    "movies", "people", "regions",
    "movie_ratings", "movie_genres", "movie_regions", "movie_credits",
]

async def main():
    await init_mysql()
    db = DatabaseLayer()
    await db.initialize("mysql")

    print("=" * 90)
    print("  movie_db 表结构审计报告")
    print("=" * 90)

    for t in TABLES:
        cols = await db.execute_raw(f"SHOW FULL COLUMNS FROM `{t}`")
        print(f"\n{'─' * 90}")
        print(f"  表: {t}")
        print(f"  {'列名':22s} {'类型':16s} {'可空':5s} {'键':6s} {'默认值':14s} {'额外':12s} {'注释'}")
        print(f"  {'─' * 22} {'─' * 16} {'─' * 5} {'─' * 6} {'─' * 14} {'─' * 12} {'─' * 20}")
        for c in cols:
            field = c["Field"]
            col_type = c["Type"]
            nullable = "YES" if c["Null"] == "YES" else "NO"
            key = c["Key"]
            default = str(c["Default"]) if c["Default"] is not None else "NULL"
            extra = c["Extra"]
            comment = c["Comment"]
            print(f"  {field:22s} {col_type:16s} {nullable:5s} {key:6s} {default:14s} {extra:12s} {comment}")

    print(f"\n{'─' * 90}")
    print("  审计完成 — 共 8 张表")
    print(f"{'─' * 90}")

    await close_mysql()

asyncio.run(main())
