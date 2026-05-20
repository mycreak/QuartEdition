"""
db/database_v2.py

统一数据库中间层 V2（支持 MySQL/MongoDB/Redis）
基于 database.py 重构，新增手动事务支持。

与 database.py 的差异：
    1. DatabaseLayer → DatabaseLayerV2（类名加 V2 后缀，避免冲突）
    2. 新增 TransactionContext 类 — 同一连接上的 CRUD 代理
    3. 新增 DatabaseLayerV2.transaction() — 手动事务上下文管理器
    4. 所有参数化查询逻辑不变，防注入机制完全一致
"""

import asyncio
import contextvars
import logging
from contextlib import asynccontextmanager
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
    add_delayed_task_with_limit as redis_add_delayed_task_with_limit,
    batch_pop_due_tasks as redis_batch_pop_due_tasks,
    get_earliest_score as redis_get_earliest_score,
    redis_incr_expire as redis_incr_expire_fn,
    redis_get as redis_get_fn,
)

logger = logging.getLogger(__name__)


class DatabaseType(Enum):
    """数据库类型枚举"""
    MYSQL = "mysql"
    MONGODB = "mongodb"
    REDIS = "redis"


# ═══════════════════════════════════════════
# TransactionContext — 同一连接上的事务操作代理
# ═══════════════════════════════════════════

class TransactionContext:
    """
    手动事务内的 CRUD 代理。

    与 DatabaseLayerV2 的区别：
        DatabaseLayerV2.insert():
            pool.acquire() → INSERT → release   （每个操作独立的连接 + autocommit）
        TransactionContext.insert():
            同一 conn → INSERT → 不释放           （所有操作在同一事务内）

    使用方式（仅通过 DatabaseLayerV2.transaction() 获取）：
        async with db.transaction() as tx:
            mid = await tx.insert("movies", values, return_id=True)
            # 退出 with 块 → COMMIT（异常 → ROLLBACK）

    安全保证：
        所有 SQL 走 %s 占位符 + aiomysql 参数化 → 防注入不变
    """

    def __init__(self, conn):
        """
        Args:
            conn: aiomysql.Connection（已执行 BEGIN，autocommit 已关闭）
        """
        self._conn = conn

    async def insert(self, table: str, data: Dict[str, Any], return_id: bool = True) -> Any:
        """
        INSERT INTO `table` (...) VALUES (...)
        与 DatabaseLayerV2._mysql_insert 的 SQL 构建逻辑一致。
        """
        fields = ", ".join(f"`{k}`" for k in data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        sql = f"INSERT INTO `{table}` ({fields}) VALUES ({placeholders})"
        params = tuple(data.values())
        return await self._execute(sql, params, return_id)

    async def find_one(self, table: str, conditions: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        SELECT * FROM `table` WHERE ... LIMIT 1
        """
        where_clause, params = _build_where(conditions)
        sql = f"SELECT * FROM `{table}`{where_clause} LIMIT 1"
        result = await self._execute_query(sql, params)
        return result[0] if result else None

    async def update(
        self, table: str, conditions: Dict[str, Any], data: Dict[str, Any]
    ) -> int:
        """
        UPDATE `table` SET ... WHERE ...
        """
        set_parts = [f"`{k}` = %s" for k in data.keys()]
        set_clause = ", ".join(set_parts)
        params = list(data.values())
        where_clause, where_params = _build_where(conditions)
        params.extend(where_params)
        sql = f"UPDATE `{table}` SET {set_clause}{where_clause}"
        return await self._execute(sql, tuple(params), return_id=False)

    async def delete(self, table: str, conditions: Dict[str, Any]) -> int:
        """
        DELETE FROM `table` WHERE ...
        """
        where_clause, params = _build_where(conditions)
        sql = f"DELETE FROM `{table}`{where_clause}"
        return await self._execute(sql, params, return_id=False)

    async def execute_raw(self, sql: str, params: tuple = None) -> List[Dict]:
        """
        执行原生查询（用于 JOIN / GROUP BY 等复杂场景）。
        使用方法与 DatabaseLayerV2.execute_raw 一致，但走同一连接。
        """
        return await self._execute_query(sql, params)

    async def _execute(self, sql: str, params: tuple, return_id: bool) -> Any:
        """内部 — 执行写操作 SQL"""
        async with self._conn.cursor() as cur:
            await cur.execute(sql, params)
            if return_id:
                return cur.lastrowid
            return cur.rowcount

    async def _execute_query(self, sql: str, params: tuple = None) -> List[Dict]:
        """内部 — 执行查询 SQL，返回 dict 列表"""
        async with self._conn.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchall()


# ═══════════════════════════════════════════
# DatabaseLayerV2 — 统一数据库中间层（含事务支持）
# ═══════════════════════════════════════════

class DatabaseLayerV2:
    """
    统一数据库中间层（V2 — 新增手动事务）

    与 DatabaseLayer 的差异：
        - 新增 transaction() 上下文管理器
        - 类名带 V2 后缀，与旧版共存
        - 公共 API（find/insert/update/delete/execute_raw）完全兼容
        - 2026-05-10: _database_type 改为 ContextVar，修复 asyncio 并发竞态
    """

    def __init__(self):
        self._database_type: contextvars.ContextVar = contextvars.ContextVar(
            "db_type", default=None
        )
        self._initialized = False

    def _get_type(self) -> DatabaseType:
        """获取当前 asyncio 任务的数据库类型（ContextVar 隔离）。
        未设置时始终降级为 MYSQL，保证返回值永不为 None。"""
        val = self._database_type.get()
        if val is None:
            val = DatabaseType.MYSQL
            self._database_type.set(val)
        return val

    def _set_type(self, value: Optional[DatabaseType]):
        self._database_type.set(value)

    async def initialize(self, database_type: str = "mysql"):
        """
        初始化中间层（指定默认数据库类型）

        Args:
            database_type: "mysql" | "mongodb" | "redis"
        """
        self._set_type(DatabaseType(database_type.lower()))
        self._initialized = True
        logger.info(f"DatabaseLayerV2 初始化完成，默认数据库: {database_type}")

    def set_database(self, database_type: str):
        """设置当前 asyncio 任务的数据库类型（仅影响当前任务，不跨任务传播）"""
        self._set_type(DatabaseType(database_type.lower()))
        logger.debug(f"切换数据库类型: {database_type}")

    @asynccontextmanager
    async def transaction(self):
        """
        手动事务上下文管理器。

        用法:
            async with self.db.transaction() as tx:
                mid = await tx.insert("movies", values, return_id=True)
                # 正常退出 → COMMIT；异常 → ROLLBACK

        TransactionContext 暴露的方法:
            insert(table, data, return_id=True)       → 返回 lastrowid 或 rowcount
            find_one(table, conditions)                → 返回 dict 或 None
            update(table, conditions, data)            → 返回 rowcount
            delete(table, conditions)                  → 返回 rowcount
            execute_raw(sql, params)                   → 返回 list[dict]

        安全保证:
            所有 SQL 走 %s 占位符 + aiomysql 参数化 → 防注入不变
        """
        pool = get_mysql_pool()
        async with pool.acquire() as conn:
            await conn.begin()
            tx = TransactionContext(conn)
            try:
                yield tx
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    # ═══════════════════════════════════════
    # 通用 CRUD（与 DatabaseLayer 完全兼容）
    # ═══════════════════════════════════════

    async def find(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder, QueryBuilder] = None,
        page: int = 1,
        page_size: int = 20,
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        通用查询（分页）。

        projection / sort 仅在 MongoDB 模式下生效，MySQL 模式忽略。
        """
        if not self._initialized:
            raise RuntimeError("DatabaseLayerV2 未初始化，请先调用 initialize()")

        db_type = self._get_type()
        if db_type == DatabaseType.MYSQL:
            return await self._mysql_find(table, conditions, page, page_size)
        elif db_type == DatabaseType.MONGODB:
            return await self._mongo_find(table, conditions, page, page_size, projection=projection, sort=sort)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type.value if db_type else 'None'}")

    async def find_one(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder] = None
    ) -> Optional[Dict[str, Any]]:
        """查询单条记录"""
        if not self._initialized:
            raise RuntimeError("DatabaseLayerV2 未初始化，请先调用 initialize()")

        db_type = self._get_type()
        if db_type == DatabaseType.MYSQL:
            return await self._mysql_find_one(table, conditions)
        elif db_type == DatabaseType.MONGODB:
            return await self._mongo_find_one(table, conditions)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type.value if db_type else 'None'}")

    async def insert(
        self,
        table: str,
        data: Dict[str, Any],
        **kwargs
    ) -> Any:
        """插入记录"""
        if not self._initialized:
            raise RuntimeError("DatabaseLayerV2 未初始化，请先调用 initialize()")

        db_type = self._get_type()
        if db_type == DatabaseType.MYSQL:
            return await self._mysql_insert(table, data, **kwargs)
        elif db_type == DatabaseType.MONGODB:
            return await self._mongo_insert(table, data, **kwargs)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type.value if db_type else 'None'}")

    async def update(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder],
        data: Dict[str, Any],
        upsert: bool = False,
        **kwargs
    ) -> int:
        """更新记录"""
        if not self._initialized:
            raise RuntimeError("DatabaseLayerV2 未初始化，请先调用 initialize()")

        db_type = self._get_type()
        if db_type == DatabaseType.MYSQL:
            return await self._mysql_update(table, conditions, data, **kwargs)
        elif db_type == DatabaseType.MONGODB:
            return await self._mongo_update(table, conditions, data, upsert=upsert, **kwargs)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type.value if db_type else 'None'}")

    async def delete(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder]
    ) -> int:
        """删除记录"""
        if not self._initialized:
            raise RuntimeError("DatabaseLayerV2 未初始化，请先调用 initialize()")

        db_type = self._get_type()
        if db_type == DatabaseType.MYSQL:
            return await self._mysql_delete(table, conditions)
        elif db_type == DatabaseType.MONGODB:
            return await self._mongo_delete(table, conditions)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type.value if db_type else 'None'}")

    # ═══════════════════════════════════════
    # MySQL 实现（与 DatabaseLayer 一致）
    # ═══════════════════════════════════════

    async def _mysql_find(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder, QueryBuilder],
        page: int,
        page_size: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """MySQL 分页查询"""
        if isinstance(conditions, QueryBuilder):
            where_clause_only, where_params = conditions._builder.build_mysql()
            where_sql, full_params, qb_page, qb_page_size = conditions.build_mysql()
            if conditions._projection:
                included_fields = [f"`{k}`" for k, v in conditions._projection.items() if v == 1]
                fields_str = ", ".join(included_fields) if included_fields else "*"
            else:
                fields_str = "*"
            count_sql = f"SELECT COUNT(*) AS total FROM `{table}`{where_clause_only}"
            count_result = await mysql_execute_one(count_sql, where_params)
            total = list(count_result.values())[0] if count_result else 0
            data_sql = f"SELECT {fields_str} FROM `{table}`{where_sql}"
            data = await mysql_execute_query(data_sql, full_params)
            return data, total
        else:
            where_clause, where_params = self._build_mysql_where(conditions)
            count_sql = f"SELECT COUNT(*) AS total FROM `{table}`{where_clause}"
            count_result = await mysql_execute_one(count_sql, where_params)
            total = list(count_result.values())[0] if count_result else 0
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

    # ═══════════════════════════════════════
    # MongoDB 实现（与 DatabaseLayer 一致）
    # ═══════════════════════════════════════

    async def _mongo_find(
        self,
        table: str,
        conditions: Union[Dict[str, Any], ConditionBuilder, QueryBuilder],
        page: int,
        page_size: int,
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """MongoDB 分页查询"""
        if isinstance(conditions, QueryBuilder):
            query = conditions.build_mongodb()
            qb_page = conditions._page or page
            qb_page_size = conditions._page_size or page_size
            qb_sort = sort
            if sort is None:
                qb_sort_raw = query.get("sort")
                if isinstance(qb_sort_raw, dict):
                    qb_sort = [(field, direction) for field, direction in qb_sort_raw.items()]
            data, total = await mongo_find_func(
                collection_name=table,
                query=query.get("filter", {}),
                projection=query.get("projection") or projection,
                sort=qb_sort,
                page=qb_page,
                page_size=qb_page_size
            )
            return data, total
        else:
            query = self._build_mongo_query(conditions)
            data, total = await mongo_find_func(
                collection_name=table,
                query=query.get("filter", {}),
                projection=projection or query.get("projection"),
                sort=sort or query.get("sort"),
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

    # ═══════════════════════════════════════
    # Redis 实现（与 DatabaseLayer 一致）
    # ═══════════════════════════════════════

    async def add_delayed_task(
        self,
        task_json: str,
        execute_at: float
    ) -> int:
        """添加延迟任务（Redis ZSet）"""
        return await redis_add_delayed_task(task_json=task_json, execute_at=execute_at)

    async def add_delayed_task_with_limit(
        self,
        task_json: str,
        cooldown_seconds: float = 0.0,
    ) -> float:
        """
        带限速的延迟任务写入（原子操作）。

        execute_at = max(now, last_submit_time + cooldown)
        输入：task_json, cooldown_seconds（0=不限速）
        输出：实际写入的 execute_at
        """
        return await redis_add_delayed_task_with_limit(
            task_json=task_json,
            cooldown_seconds=cooldown_seconds,
        )

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

    # ── 通用 Redis 计数器（限流 / 频控） ──

    async def increment_counter(self, key: str, ttl: int) -> int:
        """
        原子递增 Redis 计数器并设置过期时间。

        输入：key — Redis key / ttl — 过期时间（秒），仅首次调用时设置
        输出：递增后的计数值
        使用场景：限流计数、API 频控

        注意：此方法会临时切换数据库类型为 redis 再还原，
        不改变 DatabaseLayerV2 的默认类型。
        """
        prev = self._get_type()
        try:
            self.set_database("redis")
            return await redis_incr_expire_fn(key=key, ttl=ttl)
        finally:
            self._set_type(prev)

    async def get_counter(self, key: str) -> int:
        """获取 Redis 计数器当前值（key 不存在返回 0）。"""
        prev = self._get_type()
        try:
            self.set_database("redis")
            val = await redis_get_fn(key)
            return int(val) if val else 0
        finally:
            self._set_type(prev)

    # ═══════════════════════════════════════
    # 数据库健康检查（与 DatabaseLayer 一致）
    # ═══════════════════════════════════════

    async def ping_mysql(self) -> bool:
        """检查 MySQL 连接是否正常"""
        try:
            pool = get_mysql_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def ping_redis(self) -> bool:
        """检查 Redis 连接是否正常"""
        try:
            client = get_redis()
            await client.ping()
            return True
        except Exception:
            return False

    async def ping_mongodb(self) -> bool:
        """检查 MongoDB 连接是否正常"""
        try:
            client = get_mongo_client()
            await client.admin.command("ping")
            return True
        except Exception:
            return False

    async def ping_all(self) -> dict:
        """并行检查三个数据库连接的健康状态"""
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

    # ═══════════════════════════════════════
    # 原生入口（与 DatabaseLayer 一致）
    # ═══════════════════════════════════════

    async def execute_raw(
        self,
        query: str,
        params: Tuple[Any, ...] = None,
        database_type: str = None
    ) -> Any:
        """执行原生查询（绕过中间层）"""
        db_type = database_type or (self._get_type().value if self._get_type() else "mysql")

        if db_type == "mysql":
            return await mysql_execute_query(query, params)
        elif db_type == "mongodb":
            client = get_mongodb()
            collection_name, pipeline = self._parse_mongodb_aggregation(query)
            result = await client[collection_name].aggregate(pipeline).to_list(length=None)
            return result
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")

    def _parse_mongodb_aggregation(self, query: str) -> Tuple[str, List[Dict]]:
        """⚠️ 未实现 — 不解析管道，只提取集合名，聚合功能不可用。"""
        if "|" in query:
            parts = query.split("|", 1)
            collection = parts[0]
            pipeline = []
            return collection, pipeline
        return "unknown", []

    def raw_mysql(self):
        """获取 MySQL 原生访问入口"""
        if not self._initialized:
            raise RuntimeError("DatabaseLayerV2 未初始化")
        return MySQLRawAccessV2(self)

    def raw_mongodb(self):
        """获取 MongoDB 原生访问入口"""
        if not self._initialized:
            raise RuntimeError("DatabaseLayerV2 未初始化")
        return MongoDBRawAccessV2(self)

    def raw_redis(self):
        """获取 Redis 原生访问入口"""
        if not self._initialized:
            raise RuntimeError("DatabaseLayerV2 未初始化")
        return RedisRawAccessV2(self)


class MySQLRawAccessV2:
    """MySQL 原生访问入口（与 MySQLRawAccess 一致）"""
    def __init__(self, db):
        self.db = db

    async def execute_insert(self, sql: str, params: tuple = None) -> int:
        return await mysql_execute_insert(sql, params)

    async def execute_update(self, sql: str, params: tuple = None) -> int:
        return await mysql_execute_update(sql, params)

    async def execute_query(self, sql: str, params: tuple = None) -> List[Dict]:
        return await mysql_execute_query(sql, params)


class MongoDBRawAccessV2:
    """MongoDB 原生访问入口（与 database.py:MongoDBRawAccess 等价）。"""

    def __init__(self, db):
        self.db = db

    async def find(self, collection: str, query: dict, **kwargs) -> List[Dict]:
        return (await mongo_find_func(collection, query, **kwargs))[0]

    async def find_one(self, collection: str, query: dict, **kwargs) -> Optional[Dict]:
        return await mongo_find_one_func(collection, query, **kwargs)

    async def aggregate(self, collection: str, pipeline: list) -> List[Dict]:
        mongodb = get_mongodb()
        return await mongodb[collection].aggregate(pipeline).to_list(length=None)


class RedisRawAccessV2:
    """Redis 原生访问入口（与 database.py:RedisRawAccess 等价）。"""

    def __init__(self, db):
        self.db = db

    async def zadd(self, key: str, mapping: dict) -> int:
        return await get_redis().zadd(key, mapping)

    async def zrange(self, key: str, start: int, end: int, **kwargs):
        return await get_redis().zrange(key, start, end, **kwargs)

    async def zremrangebyscore(self, key: str, min_score: str, max_score: float) -> int:
        return await get_redis().zremrangebyscore(key, min_score, max_score)

    async def zcount(self, key: str, min_score: float, max_score: float) -> int:
        return await get_redis().zcount(key, min_score, max_score)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        return await get_redis().setex(key, ttl, value)

    async def expire(self, key: str, ttl: int) -> None:
        return await get_redis().expire(key, ttl)

    async def exists(self, key: str) -> int:
        return await get_redis().exists(key)

    async def eval(self, script: str, keys: list, args: list):
        return await get_redis().eval(script, len(keys), *keys, *args)


# ═══════════════════════════════════════════
# 共享的 SQL 构建工具函数（TransactionContext 和 DatabaseLayerV2 共用）
# ═══════════════════════════════════════════

def _build_where(conditions: Dict[str, Any] = None) -> Tuple[str, tuple]:
    """
    构建 WHERE 子句（纯函数，无副作用）。

    输入:
        conditions: {"field": value, "field2": None} 或 None
    输出:
        (" WHERE ...", (params,))
    """
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
