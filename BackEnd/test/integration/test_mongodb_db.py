"""
MongoDB 数据库层集成测试
"""

import pytest
import asyncio
from typing import Dict, Any, List
from bson import ObjectId

from db.database_v2 import DatabaseLayerV2
from db.query_builder import ConditionBuilder, QueryBuilder
from db.mongodb import (
    init_mongodb, close_mongodb, get_mongodb, get_mongo_client,
    mongo_insert_one, mongo_update_one, mongo_delete_one
)


TEST_COLLECTION = "test_collection"


# ==================== SC-MG-01 MongoDB 连接池管理与初始化 ====================

@pytest.mark.integration
@pytest.mark.db
class TestMongoDBConnection:
    """MongoDB 连接测试"""

    async def test_init_mongodb_success(self):
        """TC-MG-01-01: 正常初始化 MongoDB"""
        await init_mongodb()
        db = get_mongodb()
        assert db is not None
        await close_mongodb()

    async def test_reinit_mongodb(self):
        """TC-MG-01-02: 重复初始化 MongoDB"""
        await init_mongodb()
        await init_mongodb()  # 重复初始化应该不报错
        db = get_mongodb()
        assert db is not None
        await close_mongodb()

    async def test_close_and_reinit_mongodb(self):
        """TC-MG-01-03: 关闭并重新初始化 MongoDB"""
        await init_mongodb()
        await close_mongodb()
        with pytest.raises(RuntimeError):
            get_mongodb()
        await init_mongodb()
        db = get_mongodb()
        assert db is not None
        await close_mongodb()

    async def test_ping_mongodb(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-01-04: ping_mongodb 健康检查"""
        result = await db_mongodb.ping_mongodb()
        assert result is True


# ==================== SC-MG-02 MongoDB 单次 CRUD 操作 ====================

@pytest.mark.integration
@pytest.mark.db
class TestMongoDBSingleCRUD:
    """MongoDB 单次 CRUD 测试"""

    async def test_insert_document(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-02-01: 插入单条文档"""
        doc = {"name": "test", "value": 42}
        doc_id = await db_mongodb.insert(TEST_COLLECTION, doc)
        
        assert doc_id is not None
        assert isinstance(doc_id, str)
        
        # 验证文档存在
        db = get_mongodb()
        inserted = await db[TEST_COLLECTION].find_one({"_id": ObjectId(doc_id)})
        assert inserted is not None
        assert inserted["name"] == "test"
        assert inserted["value"] == 42

    async def test_find_one_document(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-02-02: 查询单条文档"""
        # 先插入
        doc = {"name": "find_test", "value": 100}
        doc_id = await db_mongodb.insert(TEST_COLLECTION, doc)
        
        # 查询
        found = await db_mongodb.find_one(TEST_COLLECTION, {"_id": ObjectId(doc_id)})
        assert found is not None
        assert found["name"] == "find_test"
        assert found["value"] == 100

    async def test_find_documents(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-02-03: 分页查询文档"""
        # 插入多条
        docs = [{"name": f"doc_{i}", "value": i} for i in range(5)]
        for doc in docs:
            await db_mongodb.insert(TEST_COLLECTION, doc)
        
        # 查询
        data, total = await db_mongodb.find(TEST_COLLECTION, page=1, page_size=3)
        assert total == 5
        assert len(data) == 3

    async def test_update_document(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-02-04: 更新单条文档"""
        doc = {"name": "update_test", "value": 1}
        doc_id = await db_mongodb.insert(TEST_COLLECTION, doc)
        
        # 更新
        modified = await db_mongodb.update(
            TEST_COLLECTION,
            {"_id": ObjectId(doc_id)},
            {"value": 2}
        )
        assert modified == 1
        
        # 验证
        updated = await db_mongodb.find_one(TEST_COLLECTION, {"_id": ObjectId(doc_id)})
        assert updated["value"] == 2

    async def test_delete_document(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-02-05: 删除单条文档"""
        doc = {"name": "delete_test", "value": 1}
        doc_id = await db_mongodb.insert(TEST_COLLECTION, doc)
        
        # 删除
        deleted = await db_mongodb.delete(TEST_COLLECTION, {"_id": ObjectId(doc_id)})
        assert deleted == 1
        
        # 验证已删除
        found = await db_mongodb.find_one(TEST_COLLECTION, {"_id": ObjectId(doc_id)})
        assert found is None


# ==================== SC-MG-03 MongoDB 查询功能 ====================

@pytest.fixture
async def sample_docs(mongodb_pool):
    """测试用的示例数据 fixture"""
    docs = [
        {"name": "alice", "age": 25},
        {"name": "bob", "age": 30},
        {"name": "charlie", "age": 35},
        {"name": "david", "age": 40},
        {"name": "eve", "age": 45},
    ]
    await mongodb_pool[TEST_COLLECTION].insert_many(docs)
    yield
    # 清理
    await mongodb_pool[TEST_COLLECTION].delete_many({})


@pytest.mark.integration
@pytest.mark.db
class TestMongoDBQuery:
    """MongoDB 查询功能测试"""

    async def test_query_dict(self, db_mongodb: DatabaseLayerV2, sample_docs):
        """TC-MG-03-01: 条件查询（字典）"""
        data, total = await db_mongodb.find(TEST_COLLECTION, {"age": {"$gt": 30}})
        assert total == 3
        names = [d["name"] for d in data]
        assert "charlie" in names
        assert "david" in names
        assert "eve" in names

    async def test_query_condition_builder(self, db_mongodb: DatabaseLayerV2, sample_docs):
        """TC-MG-03-02: 条件查询（ConditionBuilder）"""
        condition = ConditionBuilder().gt("age", 30)
        data, total = await db_mongodb.find(TEST_COLLECTION, condition)
        assert total == 3

    async def test_query_query_builder(self, db_mongodb: DatabaseLayerV2, sample_docs):
        """TC-MG-03-03: 条件查询（QueryBuilder）"""
        qb = QueryBuilder().gt("age", 30).paginate(1, 2)
        data, total = await db_mongodb.find(TEST_COLLECTION, qb)
        assert total == 3
        assert len(data) == 2

    async def test_query_projection(self, db_mongodb: DatabaseLayerV2, sample_docs):
        """TC-MG-03-04: 投影查询"""
        data, _ = await db_mongodb.find(
            TEST_COLLECTION,
            projection={"name": 1, "_id": 0}
        )
        assert len(data) > 0
        for doc in data:
            assert "name" in doc
            assert "age" not in doc

    async def test_query_sort(self, db_mongodb: DatabaseLayerV2, sample_docs):
        """TC-MG-03-05: 排序查询"""
        data, _ = await db_mongodb.find(
            TEST_COLLECTION,
            sort=[("age", 1)]
        )
        ages = [d["age"] for d in data]
        assert ages == sorted(ages)

    async def test_query_boundary(self, db_mongodb: DatabaseLayerV2, sample_docs):
        """TC-MG-03-06: 分页边界测试"""
        with pytest.raises(ValueError):
            await db_mongodb.find(TEST_COLLECTION, page=0)
        
        with pytest.raises(ValueError):
            await db_mongodb.find(TEST_COLLECTION, page_size=0)
        
        with pytest.raises(ValueError):
            await db_mongodb.find(TEST_COLLECTION, page_size=101)


# ==================== SC-MG-04 MongoDB 更新功能 ====================

@pytest.mark.integration
@pytest.mark.db
class TestMongoDBUpdate:
    """MongoDB 更新功能测试"""

    async def test_update_normal(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-04-01: 普通更新（$set）"""
        doc = {"name": "test", "value": 1}
        doc_id = await db_mongodb.insert(TEST_COLLECTION, doc)
        
        modified = await db_mongodb.update(
            TEST_COLLECTION,
            {"_id": ObjectId(doc_id)},
            {"$set": {"value": 2}}
        )
        assert modified == 1

    async def test_update_not_exist(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-04-02: 更新不存在的文档"""
        modified = await db_mongodb.update(
            TEST_COLLECTION,
            {"_id": ObjectId("507f1f77bcf86cd799439011")},
            {"value": 999}
        )
        assert modified == 0

    async def test_update_upsert(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-04-03: upsert 更新"""
        query = {"name": "upsert_test"}
        modified = await db_mongodb.update(
            TEST_COLLECTION,
            query,
            {"value": 100},
            upsert=True
        )
        assert modified == 0  # upsert 时 modified_count 为 0
        
        # 验证文档被插入
        inserted = await db_mongodb.find_one(TEST_COLLECTION, query)
        assert inserted is not None
        assert inserted["value"] == 100

    async def test_update_auto_set(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-04-04: 自动 $set 包装"""
        doc = {"name": "auto_set_test", "value": 1}
        doc_id = await db_mongodb.insert(TEST_COLLECTION, doc)
        
        # 传入不带 $set 的数据
        modified = await db_mongodb.update(
            TEST_COLLECTION,
            {"_id": ObjectId(doc_id)},
            {"value": 2}  # 不带 $set
        )
        assert modified == 1


# ==================== SC-MG-05 MongoDB 删除功能 ====================

@pytest.mark.integration
@pytest.mark.db
class TestMongoDBDelete:
    """MongoDB 删除功能测试"""

    async def test_delete_exist(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-05-01: 删除存在的文档"""
        doc = {"name": "delete_exist", "value": 1}
        doc_id = await db_mongodb.insert(TEST_COLLECTION, doc)
        
        deleted = await db_mongodb.delete(TEST_COLLECTION, {"_id": ObjectId(doc_id)})
        assert deleted == 1

    async def test_delete_not_exist(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-05-02: 删除不存在的文档"""
        deleted = await db_mongodb.delete(
            TEST_COLLECTION,
            {"_id": ObjectId("507f1f77bcf86cd799439011")}
        )
        assert deleted == 0

    async def test_delete_empty_query(self):
        """TC-MG-05-03: 禁止空查询删除（mongodb.py 层）"""
        await init_mongodb()
        with pytest.raises(ValueError):
            await mongo_delete_one(TEST_COLLECTION, {})
        await close_mongodb()


# ==================== SC-MG-06 MongoDB 并发隔离性 ====================

@pytest.mark.integration
@pytest.mark.db
class TestMongoDBConcurrency:
    """MongoDB 并发隔离性测试"""

    async def test_concurrent_insert(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-06-01: 并发插入文档"""
        async def insert_task(i: int):
            await db_mongodb.insert(TEST_COLLECTION, {"index": i})
        
        tasks = [insert_task(i) for i in range(10)]
        await asyncio.gather(*tasks)
        
        data, total = await db_mongodb.find(TEST_COLLECTION, page_size=100)
        assert total == 10

    async def test_concurrent_update_same(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-06-02: 并发更新同一文档"""
        doc_id = await db_mongodb.insert(TEST_COLLECTION, {"value": 0, "updates": 0})
        
        async def update_task(new_val: int):
            # 使用 $inc 操作符来确保并发安全计数
            await db_mongodb.update(
                TEST_COLLECTION,
                {"_id": ObjectId(doc_id)},
                {"$set": {"value": new_val}, "$inc": {"updates": 1}}
            )
        
        tasks = [update_task(i) for i in range(5)]
        await asyncio.gather(*tasks)
        
        # 检查是否所有 5 次更新都成功执行
        updated = await db_mongodb.find_one(TEST_COLLECTION, {"_id": ObjectId(doc_id)})
        assert updated["updates"] == 5


# ==================== SC-MG-07 MongoDB 错误处理与异常 ====================

@pytest.mark.integration
@pytest.mark.db
class TestMongoDBErrorHandling:
    """MongoDB 错误处理测试"""

    async def test_forbidden_where(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-07-01: 禁止危险操作符（$where）"""
        with pytest.raises(ValueError):
            await db_mongodb.find_one(TEST_COLLECTION, {"$where": "this.value > 0"})

    async def test_forbidden_expr(self, db_mongodb: DatabaseLayerV2):
        """TC-MG-07-02: 禁止危险操作符（$expr）"""
        with pytest.raises(ValueError):
            await db_mongodb.find_one(TEST_COLLECTION, {"$expr": {"$gt": ["$value", 0]}})

    async def test_update_missing_set(self):
        """TC-MG-07-03: 更新操作缺少 $set 操作符（mongodb.py 层）"""
        await init_mongodb()
        await mongo_insert_one(TEST_COLLECTION, {"name": "test"})
        with pytest.raises(ValueError):
            await mongo_update_one(TEST_COLLECTION, {"name": "test"}, {"name": "new"})  # 不带 $set
        await close_mongodb()

    async def test_db_not_initialized(self):
        """TC-MG-07-04: DatabaseLayerV2 未初始化"""
        db = DatabaseLayerV2()
        with pytest.raises(RuntimeError):
            await db.insert(TEST_COLLECTION, {"name": "test"})


# ==================== SC-MG-08 DatabaseLayerV2 数据库切换 ====================

@pytest.mark.integration
@pytest.mark.db
class TestDatabaseSwitch:
    """数据库切换测试"""

    async def test_switch_to_mongodb(self, db_mongodb: DatabaseLayerV2, mongodb_pool):
        """TC-MG-08-01: 切换到 MongoDB 并操作"""
        db_mongodb.set_database("mongodb")
        doc_id = await db_mongodb.insert(TEST_COLLECTION, {"name": "switch_test"})
        assert doc_id is not None

    async def test_switch_between_databases(self, db: DatabaseLayerV2, mysql_pool, mongodb_pool):
        """TC-MG-08-02: 切换回 MySQL 并操作"""
        # 先插入 MongoDB
        db.set_database("mongodb")
        await db.insert(TEST_COLLECTION, {"name": "mongodb_test"})
        
        # 切换回 MySQL
        db.set_database("mysql")
        await db.insert("test_table", {"name": "mysql_test"})
        
        # 验证 MySQL 数据
        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM test_table WHERE name = 'mysql_test'")
                row = await cur.fetchone()
                assert row is not None

    async def test_concurrent_database_isolation(self, db: DatabaseLayerV2, mysql_pool, mongodb_pool):
        """TC-MG-08-03: 不同任务数据库类型隔离"""
        async def task_mongodb():
            db.set_database("mongodb")
            await db.insert(TEST_COLLECTION, {"name": "task_mongodb"})
            db.set_database("mysql")  # 还原
        
        async def task_mysql():
            db.set_database("mysql")
            await db.insert("test_table", {"name": "task_mysql"})
        
        await asyncio.gather(task_mongodb(), task_mysql())
        
        # 验证两个任务都成功
        db.set_database("mongodb")
        mongodb_doc, _ = await db.find(TEST_COLLECTION, {"name": "task_mongodb"})
        assert len(mongodb_doc) == 1
        
        db.set_database("mysql")
        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM test_table WHERE name = 'task_mysql'")
                row = await cur.fetchone()
                assert row is not None
