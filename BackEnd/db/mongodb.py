"""
db/mongodb.py

MongoDB 异步连接池管理与基础操作封装。
升级点：
    1. 封装参数化CRUD方法，杜绝NoSQL注入
    2. 封装分页/排序/过滤查询，强制参数化
    3. 增加查询条件校验，禁止恶意操作符
    4. 完善异常处理与日志
"""

import logging
from typing import Optional, Dict, List, Any, Tuple

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo.errors import PyMongoError, OperationFailure
from pymongo import ASCENDING, DESCENDING

from config import get_mongo_config

logger = logging.getLogger(__name__)

# 全局客户端实例
_mongo_client: Optional[AsyncIOMotorClient] = None
# 默认数据库对象（可直接使用）
_mongo_db: Optional[AsyncIOMotorDatabase] = None

# 禁止的查询操作符（防止NoSQL注入）
FORBIDDEN_OPERATORS = {"$where", "$expr"}


def _validate_query(query: Dict[str, Any]) -> Dict[str, Any]:
    """
    校验查询条件，禁止恶意操作符，防止NoSQL注入
    """
    if not isinstance(query, dict):
        raise ValueError("查询条件必须为字典类型")
    
    # 递归检查所有键，禁止危险操作符
    def _recursive_check(data: Any):
        if isinstance(data, dict):
            for key in data.keys():
                if key.startswith("$") and key in FORBIDDEN_OPERATORS:
                    raise ValueError(f"禁止使用危险操作符: {key}")
                _recursive_check(data[key])
        elif isinstance(data, list):
            for item in data:
                _recursive_check(item)
    
    _recursive_check(query)
    return query


async def init_mongodb():
    """
    初始化 MongoDB 客户端（含连接池）。
    升级：增加重试逻辑，完善异常日志
    """
    global _mongo_client, _mongo_db

    # 构建连接 URI
    if get_mongo_config().user and get_mongo_config().password:
        uri = (
            f"mongodb://{get_mongo_config().user}:{get_mongo_config().password}"
            f"@{get_mongo_config().host}:{get_mongo_config().port}"
            f"/?authSource=admin"
        )
    else:
        uri = f"mongodb://{get_mongo_config().host}:{get_mongo_config().port}"

    logger.info(f"初始化 MongoDB 客户端: {get_mongo_config().host}:{get_mongo_config().port}/{get_mongo_config().database}")
    retry_times = 3
    for retry in range(retry_times):
        try:
            _mongo_client = AsyncIOMotorClient(
                uri,
                minPoolSize=get_mongo_config().min_pool_size,
                maxPoolSize=get_mongo_config().max_pool_size,
                connectTimeoutMS=get_mongo_config().connect_timeout_ms,
                retryWrites=True,  # 开启写重试
            )
            _mongo_db = _mongo_client[get_mongo_config().database]

            # 测试连接
            await _mongo_client.admin.command("ping")
            logger.info("MongoDB 客户端初始化成功")
            return
        except PyMongoError as e:
            logger.warning(f"MongoDB 初始化重试 {retry+1}/{retry_times} 失败: {e}")
            if retry == retry_times - 1:
                logger.error("MongoDB 初始化最终失败")
                raise


async def close_mongodb():
    """
    关闭 MongoDB 客户端。
    升级：增加异常捕获
    """
    global _mongo_client, _mongo_db
    if _mongo_client:
        try:
            _mongo_client.close()
            _mongo_client = None
            _mongo_db = None
            logger.info("MongoDB 客户端已关闭")
        except PyMongoError as e:
            logger.error(f"关闭 MongoDB 客户端失败: {e}")


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


def get_collection(collection_name: str) -> AsyncIOMotorCollection:
    """
    获取集合对象（封装，便于统一管理）
    """
    db = get_mongodb()
    if not isinstance(collection_name, str) or not collection_name:
        raise ValueError("集合名称必须为非空字符串")
    return db[collection_name]


# ==================== 基础CRUD封装（参数化，防注入） ====================

async def mongo_find(
    collection_name: str,
    query: Dict[str, Any] = None,
    projection: Dict[str, Any] = None,
    sort: List[Tuple[str, int]] = None,
    page: int = 1,
    page_size: int = 20
) -> Tuple[List[Dict[str, Any]], int]:
    """
    分页查询集合数据（参数化，防NoSQL注入）
    """
    # 校验参数
    query = _validate_query(query or {})
    if page < 1:
        raise ValueError("页码必须大于等于1")
    if page_size < 1 or page_size > 100:
        raise ValueError("每页条数必须在1-100之间")
    
    collection = get_collection(collection_name)
    try:
        # 总条数
        total = await collection.count_documents(query)
        
        # 分页查询
        cursor = collection.find(query, projection or {})
        # 排序（默认按_id降序）
        if sort:
            cursor = cursor.sort(sort)
        else:
            cursor = cursor.sort([("_id", DESCENDING)])
        # 分页
        cursor = cursor.skip((page - 1) * page_size).limit(page_size)
        
        # 获取数据
        data = await cursor.to_list(length=page_size)
        return data, total
    except OperationFailure as e:
        logger.error(f"MongoDB 查询失败（权限/语法）: collection={collection_name}, query={query}, error={e}")
        raise
    except PyMongoError as e:
        logger.error(f"MongoDB 查询失败: collection={collection_name}, query={query}, error={e}")
        raise


async def mongo_find_one(
    collection_name: str,
    query: Dict[str, Any] = None,
    projection: Dict[str, Any] = None
) -> Optional[Dict[str, Any]]:
    """
    查询单条数据（参数化，防NoSQL注入）
    """
    query = _validate_query(query or {})
    collection = get_collection(collection_name)
    try:
        return await collection.find_one(query, projection or {})
    except PyMongoError as e:
        logger.error(f"MongoDB 查询单条失败: collection={collection_name}, query={query}, error={e}")
        raise


async def mongo_insert_one(
    collection_name: str,
    document: Dict[str, Any]
) -> str:
    """
    插入单条数据
    """
    if not isinstance(document, dict):
        raise ValueError("插入文档必须为字典类型")
    collection = get_collection(collection_name)
    try:
        result = await collection.insert_one(document)
        logger.debug(f"插入MongoDB成功: collection={collection_name}, id={result.inserted_id}")
        return str(result.inserted_id)
    except PyMongoError as e:
        logger.error(f"MongoDB 插入失败: collection={collection_name}, document={document}, error={e}")
        raise


async def mongo_update_one(
    collection_name: str,
    query: Dict[str, Any],
    update: Dict[str, Any],
    upsert: bool = False
) -> int:
    """
    更新单条数据（强制使用$set等操作符，防止全文档覆盖）
    """
    query = _validate_query(query or {})
    # 校验更新操作必须包含$set/$unset等操作符，防止全文档覆盖
    if not update or not any(key.startswith("$") for key in update.keys()):
        raise ValueError("更新操作必须使用$set/$unset等操作符（禁止全文档覆盖）")
    
    collection = get_collection(collection_name)
    try:
        result = await collection.update_one(query, update, upsert=upsert)
        logger.debug(f"MongoDB 更新成功: collection={collection_name}, matched={result.matched_count}, modified={result.modified_count}")
        return result.modified_count
    except PyMongoError as e:
        logger.error(f"MongoDB 更新失败: collection={collection_name}, query={query}, update={update}, error={e}")
        raise

async def mongo_insert_many(
    collection_name: str,
    documents: List[Dict[str, Any]]
) -> List[str]:
    """
    批量插入多条文档
    """
    if not isinstance(documents, list):
        raise ValueError("documents 必须为列表类型")
    if not documents:
        return []
    for doc in documents:
        if not isinstance(doc, dict):
            raise ValueError("列表中每个元素必须为字典类型")

    collection = get_collection(collection_name)
    try:
        result = await collection.insert_many(documents)
        logger.debug(f"批量插入成功: collection={collection_name}, count={len(result.inserted_ids)}")
        return [str(oid) for oid in result.inserted_ids]
    except PyMongoError as e:
        logger.error(f"MongoDB 批量插入失败: collection={collection_name}, error={e}")
        raise


async def mongo_delete_one(
    collection_name: str,
    query: Dict[str, Any]
) -> int:
    """
    删除单条数据（参数化，防误删）
    """
    query = _validate_query(query or {})
    # 禁止空查询（防止删除全表）
    if not query:
        raise ValueError("删除操作禁止空查询（防止误删全表）")
    
    collection = get_collection(collection_name)
    try:
        result = await collection.delete_one(query)
        logger.debug(f"MongoDB 删除成功: collection={collection_name}, deleted={result.deleted_count}")
        return result.deleted_count
    except PyMongoError as e:
        logger.error(f"MongoDB 删除失败: collection={collection_name}, query={query}, error={e}")
        raise