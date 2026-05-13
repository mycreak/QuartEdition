
"""
MySQL 数据库层集成测试
测试 db/mysql.py 和 db/database_v2.py 的 MySQL 实现
"""

import pytest
import asyncio

from db.mysql import (
    execute_query,
    execute_one,
    execute_update,
    execute_insert,
    execute_paginated_query,
    init_mysql,
    close_mysql,
    get_mysql_pool,
)
from db.database_v2 import DatabaseLayerV2
from db.query_builder import ConditionBuilder, QueryBuilder


@pytest.mark.integration
@pytest.mark.db
class TestMySQLConnectionPool:
    """场景 1: 连接池管理测试"""

    async def test_connection_pool_init(self, mysql_pool):
        """DB-1.1: 初始化 MySQL 连接池成功"""
        assert mysql_pool is not None
        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                result = await cur.fetchone()
                assert result is not None

    async def test_uninitialized_operation(self):
        """DB-1.3: 未初始化时调用操作"""
        try:
            await close_mysql()
        except Exception:
            pass
        with pytest.raises(RuntimeError):
            get_mysql_pool()
        await init_mysql()


@pytest.mark.integration
@pytest.mark.db
class TestMySQLBasicOperations:
    """场景 2: 基础查询操作 - 使用 db fixture 表"""

    async def test_execute_query_basic(self, db):
        """DB-2.1: execute_query 基础查询"""
        await db.insert("test_table", {"name": "test1"})
        await db.insert("test_table", {"name": "test2"})
        
        results = await execute_query("SELECT * FROM test_table")
        assert len(results) == 2

    async def test_execute_one(self, db):
        """DB-2.2: execute_one 查询单条"""
        await db.insert("test_table", {"name": "single_test"})
        result = await execute_one("SELECT * FROM test_table WHERE name = %s", ("single_test",))
        assert result is not None
        assert result["name"] == "single_test"

    async def test_query_no_params(self, db):
        """DB-2.3: 无参数查询"""
        await db.insert("test_table", {"name": "test"})
        result = await execute_one("SELECT * FROM test_table LIMIT 1")
        assert result is not None

    async def test_query_multiple_params(self, db):
        """DB-2.4: 多参数查询"""
        await db.insert("test_table", {"name": "alice"})
        await db.insert("test_table", {"name": "bob"})
        
        results = await execute_query(
            "SELECT * FROM test_table WHERE name IN (%s, %s)",
            ("alice", "bob")
        )
        assert len(results) == 2

    async def test_sql_injection_protection(self, db):
        """DB-2.5: SQL 注入防护测试"""
        evil_value = "'; DROP TABLE IF EXISTS nonexistent_table; --"
        inserted_id = await db.insert("test_table", {"name": evil_value})
        
        result = await db.find_one("test_table", {"id": inserted_id})
        assert result is not None
        assert result["name"] == evil_value


@pytest.mark.integration
@pytest.mark.db
class TestMySQLWriteOperations:
    """场景 3: 数据写入操作"""

    async def test_execute_insert(self, db):
        """DB-3.1: execute_insert 插入记录"""
        inserted_id = await execute_insert(
            "INSERT INTO test_table (name) VALUES (%s)",
            ("insert_test",)
        )
        assert inserted_id is not None
        
        result = await db.find_one("test_table", {"id": inserted_id})
        assert result is not None
        assert result["name"] == "insert_test"

    async def test_execute_update(self, db):
        """DB-3.2: execute_update 更新记录"""
        inserted_id = await db.insert("test_table", {"name": "before"})
        
        affected = await execute_update(
            "UPDATE test_table SET name = %s WHERE id = %s",
            ("after", inserted_id)
        )
        assert affected == 1
        
        result = await db.find_one("test_table", {"id": inserted_id})
        assert result["name"] == "after"

    async def test_execute_delete(self, db):
        """DB-3.3: execute_delete 删除记录"""
        inserted_id = await db.insert("test_table", {"name": "to_delete"})
        
        affected = await execute_update(
            "DELETE FROM test_table WHERE id = %s",
            (inserted_id,)
        )
        assert affected == 1
        
        result = await db.find_one("test_table", {"id": inserted_id})
        assert result is None


@pytest.mark.integration
@pytest.mark.db
class TestMySQLPagination:
    """场景 4: 分页查询"""

    async def test_basic_pagination(self, db):
        """DB-4.1: 基础分页查询"""
        for i in range(25):
            await db.insert("test_table", {"name": f"item_{i:02d}"})
        
        data, total = await db.find("test_table", page=2, page_size=10)
        assert len(data) == 10
        assert total == 25
        
        sql = "SELECT * FROM test_table ORDER BY id"
        data2, total2 = await execute_paginated_query(sql, page=2, page_size=10)
        assert len(data2) == 10
        assert total2 == 25

    async def test_pagination_page_less_than_one(self):
        """DB-4.2: page < 1 边界测试"""
        with pytest.raises(ValueError):
            await execute_paginated_query("SELECT * FROM test_table", page=0, page_size=10)

    async def test_pagination_page_size_out_of_range(self):
        """DB-4.3: page_size 超出范围"""
        with pytest.raises(ValueError):
            await execute_paginated_query("SELECT * FROM test_table", page=1, page_size=0)
        with pytest.raises(ValueError):
            await execute_paginated_query("SELECT * FROM test_table", page=1, page_size=101)

    async def test_pagination_empty_dataset(self, db):
        """DB-4.4: 空数据集分页"""
        data, total = await db.find("test_table", page=1, page_size=10)
        assert len(data) == 0
        assert total == 0


@pytest.mark.integration
@pytest.mark.db
class TestDatabaseLayerV2MySQL:
    """场景 5: DatabaseLayerV2 CRUD"""

    async def test_db_layer_insert(self, db):
        """DB-5.1: insert 插入记录"""
        inserted_id = await db.insert("test_table", {"name": "layer_test"})
        assert inserted_id is not None
        
        result = await db.find_one("test_table", {"id": inserted_id})
        assert result is not None

    async def test_db_layer_find(self, db):
        """DB-5.2: find 查询多条"""
        await db.insert("test_table", {"name": "a"})
        await db.insert("test_table", {"name": "b"})
        
        data, total = await db.find("test_table")
        assert total == 2
        assert len(data) == 2

    async def test_db_layer_find_one(self, db):
        """DB-5.3: find_one 查询单条"""
        inserted_id = await db.insert("test_table", {"name": "find_one_test"})
        
        result = await db.find_one("test_table", {"id": inserted_id})
        assert result is not None
        assert result["id"] == inserted_id
        
        not_found = await db.find_one("test_table", {"id": 99999})
        assert not_found is None

    async def test_db_layer_update(self, db):
        """DB-5.4: update 更新记录"""
        inserted_id = await db.insert("test_table", {"name": "old_name"})
        
        affected = await db.update("test_table", {"id": inserted_id}, {"name": "new_name"})
        assert affected == 1
        
        result = await db.find_one("test_table", {"id": inserted_id})
        assert result["name"] == "new_name"

    async def test_db_layer_delete(self, db):
        """DB-5.5: delete 删除记录"""
        inserted_id = await db.insert("test_table", {"name": "to_delete"})
        
        affected = await db.delete("test_table", {"id": inserted_id})
        assert affected == 1
        
        result = await db.find_one("test_table", {"id": inserted_id})
        assert result is None

    async def test_db_layer_with_condition_builder(self, db):
        """DB-5.6: 使用 ConditionBuilder 查询"""
        await db.insert("test_table", {"name": "a"})
        await db.insert("test_table", {"name": "b"})
        await db.insert("test_table", {"name": "c"})
        
        cb = ConditionBuilder()
        cb.like("name", "a", position="both")
        
        data, total = await db.find("test_table", conditions=cb)
        assert total == 1
        assert data[0]["name"] == "a"

    async def test_db_layer_with_query_builder(self, db):
        """DB-5.7: 使用 QueryBuilder 查询"""
        for i in range(5):
            await db.insert("test_table", {"name": f"qb_test_{i}"})
        
        qb = QueryBuilder()
        qb.sort("name", "desc").paginate(1, 3)
        
        data, total = await db.find("test_table", conditions=qb)
        assert total == 5
        assert len(data) == 3


@pytest.mark.integration
@pytest.mark.db
class TestMySQLTransactions:
    """场景 6: 事务支持"""

    async def test_transaction_commit(self, db):
        """DB-6.1: 事务正常提交"""
        async with db.transaction() as tx:
            await tx.insert("test_table", {"name": "tx_commit"})
        
        result = await db.find_one("test_table", {"name": "tx_commit"})
        assert result is not None

    async def test_transaction_rollback(self, db):
        """DB-6.2: 事务异常回滚"""
        try:
            async with db.transaction() as tx:
                await tx.insert("test_table", {"name": "tx_rollback"})
                raise ValueError("故意异常")
        except ValueError:
            pass
        
        result = await db.find_one("test_table", {"name": "tx_rollback"})
        assert result is None

    async def test_transaction_crud(self, db):
        """DB-6.3: 事务上下文 CRUD"""
        async with db.transaction() as tx:
            inserted_id = await tx.insert("test_table", {"name": "tx_crud"})
            found = await tx.find_one("test_table", {"id": inserted_id})
            assert found is not None
            updated = await tx.update("test_table", {"id": inserted_id}, {"name": "tx_updated"})
            assert updated == 1
            deleted = await tx.delete("test_table", {"id": inserted_id})
            assert deleted == 1


@pytest.mark.integration
@pytest.mark.db
class TestMySQLRawAccess:
    """场景 7: 原生访问接口"""

    async def test_raw_mysql_execute_query(self, db):
        """DB-7.1: raw_mysql.execute_query"""
        await db.insert("test_table", {"name": "raw_test"})
        
        raw = db.raw_mysql()
        results = await raw.execute_query("SELECT * FROM test_table")
        assert len(results) == 1

    async def test_raw_mysql_execute_update(self, db):
        """DB-7.2: raw_mysql.execute_update"""
        inserted_id = await db.insert("test_table", {"name": "before_raw"})
        
        raw = db.raw_mysql()
        affected = await raw.execute_update(
            "UPDATE test_table SET name = %s WHERE id = %s",
            ("after_raw", inserted_id)
        )
        assert affected == 1

    async def test_raw_mysql_execute_insert(self, db):
        """DB-7.3: raw_mysql.execute_insert"""
        raw = db.raw_mysql()
        inserted_id = await raw.execute_insert(
            "INSERT INTO test_table (name) VALUES (%s)",
            ("raw_insert",)
        )
        assert inserted_id is not None

    async def test_execute_raw(self, db):
        """DB-7.4: execute_raw 原生查询"""
        await db.insert("test_table", {"name": "exec_raw_1"})
        await db.insert("test_table", {"name": "exec_raw_2"})
        
        results = await db.execute_raw("SELECT COUNT(*) as cnt FROM test_table")
        assert results[0]["cnt"] == 2


@pytest.mark.integration
@pytest.mark.db
class TestDatabaseTypeSwitch:
    """场景 8: 数据库类型切换"""

    async def test_set_database_type(self, db):
        """DB-8.1: 切换数据库类型到 MySQL"""
        db.set_database("mysql")
        inserted_id = await db.insert("test_table", {"name": "type_test"})
        assert inserted_id is not None

    async def test_initialize_default_type(self):
        """DB-8.2: initialize 指定默认类型"""
        new_db = DatabaseLayerV2()
        await new_db.initialize("mysql")
        assert new_db is not None


@pytest.mark.integration
@pytest.mark.db
class TestMySQLHealthCheck:
    """场景 9: 健康检查"""

    async def test_ping_mysql(self, db):
        """DB-9.1: ping_mysql 正常情况"""
        result = await db.ping_mysql()
        assert result is True

    async def test_ping_all(self, db):
        """DB-9.2: ping_all 并行检查"""
        results = await db.ping_all()
        assert "mysql" in results
        assert isinstance(results["mysql"], bool)


@pytest.mark.integration
@pytest.mark.db
class TestMySQLConnectionIsolation:
    """场景 10: 连接池管理与隔离"""

    async def test_multiple_independent_queries(self, db):
        """DB-10.1: 多次独立查询使用不同连接"""
        id1 = await db.insert("test_table", {"name": "q1"})
        id2 = await db.insert("test_table", {"name": "q2"})
        id3 = await db.insert("test_table", {"name": "q3"})
        
        r1 = await db.find_one("test_table", {"id": id1})
        r2 = await db.find_one("test_table", {"id": id2})
        r3 = await db.find_one("test_table", {"id": id3})
        
        assert r1 is not None
        assert r2 is not None
        assert r3 is not None

    async def test_concurrent_operations(self, db):
        """DB-10.2: 并发操作测试"""
        async def insert_and_query(i):
            name = f"concurrent_{i}"
            await db.insert("test_table", {"name": name})
            result = await db.find_one("test_table", {"name": name})
            return result
        
        tasks = [insert_and_query(i) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for r in results:
            assert not isinstance(r, Exception)
            assert r is not None

    async def test_connection_recovery_on_exception(self, db):
        """DB-10.4: 异常情况下连接回收"""
        try:
            await db.execute_raw("THIS IS INVALID SQL")
        except Exception:
            pass
        
        result = await db.insert("test_table", {"name": "recovery_test"})
        assert result is not None


@pytest.mark.integration
@pytest.mark.db
class TestMySQLSingleOperation:
    """场景 11: 单次 CRUD 操作隔离"""

    async def test_single_operation_isolation(self, db):
        """DB-11.x: 完整的单次操作隔离测试"""
        inserted_id = await db.insert("test_table", {"name": "step1_insert"})
        
        result = await db.find_one("test_table", {"id": inserted_id})
        assert result is not None
        assert result["name"] == "step1_insert"
        
        update_count = await db.update(
            "test_table",
            {"id": inserted_id},
            {"name": "step2_updated"}
        )
        assert update_count == 1
        
        result2 = await db.find_one("test_table", {"id": inserted_id})
        assert result2["name"] == "step2_updated"
        
        delete_count = await db.delete("test_table", {"id": inserted_id})
        assert delete_count == 1
        
        result3 = await db.find_one("test_table", {"id": inserted_id})
        assert result3 is None

