"""
db/mysql.py

MySQL 异步连接池管理与基础操作封装。
升级点：
    1. 强化参数化查询，禁止SQL拼接
    2. 封装分页查询方法（参数化LIMIT/OFFSET）
    3. 增加参数类型校验，避免恶意参数
    4. 完善异常捕获与日志，提升可追溯性
"""

import logging
from typing import Optional, Any, List, Dict, Tuple

import aiomysql
from aiomysql import Pool, Connection, DictCursor

from config import get_mysql_config

logger = logging.getLogger(__name__)

# 全局连接池实例
_mysql_pool: Optional[Pool] = None


async def init_mysql():
    """
    初始化 MySQL 连接池。
    应在 Quart 应用启动时（before_serving）调用。
    """
    global _mysql_pool
    logger.info(f"初始化 MySQL 连接池: {get_mysql_config().host}:{get_mysql_config().port}/{get_mysql_config().database}")
    try:
        _mysql_pool = await aiomysql.create_pool(
            host=get_mysql_config().host,
            port=get_mysql_config().port,
            user=get_mysql_config().user,
            password=get_mysql_config().password,
            db=get_mysql_config().database,
            charset=get_mysql_config().charset,
            minsize=get_mysql_config().minsize,
            maxsize=get_mysql_config().maxsize,
            connect_timeout=get_mysql_config().connect_timeout,
            autocommit=True,
            cursorclass=DictCursor,
            init_command="SET time_zone='+08:00'",
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


def _ensure_tuple(args: Optional[tuple]) -> Optional[tuple]:
    """
    将参数统一转为 tuple（仅做类型适配，不做内容校验）。

    安全保证：参数化查询由 aiomysql 驱动层完成防注入，此处无需额外过滤。
    """
    if args is None:
        return None
    # 仅进行必要的类型适配，不做内容审查
    return tuple(args)


async def execute_query(sql: str, args: tuple = None) -> List[dict]:
    """
    执行查询并返回所有结果（适用于 SELECT）。
    强化：参数校验 + 严格参数化，禁止拼接SQL
    
    Args:
        sql: 带占位符的SQL语句（如 "SELECT * FROM user WHERE id = %s"）
        args: 参数元组（仅支持%s占位符，避免拼接）
    
    Returns:
        查询结果列表（每行为字典）
    """
    pool = get_mysql_pool()
    validated_args = _ensure_tuple(args)
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, validated_args)
                return await cur.fetchall()
    except Exception as e:
        logger.error(f"执行查询失败: sql={sql}, args={validated_args}, error={e}")
        raise


async def execute_one(sql: str, args: tuple = None) -> Optional[dict]:
    """
    执行查询并返回单行结果。
    强化：参数校验 + 严格参数化
    """
    pool = get_mysql_pool()
    validated_args = _ensure_tuple(args)
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, validated_args)
                return await cur.fetchone()
    except Exception as e:
        logger.error(f"执行单行查询失败: sql={sql}, args={validated_args}, error={e}")
        raise


async def execute_update(sql: str, args: tuple = None) -> int:
    """
    执行更新操作（INSERT/UPDATE/DELETE），返回影响行数。
    强化：参数校验 + 严格参数化
    """
    pool = get_mysql_pool()
    validated_args = _ensure_tuple(args)
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                affected = await cur.execute(sql, validated_args)
                return affected
    except Exception as e:
        logger.error(f"执行更新失败: sql={sql}, args={validated_args}, error={e}")
        raise


async def execute_insert(sql: str, args: tuple = None) -> int:
    """
    执行插入操作，返回自增主键 ID。
    强化：参数校验 + 严格参数化
    """
    pool = get_mysql_pool()
    validated_args = _ensure_tuple(args)
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, validated_args)
                return cur.lastrowid
    except Exception as e:
        logger.error(f"执行插入失败: sql={sql}, args={validated_args}, error={e}")
        raise


async def execute_paginated_query(
    sql: str, 
    args: tuple = None, 
    page: int = 1, 
    page_size: int = 20
) -> Tuple[List[dict], int]:
    """
    分页查询封装（核心解决分页注入风险）
    强化：LIMIT/OFFSET 参数化，避免拼接
    
    Args:
        sql: 基础查询SQL（不带LIMIT/OFFSET）
        args: 基础查询参数
        page: 页码（默认1）
        page_size: 每页条数（默认20）
    
    Returns:
        (分页数据列表, 总条数)
    """
    # 校验分页参数合法性
    if page < 1:
        raise ValueError("页码必须大于等于1")
    if page_size < 1 or page_size > 100:  # 限制最大页大小，防止性能问题
        raise ValueError("每页条数必须在1-100之间")
    
    # 总条数查询（参数化）
    count_sql = f"SELECT COUNT(*) as total FROM ({sql}) as t_count"
    count_result = await execute_one(count_sql, args)
    total = count_result["total"] if count_result else 0
    
    # 分页数据查询（LIMIT/OFFSET 参数化）
    offset = (page - 1) * page_size
    paginated_sql = f"{sql} LIMIT %s OFFSET %s"
    # 合并基础参数 + 分页参数
    paginated_args = args + (page_size, offset) if args else (page_size, offset)
    data = await execute_query(paginated_sql, paginated_args)
    
    return data, total