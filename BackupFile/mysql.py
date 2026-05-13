"""
db/mysql.py

MySQL 异步连接池管理与基础操作封装。
提供：
    - 连接池初始化与关闭
    - 获取连接（从池中获取）
    - 基础执行方法（简化上层代码）
"""

import logging
from typing import Optional, Any, List

import aiomysql
from aiomysql import Pool, Connection, DictCursor

from config import mysql_config

logger = logging.getLogger(__name__)

# 全局连接池实例
_mysql_pool: Optional[Pool] = None


async def init_mysql():
    """
    初始化 MySQL 连接池。
    应在 Quart 应用启动时（before_serving）调用。
    """
    global _mysql_pool
    logger.info(f"初始化 MySQL 连接池: {mysql_config.host}:{mysql_config.port}/{mysql_config.database}")
    try:
        _mysql_pool = await aiomysql.create_pool(
            host=mysql_config.host,
            port=mysql_config.port,
            user=mysql_config.user,
            password=mysql_config.password,
            db=mysql_config.database,
            charset=mysql_config.charset,
            minsize=mysql_config.minsize,
            maxsize=mysql_config.maxsize,
            connect_timeout=mysql_config.connect_timeout,
            autocommit=True,          # 默认自动提交，简化使用
            cursorclass=DictCursor,   # 返回字典格式，便于处理
        )
        # 测试连接
        async with _mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
        logger.info("MySQL 连接池初始化成功")
    except Exception as e:
        logger.error(f"MySQL 连接池初始化失败: {e}")
        raise


async def close_mysql():
    """
    关闭 MySQL 连接池。
    应在 Quart 应用关闭时（after_serving）调用。
    """
    global _mysql_pool
    if _mysql_pool:
        _mysql_pool.close()
        await _mysql_pool.wait_closed()
        _mysql_pool = None
        logger.info("MySQL 连接池已关闭")


def get_mysql_pool() -> Pool:
    """
    获取 MySQL 连接池实例。
    若未初始化则抛出异常。
    """
    if _mysql_pool is None:
        raise RuntimeError("MySQL 连接池未初始化，请先调用 init_mysql()")
    return _mysql_pool


async def execute_query(sql: str, args: tuple = None) -> List[dict]:
    """
    执行查询并返回所有结果（适用于 SELECT）。
    
    Args:
        sql: SQL 语句
        args: 参数元组
    
    Returns:
        查询结果列表（每行为字典）
    """
    pool = get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            return await cur.fetchall()


async def execute_one(sql: str, args: tuple = None) -> Optional[dict]:
    """
    执行查询并返回单行结果。
    """
    pool = get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            return await cur.fetchone()


async def execute_update(sql: str, args: tuple = None) -> int:
    """
    执行更新操作（INSERT/UPDATE/DELETE），返回影响行数。
    """
    pool = get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            affected = await cur.execute(sql, args)
            return affected


async def execute_insert(sql: str, args: tuple = None) -> int:
    """
    执行插入操作，返回自增主键 ID。
    """
    pool = get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            return cur.lastrowid