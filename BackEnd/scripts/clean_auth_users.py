"""
scripts/clean_auth_users.py

清理认证相关用户数据（users + user_permissions）。

用途：
    开发过程中会产生大量测试用户，用此脚本一键清理，
    同时保留种子超级管理员（username='admin'）。

MySQL 删除顺序（外键约束）：
    1. user_permissions 有 ON DELETE CASCADE，随 users 自动删除
    2. 直接 DELETE FROM users WHERE username != 'admin'

保留数据：
    admin 用户及其权限
    permissions 表（权限定义）
    task_failures（失败任务日志，admin_id 只是数值引用，无外键约束）

用法：
    python scripts/clean_auth_users.py
    python scripts/clean_auth_users.py --dry-run   # 只看不删
"""

import asyncio
import logging
import sys
import os

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)
os.chdir(_BACKEND_DIR)

from db.mysql import init_mysql, close_mysql, get_mysql_pool

logger = logging.getLogger(__name__)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")


async def show_users(pool) -> tuple[list[dict], int | None]:
    """列出所有用户，返回 (非 admin 用户列表, admin_id)。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, username, display_name, created_at FROM users ORDER BY id")
            rows = await cur.fetchall()
    admin_id = None
    non_admin = []
    print(f"\n{'ID':>6} {'Username':<20} {'DisplayName':<20} {'CreatedAt'}")
    print("-" * 70)
    for r in rows:
        print(f"{r['id']:>6} {r['username']:<20} {r['display_name']:<20} {r['created_at']}")
        if r["username"] == ADMIN_USERNAME:
            admin_id = r["id"]
        else:
            non_admin.append(r)
    print("-" * 70)
    suffix = f"admin(id={admin_id})" if admin_id else "无 admin"
    print(f"总计 {len(rows)} 个用户，{suffix} + {len(non_admin)} 个待清理\n")
    return non_admin, admin_id


async def count_permissions(pool, admin_id: int) -> dict:
    """统计权限分布。"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS total FROM user_permissions")
            total = (await cur.fetchone())["total"]
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM user_permissions WHERE user_id = %s",
                (admin_id,),
            )
            admin_perm = (await cur.fetchone())["cnt"]
    return {"total": total, "admin": admin_perm, "others": total - admin_perm}


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    dry_run = "--dry-run" in sys.argv

    logger.info("=" * 50)
    logger.info("清理认证用户数据")
    logger.info(f"模式: {'[只读预览] (--dry-run)' if dry_run else '[执行清理]'}")
    logger.info("=" * 50)

    await init_mysql()
    pool = get_mysql_pool()

    non_admin, admin_id = await show_users(pool)

    if admin_id:
        perm = await count_permissions(pool, admin_id)
        print(f"权限分布: {perm['total']} 条总权限, admin 拥有 {perm['admin']} 条, 其他用户 {perm['others']} 条\n")
    else:
        print("[警告] 未找到 admin 用户，将清理所有用户\n")

    if not non_admin:
        logger.info("没有需要清理的非 admin 用户")
        await close_mysql()
        return

    if dry_run:
        logger.info("预览完成。不加 --dry-run 即可执行清理。")
        await close_mysql()
        return

    # ── 执行清理 ──
    logger.info(f"清理 {len(non_admin)} 个非 admin 用户...")
    user_ids = [r["id"] for r in non_admin]

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(user_ids))
            await cur.execute(
                f"DELETE FROM users WHERE id IN ({placeholders}) AND username != %s",
                (*user_ids, ADMIN_USERNAME),
            )
            deleted_users = cur.rowcount
            logger.info(f"  users 表: 删除 {deleted_users} 行（CASCADE 自动清理 user_permissions）")

            await cur.execute(
                "SELECT COUNT(*) AS remaining FROM user_permissions "
                "WHERE user_id IN (SELECT id FROM users)"
            )
            remaining_perm = (await cur.fetchone())["remaining"]
            logger.info(f"  user_permissions 剩余: {remaining_perm} 行（仅 admin）")

            await cur.execute("SELECT COUNT(*) AS remaining FROM users")
            remaining_users = (await cur.fetchone())["remaining"]
            logger.info(f"  users 剩余: {remaining_users} 行（仅 admin）")

    await close_mysql()

    print()
    logger.info("=" * 50)
    logger.info(f"清理完成，保留 {remaining_users} 个用户（admin），{remaining_perm} 条权限")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
