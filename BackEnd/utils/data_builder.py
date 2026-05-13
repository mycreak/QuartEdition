# test/utils/test_data_manager.py

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, List, Any, Callable, Union
from db.redis import get_redis
import json

logger = logging.getLogger(__name__)


class TestDataManager:
    """
    测试数据管理器，支持 MySQL / MongoDB / Redis 的测试数据准备与清理。
    设计为可复用工具，每个测试用例独立使用不同的资源名以避免冲突。
    """

    def __init__(self, db_layer, resource_name: str):
        """
        Args:
            db_layer: DatabaseLayer 实例（已初始化）
            resource_name: 基础资源名（如表名），实际使用时会添加随机后缀保证隔离
        """
        self.db = db_layer
        self.base_name = resource_name
        self._unique_suffix = f"_{id(self)}"  # 简单唯一标识
        self._created_resources: List[str] = []  # 记录创建的资源，便于清理

    def _unique_name(self, name: str = None) -> str:
        """生成唯一资源名"""
        if name is None:
            name = self.base_name
        return f"{name}{self._unique_suffix}"

    # ==================== MySQL ====================
    async def create_mysql_table(
        self,
        table_name: str = None,
        schema: str = None,
        indexes: List[str] = None
    ) -> str:
        """创建 MySQL 测试表，返回实际表名"""
        actual_name = self._unique_name(table_name)
        if schema is None:
            schema = """
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """
        sql = f"CREATE TABLE IF NOT EXISTS `{actual_name}` ({schema})"
        # 假设底层有原生执行方法，若无则使用 raw_mysql
        await self.db.raw_mysql().execute_update(sql)
        if indexes:
            for idx_sql in indexes:
                await self.db.raw_mysql().execute_update(idx_sql.format(table=actual_name))
        self._created_resources.append(("mysql_table", actual_name))
        logger.info(f"创建 MySQL 测试表: {actual_name}")
        return actual_name

    async def drop_mysql_table(self, table_name: str):
        """删除 MySQL 测试表"""
        await self.db.raw_mysql().execute_update(f"DROP TABLE IF EXISTS `{table_name}`")
        logger.info(f"删除 MySQL 测试表: {table_name}")

    async def insert_mysql_data(self, table_name: str, rows: List[Dict[str, Any]]) -> List[int]:
        """批量插入 MySQL 数据，返回自增 ID 列表"""
        ids = []
        for row in rows:
            # 这里使用 DatabaseLayer.insert 已支持 MySQL
            inserted_id = await self.db.insert(table_name, row)
            ids.append(inserted_id)
        return ids

    # ==================== MongoDB ====================
    async def create_mongodb_collection(
        self,
        collection_name: str = None,
        indexes: List[Dict] = None
    ) -> str:
        """创建 MongoDB 集合（MongoDB 通常自动创建，此处仅记录）"""
        actual_name = self._unique_name(collection_name)
        self._created_resources.append(("mongodb_collection", actual_name))
        if indexes:
            raw = self.db.raw_mongodb()
            for idx in indexes:
                await raw.db[actual_name].create_index(idx["keys"], **idx.get("options", {}))
        logger.info(f"记录 MongoDB 测试集合: {actual_name}")
        return actual_name

    async def drop_mongodb_collection(self, collection_name: str):
        """删除 MongoDB 测试集合"""
        await self.db.raw_mongodb().db.drop_collection(collection_name)
        logger.info(f"删除 MongoDB 测试集合: {collection_name}")

    async def insert_mongodb_data(self, collection_name: str, docs: List[Dict[str, Any]]) -> List[str]:
        """批量插入 MongoDB 文档，返回 _id 列表"""
        ids = []
        for doc in docs:
            inserted_id = await self.db.insert(collection_name, doc)
            ids.append(inserted_id)
        return ids

    # ==================== Redis ====================
    async def prepare_redis_data(self, key: str = None, mapping: Dict[str, Any] = None) -> str:
        """向 Redis 写入测试数据（Hash 或 String）"""
        actual_key = self._unique_name(key)
        client = self.db.raw_redis().client
        if mapping is None:
            mapping = {"test": "value"}
        await client.hset(actual_key, mapping=mapping)
        self._created_resources.append(("redis_key", actual_key))
        logger.info(f"写入 Redis 测试键: {actual_key}")
        return actual_key

    async def prepare_delayed_tasks(
        self,
        tasks: List[Dict[str, Any]],  # 每个元素: {"data": {...}, "execute_at": float}
        key: str = None
    ) -> str:
        """向 Redis ZSet 批量添加延迟任务，返回实际使用的 key"""
        actual_key = key or redis_config.delay_queue_key
        client = get_redis()
        mapping = {}
        for task in tasks:
            task_json = json.dumps(task["data"])
            mapping[task_json] = task["execute_at"]
        if mapping:
            await client.zadd(actual_key, mapping)
        self._created_resources.append(("redis_key", actual_key))
        logger.info(f"向 Redis ZSet [{actual_key}] 添加 {len(mapping)} 个延迟任务")
        return actual_key

async def clear_delayed_tasks(self, key: str = None):
    """清空延迟任务 ZSet"""
    actual_key = key or redis_config.delay_queue_key
    try:
        client = get_redis()
        await client.delete(actual_key)
        logger.info(f"已清空延迟任务 ZSet: {actual_key}")
    except Exception as e:
        logger.error(f"清空延迟任务 ZSet {actual_key} 失败: {e}")

    async def cleanup_redis_keys(self, *keys: str):
        """删除 Redis 测试键"""
        client = self.db.raw_redis().client
        if keys:
            await client.delete(*keys)
            logger.info(f"删除 Redis 测试键: {keys}")

    # ==================== 统一清理 ====================
    async def cleanup_all(self):
        """根据记录的资源类型逐一清理"""
        for res_type, name in reversed(self._created_resources):
            try:
                if res_type == "mysql_table":
                    await self.drop_mysql_table(name)
                elif res_type == "mongodb_collection":
                    await self.drop_mongodb_collection(name)
                elif res_type == "redis_key":
                    await self.cleanup_redis_keys(name)
            except Exception as e:
                logger.error(f"清理资源 {res_type}:{name} 失败: {e}")

    # ==================== 上下文管理器 ====================
    @asynccontextmanager
    async def managed_mysql_table(
        self,
        table_name: str = None,
        schema: str = None,
        initial_data: List[Dict] = None
    ):
        """MySQL 测试表上下文管理器"""
        actual_name = await self.create_mysql_table(table_name, schema)
        try:
            if initial_data:
                await self.insert_mysql_data(actual_name, initial_data)
            yield actual_name
        finally:
            await self.drop_mysql_table(actual_name)

    @asynccontextmanager
    async def managed_mongodb_collection(
        self,
        collection_name: str = None,
        initial_data: List[Dict] = None
    ):
        """MongoDB 测试集合上下文管理器"""
        actual_name = await self.create_mongodb_collection(collection_name)
        try:
            if initial_data:
                await self.insert_mongodb_data(actual_name, initial_data)
            yield actual_name
        finally:
            await self.drop_mongodb_collection(actual_name)

    @asynccontextmanager
    async def managed_redis_key(self, key: str = None, initial_data: Dict = None):
        """Redis 测试键上下文管理器"""
        actual_key = await self.prepare_redis_data(key, initial_data)
        try:
            yield actual_key
        finally:
            await self.cleanup_redis_keys(actual_key)