"""
db/__init__.py

数据库模块统一入口，方便其他模块导入。
"""

# 底层驱动
from .mysql import (
    init_mysql, close_mysql, get_mysql_pool,
    execute_query, execute_one, execute_update, execute_insert,
    execute_paginated_query,
)
from .redis import (
    init_redis, close_redis, get_redis,
    add_delayed_task, add_delayed_task_with_limit,
    batch_pop_due_tasks, get_earliest_score,
    redis_incr_expire, redis_get, redis_setex, redis_set, redis_delete,
)
from .mongodb import (
    init_mongodb, close_mongodb, get_mongodb, get_mongo_client,
    mongo_find, mongo_find_one,
    mongo_insert_one, mongo_update_one, mongo_delete_one,
)

# 数据库中间层（V2 — 生产代码使用）
from .database_v2 import DatabaseLayerV2, TransactionContext, DatabaseType
from .query_builder import ConditionBuilder, QueryBuilder

# 旧版（仅测试/脚本引用，DEPRECATED）
from .database import DatabaseLayer

__all__ = [
    # MySQL
    "init_mysql", "close_mysql", "get_mysql_pool",
    "execute_query", "execute_one", "execute_update", "execute_insert",
    "execute_paginated_query",
    # Redis
    "init_redis", "close_redis", "get_redis",
    "add_delayed_task", "add_delayed_task_with_limit",
    "batch_pop_due_tasks", "get_earliest_score",
    "redis_incr_expire", "redis_get", "redis_setex", "redis_set", "redis_delete",
    # MongoDB
    "init_mongodb", "close_mongodb", "get_mongodb", "get_mongo_client",
    "mongo_find", "mongo_find_one",
    "mongo_insert_one", "mongo_update_one", "mongo_delete_one",
    # 中间层
    "DatabaseLayerV2", "TransactionContext", "DatabaseType",
    "ConditionBuilder", "QueryBuilder",
    # 旧版
    "DatabaseLayer",
]
