"""
db/redis.py

Redis 异步连接池管理与基础操作封装。
提供：
    - 连接池初始化与关闭
    - 获取 Redis 客户端单例
    - 封装延迟队列相关操作（添加任务、批量弹出到期任务等）
"""

import logging
from typing import Optional, List

import redis.asyncio as redis
from redis.asyncio import Redis

from config import redis_config

logger = logging.getLogger(__name__)

# 全局 Redis 客户端实例（连接池）
_redis_client: Optional[Redis] = None

# Lua 脚本：原子批量弹出到期的任务
LUA_BATCH_POP = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

local members = redis.call('ZRANGEBYSCORE', key, '-inf', now, 'LIMIT', 0, limit)
if #members > 0 then
    redis.call('ZREM', key, unpack(members))
end
return members
"""


async def init_redis():
    """
    初始化 Redis 连接池。
    应在 Quart 应用启动时（before_serving）调用。
    """
    global _redis_client
    logger.info(f"初始化 Redis 连接池: {redis_config.host}:{redis_config.port}/{redis_config.db}")
    try:
        _redis_client = await redis.from_url(
            f"redis://{redis_config.host}:{redis_config.port}/{redis_config.db}",
            password=redis_config.password,
            max_connections=redis_config.maxsize,
            socket_timeout=redis_config.socket_timeout,
            decode_responses=True,
        )
        await _redis_client.ping()
        logger.info("Redis 连接池初始化成功")
    except Exception as e:
        logger.error(f"Redis 连接池初始化失败: {e}")
        raise


async def close_redis():
    """
    关闭 Redis 连接池。
    应在 Quart 应用关闭时（after_serving）调用。
    """
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis 连接池已关闭")


def get_redis() -> Redis:
    """
    获取 Redis 客户端实例。
    """
    if _redis_client is None:
        raise RuntimeError("Redis 连接池未初始化，请先调用 init_redis()")
    return _redis_client


# ==================== 延迟队列相关操作 ====================

async def add_delayed_task(task_json: str, execute_at: float) -> int:
    """向延迟队列添加任务"""
    client = get_redis()
    added = await client.zadd(redis_config.delay_queue_key, {task_json: execute_at})
    logger.debug(f"任务已加入延迟队列: score={execute_at}")
    return added


async def batch_pop_due_tasks(now: float, limit: int) -> List[str]:
    """原子批量弹出到期任务，返回任务 JSON 字符串列表"""
    client = get_redis()
    members = await client.eval(
        LUA_BATCH_POP,
        1,
        redis_config.delay_queue_key,
        now,
        limit,
    )
    return members if members else []


async def get_earliest_score() -> Optional[float]:
    """获取延迟队列中最早任务的 score，队列为空返回 None"""
    client = get_redis()
    result = await client.zrange(redis_config.delay_queue_key, 0, 0, withscores=True)
    if result:
        return result[0][1]
    return None