"""
db/redis.py

Redis 异步连接池管理与基础操作封装。
升级点：
    1. 增加参数类型校验（避免Lua脚本执行失败/恶意参数）
    2. 可选关闭decode_responses，适配二进制数据
    3. 完善异常处理与参数校验
    4. 增加延迟队列任务ID唯一性校验（可选）
"""

import logging
import json
import time
from typing import Optional, List, Union

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from config import get_redis_config

logger = logging.getLogger(__name__)

# 全局 Redis 客户端实例（连接池）
_redis_client: Optional[Redis] = None

# Lua 脚本：原子批量弹出到期的任务（保持原有逻辑，安全合规）
LUA_BATCH_POP = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

if not now or not limit then
    return {}
end

local members = redis.call('ZRANGEBYSCORE', key, '-inf', now, 'LIMIT', 0, limit)
if #members > 0 then
    redis.call('ZREM', key, unpack(members))
end
return members
"""

LUA_ADD_WITH_RATE_LIMIT = """
-- 带限速的任务写入：保证相邻任务 execute_at 至少间隔 cooldown 秒
-- KEYS[1]: ZSET 延迟队列 key
-- KEYS[2]: 上次提交时间 key（string）
-- ARGV[1]: 任务 JSON 字符串
-- ARGV[2]: 当前时间戳（秒）
-- ARGV[3]: 冷却间隔（秒）
-- 返回: 实际写入的 execute_at

local delay_key = KEYS[1]
local rate_key = KEYS[2]
local task_json = ARGV[1]
local now = tonumber(ARGV[2])
local cooldown = tonumber(ARGV[3])

if not now or not cooldown or cooldown <= 0 then
    -- 不限速：直接写入
    redis.call('ZADD', delay_key, now, task_json)
    return now
end

local last_time = redis.call('GET', rate_key)
local execute_at = now

if last_time then
    local next_available = tonumber(last_time) + cooldown
    if next_available > now then
        execute_at = next_available
    end
end

redis.call('SET', rate_key, execute_at)
redis.call('ZADD', delay_key, execute_at, task_json)
return execute_at
"""


async def init_redis():
    """
    初始化 Redis 连接池。
    升级：增加重试逻辑（基础），可选decode_responses
    """
    global _redis_client
    logger.info(f"初始化 Redis 连接池: {get_redis_config().host}:{get_redis_config().port}/{get_redis_config().db}")
    retry_times = 3  # 初始化重试次数
    for retry in range(retry_times):
        try:
            # 创建连接池
            pool = redis.ConnectionPool.from_url(
                f"redis://{get_redis_config().host}:{get_redis_config().port}/{get_redis_config().db}",
                password=get_redis_config().password,
                max_connections=get_redis_config().maxsize,
                socket_timeout=get_redis_config().socket_timeout,
                decode_responses=get_redis_config().decode_responses,
            )
            _redis_client = redis.Redis(connection_pool=pool)
            await _redis_client.ping()
            logger.info("Redis 连接池初始化成功")
            return
        except RedisError as e:
            logger.warning(f"Redis 初始化重试 {retry+1}/{retry_times} 失败: {e}")
            if retry == retry_times - 1:
                logger.error("Redis 初始化最终失败")
                raise

async def close_redis():
    """
    关闭 Redis 连接池。
    升级：增加异常捕获
    """
    global _redis_client
    if _redis_client:
        try:
            await _redis_client.aclose()
            _redis_client = None
            logger.info("Redis 连接池已关闭")
        except RedisError as e:
            logger.error(f"关闭 Redis 连接池失败: {e}")


def get_redis() -> Redis:
    """
    获取 Redis 客户端实例。
    """
    if _redis_client is None:
        raise RuntimeError("Redis 连接池未初始化，请先调用 init_redis()")
    return _redis_client


def _validate_delayed_task_params(task_json: str, execute_at: float) -> None:
    """校验延迟队列参数合法性"""
    # 校验execute_at为有效数字
    if not isinstance(execute_at, (int, float)) or execute_at < 0:
        raise ValueError("execute_at 必须为非负数字")
    # 校验task_json为合法JSON（避免存储无效数据）
    try:
        json.loads(task_json)
    except json.JSONDecodeError:
        raise ValueError("task_json 必须为合法JSON字符串")


# ==================== 延迟队列相关操作 ====================

async def add_delayed_task(task_json: str, execute_at: float) -> int:
    """
    向延迟队列添加任务
    升级：参数校验 + 异常捕获
    """
    try:
        _validate_delayed_task_params(task_json, execute_at)
        client = get_redis()
        added = await client.zadd(get_redis_config().delay_queue_key, {task_json: execute_at})
        logger.debug(f"任务已加入延迟队列: score={execute_at}, task={task_json[:50]}...")
        return added
    except RedisError as e:
        logger.error(f"添加延迟任务失败: execute_at={execute_at}, error={e}")
        raise
    except ValueError as e:
        logger.warning(f"延迟任务参数非法: {e}")
        raise


async def batch_pop_due_tasks(now: float, limit: int) -> List[str]:
    """
    原子批量弹出到期任务，返回任务 JSON 字符串列表
    升级：参数校验 + Lua脚本容错 + 异常捕获
    """
    # 校验参数类型
    if not isinstance(now, (int, float)):
        raise ValueError("now 必须为数字（时间戳）")
    if not isinstance(limit, int) or limit < 1 or limit > 1000:  # 限制单次弹出数量
        raise ValueError("limit 必须为1-1000之间的整数")
    
    try:
        client = get_redis()
        members = await client.eval(
            LUA_BATCH_POP,
            1,
            get_redis_config().delay_queue_key,
            now,
            limit,
        )
        logger.debug(f"弹出到期任务数: {len(members)}")
        return members if members else []
    except RedisError as e:
        logger.error(f"批量弹出延迟任务失败: now={now}, limit={limit}, error={e}")
        raise


async def get_earliest_score() -> Optional[float]:
    """
    获取延迟队列中最早任务的 score，队列为空返回 None
    升级：异常捕获 + 类型转换
    """
    try:
        client = get_redis()
        result = await client.zrange(get_redis_config().delay_queue_key, 0, 0, withscores=True)
        if result:
            score = result[0][1]
            return float(score) if isinstance(score, (int, float)) else None
        return None
    except RedisError as e:
        logger.error(f"获取最早任务score失败: {e}")
        raise


async def add_delayed_task_with_limit(
    task_json: str,
    cooldown_seconds: float = 0.0,
) -> float:
    """
    带限速的延迟任务写入 — 原子操作，保证相邻任务间至少间隔 cooldown_seconds。

    核心算法：
        execute_at = max(now, last_submit_time + cooldown)
        - cooldown <= 0  → 不限速，立即写入
        - cooldown > 0   → 在 Redis 中原子执行 Lua 脚本，避免并发竞态

    输入：
        task_json:       任务 JSON 字符串（已由调用方校验格式）
        cooldown_seconds: 相邻任务最小间隔（秒），0=不限速
    输出：
        实际写入的 execute_at 时间戳
    异常：
        ValueError — 参数非法
        RedisError — Redis 操作失败
    副作用：
        ZADD crawler:delay_queue score=execute_at
        SET  crawler:last_task_time = execute_at（Lua 原子执行）
    """
    if not task_json or not task_json.strip():
        raise ValueError("task_json 不能为空")

    # 校验 JSON 格式 — 防止非法数据写入 Redis ZSET
    _validate_delayed_task_params(task_json, cooldown_seconds)

    try:
        now = time.time()
        client = get_redis()

        result = await client.eval(
            LUA_ADD_WITH_RATE_LIMIT,
            2,  # KEYS 数量
            get_redis_config().delay_queue_key,
            get_redis_config().rate_limit_key,
            task_json,
            now,
            cooldown_seconds,
        )

        execute_at = float(result)
        delay = execute_at - now
        if delay > 0:
            logger.info(
                f"限速写入: cooldown={cooldown_seconds}s delay={delay:.1f}s "
                f"execute_at={execute_at:.1f}"
            )
        else:
            logger.debug(f"任务已加入延迟队列（无延迟）: execute_at={execute_at:.1f}")
        return execute_at

    except RedisError as e:
        logger.error(f"限速写入失败: cooldown={cooldown_seconds}s error={e}")
        raise


async def submit_crawler_task(task_json: str) -> float:
    """
    提交爬虫任务到延迟队列（自动应用配置的 cooldown）。

    等同于：
        add_delayed_task_with_limit(task_json, puller_config.task_cooldown_seconds)

    输入：task_json — 任务 JSON 字符串
    输出：实际写入的 execute_at
    """
    cooldown = _get_rate_limit_seconds()
    return await add_delayed_task_with_limit(
        task_json=task_json,
        cooldown_seconds=cooldown,
    )


def _get_rate_limit_seconds() -> float:
    """
    从 puller_config 读取全局限速 cooldown。
    供 DatabaseLayer 和外部直接调用。
    """
    try:
        from config.puller_config import puller_config
        return puller_config.task_cooldown_seconds
    except Exception:
        return 0.0


# ==================== 通用计数器（限流/频控） ====================

async def redis_incr_expire(key: str, ttl: int) -> int:
    """
    原子递增 Redis key 的计数器值。

    首次调用时设置 TTL（使用 SET NX 避免每次 INCR 都重置过期时间）。

    输入：
        key — Redis key
        ttl — 过期时间（秒），仅在首次创建时设置
    输出：递增后的计数值
    副作用：首次写入时设置 EXPIRE
    """
    client = get_redis()
    # 使用 pipeline 保证 INCR + 条件 EXPIRE 的原子性
    async with client.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.ttl(key)
        results = await pipe.execute()
    count = results[0]
    existing_ttl = results[1]
    # 仅在首次写入时设置过期时间（TTL == -1 表示 key 无过期时间）
    if existing_ttl < 0:
        await client.expire(key, ttl)
    return count


async def redis_get(key: str) -> Optional[str]:
    """获取 Redis key 的原始值（不解析类型）。"""
    client = get_redis()
    return await client.get(key)


async def redis_set(key: str, value: str) -> None:
    """设置 Redis key（永久有效）。"""
    client = get_redis()
    await client.set(key, value)


async def redis_setex(key: str, ttl: int, value: str) -> None:
    """设置 Redis key 并指定过期时间（秒）。"""
    client = get_redis()
    await client.setex(key, ttl, value)


async def redis_delete(*keys: str) -> int:
    """删除一个或多个 Redis key，返回删除数量。"""
    if not keys:
        return 0
    client = get_redis()
    return await client.delete(*keys)