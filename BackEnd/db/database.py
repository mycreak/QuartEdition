"""
db/database.py

⚠️ DEPRECATED — 请使用 database_v2.DatabaseLayerV2（新增 ContextVar + transaction 支持）。

当前状态：
    - 仅 6 处测试 + 1 处脚本引用 DatabaseLayer（非生产路径）
    - 所有生产代码已迁移至 DatabaseLayerV2
    - 迁移障碍：DatabaseLayerV2 尚缺 raw_mongodb() / raw_redis()

迁移计划（待完成）：
    1. DatabaseLayerV2 补全 raw_mongodb() / raw_redis()
    2. 测试和脚本迁移到 DatabaseLayerV2
    3. 删除本文件
"""

import asyncio
import logging
from typing import Optional, Dict, List, Any, Tuple, Union
from enum import Enum

from db.query_builder import ConditionBuilder, QueryBuilder
from db.mysql import (
    execute_query as mysql_execute_query,
    execute_one as mysql_execute_one,
    execute_update as mysql_execute_update,
    execute_insert as mysql_execute_insert,
    execute_paginated_query as mysql_execute_paginated,
    get_mysql_pool
)
from db.mongodb import (
    mongo_find as mongo_find_func,
    mongo_find_one as mongo_find_one_func,
    mongo_insert_one as mongo_insert_one_func,
    mongo_update_one as mongo_update_one_func,
    mongo_delete_one as mongo_delete_one_func,
    get_mongodb,
    get_mongo_client,
)
from db.redis import (
    get_redis,
    add_delayed_task as redis_add_delayed_task,
    batch_pop_due_tasks as redis_batch_pop_due_tasks,
    get_earliest_score as redis_get_earliest_score
)

logger = logging.getLogger(__name__)


class DatabaseType(Enum):
    """数据库类型枚举"""
    MYSQL = "mysql"
    MONGODB = "mongodb"
    REDIS = "redis"


class DatabaseLayer:
    """
    统一数据库中间层
    提供统一的 CRUD 接口，底层自动适配不同数据库
    """
    
    def __init__(self):
        self._database_type: Optional[DatabaseType] = None
        self._initialized = False
    
    async def initialize(self, database_type: str = "mysql"):
        """
        初始化中间层（指定默认数据库类型）
        
        Args:
            database_type: "mysql" | "mongodb" | "redis"
        """
        self._database_type = DatabaseType(database_type.lower())
        self._initialized = True
        
        logger.info(f"DatabaseLayer 初始化完成，默认数据库: {database_type}")
    
    def set_database(self, database_type: str):
        """
        设置当前操作的数据库类型
        
        Args:
            database_type: "mysql" | "mongodb" | "redis"
        """
        self._database_type = DatabaseType(database_type.lower())
        logger.debug(f"切换数据库类型: {database_type}")
    
    # ==================== 通用 CRUD ====================
    
    async def find(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder, QueryBuilder] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        通用查询（分页）
        
        Args:
            table: 表名/集合名
            conditions: 查询条件（字典或 ConditionBuilder/QueryBuilder）
            page: 页码
            page_size: 每页条数
        
        Returns:
            (数据列表, 总条数)
        """
        if not self._initialized:
            raise RuntimeError("DatabaseLayer 未初始化，请先调用 initialize()")
        
        if self._database_type == DatabaseType.MYSQL:
            return await self._mysql_find(table, conditions, page, page_size)
        elif self._database_type == DatabaseType.MONGODB:
            return await self._mongo_find(table, conditions, page, page_size)
        else:
            raise ValueError(f"不支持的数据库类型: {self._database_type.value}")
    
    async def find_one(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder] = None
    ) -> Optional[Dict[str, Any]]:
        """
        查询单条记录
        
        Args:
            table: 表名/集合名
            conditions: 查询条件
        
        Returns:
            单条记录或 None
        """
        if not self._initialized:
            raise RuntimeError("DatabaseLayer 未初始化，请先调用 initialize()")
        
        if self._database_type == DatabaseType.MYSQL:
            return await self._mysql_find_one(table, conditions)
        elif self._database_type == DatabaseType.MONGODB:
            return await self._mongo_find_one(table, conditions)
        else:
            raise ValueError(f"不支持的数据库类型: {self._database_type.value}")
    
    async def insert(
        self,
        table: str,
        data: Dict[str, Any],
        **kwargs
    ) -> Any:
        """
        插入记录
        
        Args:
            table: 表名/集合名
            data: 插入的数据
            **kwargs: 数据库特定参数（如 MySQL 的 return_id）
        
        Returns:
            插入的 ID 或影响行数
        """
        if not self._initialized:
            raise RuntimeError("DatabaseLayer 未初始化，请先调用 initialize()")
        
        if self._database_type == DatabaseType.MYSQL:
            return await self._mysql_insert(table, data, **kwargs)
        elif self._database_type == DatabaseType.MONGODB:
            return await self._mongo_insert(table, data, **kwargs)
        else:
            raise ValueError(f"不支持的数据库类型: {self._database_type.value}")
    
    async def update(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder],
        data: Dict[str, Any],
        upsert: bool = False,      # 新增这一行
        **kwargs
    ) -> int:
        """
        更新记录
        
        Args:
            table: 表名/集合名
            conditions: 查询条件（确定更新哪些记录）
            data: 更新的数据（自动添加 $set）
            **kwargs: 数据库特定参数
        
        Returns:
            影响的行数/文档数
        """
        if not self._initialized:
            raise RuntimeError("DatabaseLayer 未初始化，请先调用 initialize()")
        
        if self._database_type == DatabaseType.MYSQL:
            return await self._mysql_update(table, conditions, data, **kwargs)
        elif self._database_type == DatabaseType.MONGODB:
            return await self._mongo_update(table, conditions, data, upsert=upsert, **kwargs)
        else:
            raise ValueError(f"不支持的数据库类型: {self._database_type.value}")
    
    async def delete(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder]
    ) -> int:
        """
        删除记录
        
        Args:
            table: 表名/集合名
            conditions: 查询条件（确定删除哪些记录）
        
        Returns:
            删除的行数/文档数
        """
        if not self._initialized:
            raise RuntimeError("DatabaseLayer 未初始化，请先调用 initialize()")
        
        if self._database_type == DatabaseType.MYSQL:
            return await self._mysql_delete(table, conditions)
        elif self._database_type == DatabaseType.MONGODB:
            return await self._mongo_delete(table, conditions)
        else:
            raise ValueError(f"不支持的数据库类型: {self._database_type.value}")
    
    # ==================== MySQL 实现 ====================
    
    async def _mysql_find(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder, QueryBuilder],
        page: int,
        page_size: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """MySQL 分页查询"""
        if isinstance(conditions, QueryBuilder):
            # 1. 获取纯 WHERE 条件（不带分页参数），用于 COUNT
            where_clause_only, where_params = conditions._builder.build_mysql()

            # 2. 获取完整 SQL 片段和参数（包含排序、分页），用于数据查询
            where_sql, full_params, qb_page, qb_page_size = conditions.build_mysql()

            # 3. 字段投影
            if conditions._projection:
                included_fields = [f"`{k}`" for k, v in conditions._projection.items() if v == 1]
                fields_str = ", ".join(included_fields) if included_fields else "*"
            else:
                fields_str = "*"

            # 4. 执行 COUNT 查询（使用纯 WHERE 参数）
            count_sql = f"SELECT COUNT(*) AS total FROM `{table}`{where_clause_only}"
            count_result = await mysql_execute_one(count_sql, where_params)
            total = list(count_result.values())[0] if count_result else 0

            # 5. 执行数据查询（使用完整参数）
            data_sql = f"SELECT {fields_str} FROM `{table}`{where_sql}"
            data = await mysql_execute_query(data_sql, full_params)

            return data, total
        else:
        # 单独获取 WHERE 子句和参数（用于 COUNT）
            where_clause, where_params = self._build_mysql_where(conditions)
            count_sql = f"SELECT COUNT(*) AS total FROM `{table}`{where_clause}"
            count_result = await mysql_execute_one(count_sql, where_params)
            total = list(count_result.values())[0] if count_result else 0

            # 构建完整数据查询 SQL
            sql, params = self._build_mysql_query(table, conditions)
            if page and page_size:
                sql += " LIMIT %s OFFSET %s"
                params = params + (page_size, (page - 1) * page_size)
            data = await mysql_execute_query(sql, params)
            return data, total

    async def _mysql_find_one(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder]
    ) -> Optional[Dict[str, Any]]:
        """MySQL 单条查询"""
        sql, params = self._build_mysql_query(table, conditions, limit=1)
        return await mysql_execute_one(sql, params)
    
    async def _mysql_insert(
        self,
        table: str,
        data: Dict[str, Any],
        return_id: bool = True
    ) -> Any:
        """MySQL 插入"""
        fields = list(data.keys())
        placeholders = ", ".join(["%s"] * len(fields))
        fields_str = ", ".join([f"`{f}`" for f in fields])
        
        sql = f"INSERT INTO `{table}` ({fields_str}) VALUES ({placeholders})"
        params = tuple(data.values())
        
        if return_id:
            return await mysql_execute_insert(sql, params)
        else:
            return await mysql_execute_update(sql, params)
    
    async def _mysql_update(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder],
        data: Dict[str, Any]
    ) -> int:
        """MySQL 更新"""
        set_parts = [f"`{k}` = %s" for k in data.keys()]
        set_clause = ", ".join(set_parts)
        params = list(data.values())
        
        where_clause, where_params = self._build_mysql_where(conditions)
        params.extend(where_params)
        
        sql = f"UPDATE `{table}` SET {set_clause} {where_clause}"
        return await mysql_execute_update(sql, tuple(params))
    
    async def _mysql_delete(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder]
    ) -> int:
        """MySQL 删除"""
        where_clause, params = self._build_mysql_where(conditions)
        sql = f"DELETE FROM `{table}` {where_clause}"
        return await mysql_execute_update(sql, params)
    
    def _build_mysql_query(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder, QueryBuilder],
        limit: Optional[int] = None
    ) -> Tuple[str, Tuple[Any, ...]]:
        """构建 MySQL 查询语句"""
        if isinstance(conditions, QueryBuilder):
            sql, params, _, _ = conditions.build_mysql()
            return f"SELECT * FROM `{table}`{sql}", params
        
        where_clause, params = self._build_mysql_where(conditions)
        
        sql = f"SELECT * FROM `{table}`{where_clause}"
        if limit:
            sql += " LIMIT 1"
        
        return sql, params
    
    def _build_mysql_where(
        self,
        conditions: Union[Dict[str, Any], ConditionBuilder]
    ) -> Tuple[str, Tuple[Any, ...]]:
        """构建 MySQL WHERE 子句"""
        if isinstance(conditions, ConditionBuilder):
            return conditions.build_mysql()
        
        if not conditions:
            return "", ()
        
        parts = []
        params = []
        for field, value in conditions.items():
            if value is None:
                parts.append(f"`{field}` IS NULL")
            else:
                parts.append(f"`{field}` = %s")
                params.append(value)
        
        where_clause = " WHERE " + " AND ".join(parts) if parts else ""
        return where_clause, tuple(params)
    
    # ==================== MongoDB 实现 ====================
    
    async def _mongo_find(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder, QueryBuilder],
        page: int,
        page_size: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """MongoDB 分页查询"""
        if isinstance(conditions, QueryBuilder):
            query = conditions.build_mongodb()
            qb_page = conditions._page or page
            qb_page_size = conditions._page_size or page_size

            sort = query.get("sort")
            if isinstance(sort, dict):
                sort = [(field, direction) for field, direction in sort.items()]

            # 执行 COUNT（利用 mongo_find_func 内部实现）
            data, total = await mongo_find_func(
                collection_name=table,
                query=query.get("filter", {}),
                projection=query.get("projection"),
                sort=sort,
                page=qb_page,
                page_size=qb_page_size
            )
            return data, total
        else:
            query = self._build_mongo_query(conditions)
            data, total = await mongo_find_func(
                collection_name=table,
                query=query.get("filter", {}),
                projection=query.get("projection"),
                sort=query.get("sort"),
                page=page,
                page_size=page_size
            )
            return data, total

    async def _mongo_find_one(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder]
    ) -> Optional[Dict[str, Any]]:
        """MongoDB 单条查询"""
        query = self._build_mongo_query(conditions)
        return await mongo_find_one_func(
            collection_name=table,
            query=query.get("filter", {}),
            projection=query.get("projection")
        )
    
    async def _mongo_insert(
        self,
        table: str,
        data: Dict[str, Any]
    ) -> str:
        """MongoDB 插入"""
        return await mongo_insert_one_func(collection_name=table, document=data)
    
    async def _mongo_update(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder],
        data: Dict[str, Any],
        upsert: bool = False
    ) -> int:
        query = self._build_mongo_query(conditions)
        if data and not any(k.startswith("$") for k in data.keys()):
            data = {"$set": data}
        result = await mongo_update_one_func(
        collection_name=table,
        query=query.get("filter", {}),
        update=data,
        upsert=upsert
    )
        return result
    
    async def _mongo_delete(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder]
    ) -> int:
        """MongoDB 删除"""
        query = self._build_mongo_query(conditions)
        result = await mongo_delete_one_func(
            collection_name=table,
            query=query.get("filter", {})
        )
        return result
    
    def _build_mongo_query(
        self,
        conditions: Union[Dict[str, Any], ConditionBuilder]
    ) -> Dict[str, Any]:
        """构建 MongoDB 查询文档"""
        if isinstance(conditions, ConditionBuilder):
            return {"filter": conditions.build_mongodb()}
        
        if not conditions:
            return {"filter": {}}
        
        return {"filter": conditions}
    
    # ==================== Redis 实现 ====================
    
    async def add_delayed_task(
        self,
        task_json: str,
        execute_at: float
    ) -> int:
        """添加延迟任务（Redis ZSet）"""
        return await redis_add_delayed_task(task_json=task_json, execute_at=execute_at)
    
    async def batch_pop_due_tasks(
        self,
        now: float,
        limit: int = 10
    ) -> List[str]:
        """批量弹出到期任务（Redis）"""
        return await redis_batch_pop_due_tasks(now=now, limit=limit)
    
    async def get_earliest_score(self) -> Optional[float]:
        """获取最早任务的 score（Redis）"""
        return await redis_get_earliest_score()
    
    # ==================== 数据库健康检查 ====================
    
    async def ping_mysql(self) -> bool:
        """
        检查 MySQL 连接是否正常。
        从连接池借一个连接执行 SELECT 1，成功返回 True，失败返回 False。
        """
        try:
            pool = get_mysql_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
            return True
        except Exception:
            return False
    
    async def ping_redis(self) -> bool:
        """
        检查 Redis 连接是否正常。
        调用 Redis ping 命令，成功返回 True，失败返回 False。
        """
        try:
            client = get_redis()
            await client.ping()
            return True
        except Exception:
            return False
    
    async def ping_mongodb(self) -> bool:
        """
        检查 MongoDB 连接是否正常。
        执行 admin command ping，成功返回 True，失败返回 False。
        """
        try:
            client = get_mongo_client()
            await client.admin.command("ping")
            return True
        except Exception:
            return False
    
    async def ping_all(self) -> dict:
        """
        并行检查三个数据库连接的健康状态。

        Returns:
            {"mysql": bool, "redis": bool, "mongodb": bool}
        """
        results = await asyncio.gather(
            self.ping_mysql(),
            self.ping_redis(),
            self.ping_mongodb(),
            return_exceptions=True,
        )
        return {
            "mysql": results[0] if isinstance(results[0], bool) else False,
            "redis": results[1] if isinstance(results[1], bool) else False,
            "mongodb": results[2] if isinstance(results[2], bool) else False,
        }
    
    # ==================== 原生入口（高级功能） ====================
    
    async def execute_raw(
        self,
        query: str,
        params: Tuple[Any, ...] = None,
        database_type: str = None
    ) -> Any:
        """
        执行原生查询（绕过中间层，直接操作底层数据库）
        
        Args:
            query: SQL 语句或 MongoDB 聚合管道
            params: 参数元组
            database_type: 指定数据库类型（None 使用默认）
        
        Returns:
            查询结果
        """
        db_type = database_type or (self._database_type.value if self._database_type else "mysql")
        
        if db_type == "mysql":
            return await mysql_execute_query(query, params)
        elif db_type == "mongodb":
            # MongoDB 聚合查询
            client = get_mongodb()
            collection_name, pipeline = self._parse_mongodb_aggregation(query)
            result = await client[collection_name].aggregate(pipeline).to_list(length=None)
            return result
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")
    
    def _parse_mongodb_aggregation(self, query: str) -> Tuple[str, List[Dict]]:
        """解析 MongoDB 聚合管道（简化版）"""
        # 示例: "users|[{\"$match\": {\"status\": \"active\"}}, {\"$group\": {...}}]"
        if "|" in query:
            parts = query.split("|", 1)
            collection = parts[0]
            # 这里需要实际解析 JSON，简化处理
            pipeline = []
            return collection, pipeline
        return "unknown", []
    
    def raw_mysql(self):
        """获取 MySQL 原生访问入口"""
        if not self._initialized:
            raise RuntimeError("DatabaseLayer 未初始化")
        return MySQLRawAccess(self)
    
    def raw_mongodb(self):
        """获取 MongoDB 原生访问入口"""
        if not self._initialized:
            raise RuntimeError("DatabaseLayer 未初始化")
        return MongoDBRawAccess(self)
    
    def raw_redis(self):
        """获取 Redis 原生访问入口"""
        if not self._initialized:
            raise RuntimeError("DatabaseLayer 未初始化")
        return RedisRawAccess(self)


class MySQLRawAccess:
    """MySQL 原生访问包装"""
    
    def __init__(self, db_layer: DatabaseLayer):
        self.db_layer = db_layer
    
    async def execute(self, sql: str, params: Tuple = None) -> Any:
        return await mysql_execute_query(sql, params)
    
    async def execute_update(self, sql: str, params: Tuple = None) -> int:
        return await mysql_execute_update(sql, params)
    
    async def execute_insert(self, sql: str, params: Tuple = None) -> int:
        return await mysql_execute_insert(sql, params)


class MongoDBRawAccess:
    """MongoDB 原生访问包装"""
    
    def __init__(self, db_layer: DatabaseLayer):
        self.db_layer = db_layer
    
    async def find(self, collection: str, query: Dict, **kwargs) -> List[Dict]:
        return (await mongo_find_func(collection, query, **kwargs))[0]
    
    async def find_one(self, collection: str, query: Dict, **kwargs) -> Optional[Dict]:
        return await mongo_find_one_func(collection, query, **kwargs)
    
    async def aggregate(self, collection: str, pipeline: List[Dict]) -> List[Dict]:
        db = get_mongodb()
        result = await db[collection].aggregate(pipeline).to_list(length=None)
        return result


class RedisRawAccess:
    """Redis 原生访问包装"""
    
    def __init__(self, db_layer: DatabaseLayer):
        self.db_layer = db_layer
    
    async def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        client = get_redis()
        return await client.zadd(key, mapping)
    
    async def zrange(self, key: str, start: int, end: int, **kwargs) -> List[Any]:
        client = get_redis()
        return await client.zrange(key, start, end, **kwargs)
    
    async def eval(self, script: str, keys: List[str], args: List[Any]) -> Any:
        client = get_redis()
        return await client.eval(script, len(keys), *keys, *args)
