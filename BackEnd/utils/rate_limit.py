"""
utils/rate_limit.py

基于 Redis 计数器的频率限制。

依赖分层说明：
    入参标注用 DatabaseLayerV2（统一入口风格），
    底层的 increment_counter/get_counter 实际由 DatabaseLayerV2 代理到 db.redis 模块，
    rate_limit.py 内部直接用 get_redis() 写事件记录，形成两层依赖。
    此为有意设计 — limit 逻辑层与审计事件层分离。

使用方式：
    from quart import current_app
    from utils.rate_limit import check_rate_limit

    # 登录限流：同一 IP 每分钟最多 5 次
    await check_rate_limit(
        db=current_app.services.db,
        key_prefix="ratelimit:login",
        identifier=request.remote_addr,
        max_requests=5,
        window_seconds=60,
    )

实现原理：
    Redis key = "{key_prefix}:{identifier}"
    每次请求 INCR + 首次 EXPIRE（原子 pipeline）
    INCR 返回值 > max_requests → 抛 TooManyRequestsError (429)

优雅降级：
    Redis 未初始化时静默跳过限流（日志 WARNING 提示），
    不阻塞请求——适用于测试环境或 Redis 临时不可用。
"""

import json
import logging
import time

from db.database_v2 import DatabaseLayerV2
from db.redis import get_redis
from utils.errors import TooManyRequestsError

logger = logging.getLogger(__name__)


async def check_rate_limit(
    db: DatabaseLayerV2,
    key_prefix: str,
    identifier: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    """
    检查频率限制。

    输入：
        db:              DatabaseLayerV2 实例
        key_prefix:      Redis key 前缀（如 "ratelimit:login"）
        identifier:      唯一标识（如 IP 地址）
        max_requests:    时间窗口内最大请求数
        window_seconds:  时间窗口长度（秒）

    行为：
        请求合法（计数 <= max_requests） → 静默返回 None
        超限（计数 >  max_requests）     → 抛 TooManyRequestsError (429)
        Redis 不可达                      → 静默跳过（WARNING 日志）

    副作用：
        INCR ratelimit:xxx:yyy（首次写入同时 EXPIRE）
    """
    key = f"{key_prefix}:{identifier}"
    try:
        count = await db.increment_counter(key=key, ttl=window_seconds)
    except (RuntimeError, ConnectionError, OSError) as e:
        logger.warning(f"限流计数器不可用（Redis 未初始化？），跳过限流: {e}")
        return

    if count > max_requests:
        try:
            endpoint = key_prefix.replace("ratelimit:", "")
            event = json.dumps({
                "identifier": identifier,
                "count": count,
                "max_requests": max_requests,
                "window_seconds": window_seconds,
                "ts": time.time(),
            })
            redis_client = get_redis()
            if redis_client:
                pipe = redis_client.pipeline()
                pipe.zadd(f"ratelimit:events:{endpoint}", {event: time.time()})
                pipe.expire(f"ratelimit:events:{endpoint}", 86400)
                try:
                    await pipe.execute()
                except Exception:
                    pass  # zadd 成功但 expire 失败：仅短窗口丢失 TTL，不影响功能
        except Exception:
            pass  # 事件记录失败不影响限流结果

        raise TooManyRequestsError(
            f"请求频率超限，请在 {window_seconds} 秒后重试",
            "RATE_LIMITED",
        )
