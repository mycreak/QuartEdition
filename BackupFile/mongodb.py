"""
db/mongodb.py

MongoDB 异步连接池管理与基础操作封装。
Motor 驱动自身已内置连接池，只需管理客户端生命周期。
提供：
    - 客户端初始化与关闭
    - 获取数据库对象
"""

import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import mongo_config

logger = logging.getLogger(__name__)

# 全局客户端实例
_mongo_client: Optional[AsyncIOMotorClient] = None
# 默认数据库对象（可直接使用）
_mongo_db: Optional[AsyncIOMotorDatabase] = None


async def init_mongodb():
    """
    初始化 MongoDB 客户端（含连接池）。
    应在 Quart 应用启动时（before_serving）调用。
    """
    global _mongo_client, _mongo_db

    # 构建连接 URI
    if mongo_config.user and mongo_config.password:
        uri = (
            f"mongodb://{mongo_config.user}:{mongo_config.password}"
            f"@{mongo_config.host}:{mongo_config.port}"
            f"/?authSource=admin"
        )
    else:
        uri = f"mongodb://{mongo_config.host}:{mongo_config.port}"

    logger.info(f"初始化 MongoDB 客户端: {mongo_config.host}:{mongo_config.port}/{mongo_config.database}")

    try:
        _mongo_client = AsyncIOMotorClient(
            uri,
            minPoolSize=mongo_config.min_pool_size,
            maxPoolSize=mongo_config.max_pool_size,
            connectTimeoutMS=mongo_config.connect_timeout_ms,
        )
        _mongo_db = _mongo_client[mongo_config.database]

        # 测试连接
        await _mongo_client.admin.command("ping")
        logger.info("MongoDB 客户端初始化成功")
    except Exception as e:
        logger.error(f"MongoDB 初始化失败: {e}")
        raise


async def close_mongodb():
    """
    关闭 MongoDB 客户端。
    应在 Quart 应用关闭时（after_serving）调用。
    """
    global _mongo_client, _mongo_db
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
        _mongo_db = None
        logger.info("MongoDB 客户端已关闭")


def get_mongodb() -> AsyncIOMotorDatabase:
    """
    获取 MongoDB 数据库对象。
    若未初始化则抛出异常。
    """
    if _mongo_db is None:
        raise RuntimeError("MongoDB 未初始化，请先调用 init_mongodb()")
    return _mongo_db


def get_mongo_client() -> AsyncIOMotorClient:
    """
    获取 MongoDB 客户端实例（用于高级操作）。
    """
    if _mongo_client is None:
        raise RuntimeError("MongoDB 未初始化，请先调用 init_mongodb()")
    return _mongo_client