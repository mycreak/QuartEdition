"""
test_task_failure_service.py

TaskFailureService 服务层集成测试。

测试标记：
    @pytest.mark.integration
    @pytest.mark.services
    @pytest.mark.task_failure
"""

import pytest
import json

from db.database_v2 import DatabaseLayerV2
from services.task_failure_service import TaskFailureService
from utils.errors import NotFoundError


# ==================== 测试辅助函数 ====================

_SERIAL_TASK_ID = 100

async def create_test_history(
    db: DatabaseLayerV2,
    task_id: int = 1,
    admin_id: int = 999,
    task_type: str = "movie_crawl",
    task_params: dict = None,
) -> int:
    """创建测试用 task_history 记录（供 LEFT JOIN 验证）。"""
    params_json = json.dumps(task_params or {"id": task_id, "type": task_type}, ensure_ascii=False)
    sql = (
        "INSERT INTO task_history (id, admin_id, task_type, task_params, status) "
        "VALUES (%s, %s, %s, %s, 'failed')"
    )
    raw = db.raw_mysql()
    await raw.execute_insert(sql, (task_id, admin_id, task_type, params_json))
    return task_id


async def create_test_failure(
    db: DatabaseLayerV2,
    status: str = "pending",
    claimed_by: int = 0,
    retry_count: int = 0,
    scope: str = "batch",
    item_douban_id: str = "",
    item_title: str = "",
    task_id: int = 1,
    failure_layer: str = "crawler",
) -> int:
    """创建测试失败记录，返回 ID。"""
    sql = """
        INSERT INTO task_failures
        (task_id, worker_id, kind, failure_layer, reason,
         status, claimed_by, retry_count, scope,
         item_douban_id, item_title)
        VALUES (%s, 1, 'network', %s, '测试失败',
                %s, %s, %s, %s, %s, %s)
    """
    raw = db.raw_mysql()
    return await raw.execute_insert(sql, (
        task_id, failure_layer, status, claimed_by, retry_count,
        scope, item_douban_id, item_title,
    ))


async def get_failure_by_id(db: DatabaseLayerV2, failure_id: int) -> dict:
    """从数据库直接查询失败记录。"""
    rows = await db.execute_raw(
        "SELECT * FROM task_failures WHERE id = %s", (failure_id,)
    )
    return rows[0] if rows else None


# ==================== 测试类 ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.task_failure
class TestTaskFailureService:

    # ==================== 场景 1：失败记录查询 ====================

    async def test_query_list_all_failures(self, db: DatabaseLayerV2):
        """TC-Query-01: 查询所有失败记录（status=None）。"""
        service = TaskFailureService(db)
        # 创建 task_history 记录以验证 JOIN 注入
        await create_test_history(db, task_id=1, admin_id=999, task_type="movie_crawl")
        await create_test_history(db, task_id=2, admin_id=888, task_type="review_crawl")
        fid1 = await create_test_failure(db, status="pending", task_id=1)
        fid2 = await create_test_failure(db, status="claimed", task_id=2)

        items, total = await service.list_task_failures(status=None)

        assert total >= 2
        assert any(f["id"] == fid1 for f in items)
        assert any(f["id"] == fid2 for f in items)
        # 验证 JOIN 注入的字段
        for item in items:
            assert "task_params" in item
            assert "admin_id" in item
            assert "task_type" in item

    async def test_query_join_injects_admin_id(self, db: DatabaseLayerV2):
        """TC-Query-01b: LEFT JOIN 正确注入 admin_id 和 task_params。"""
        service = TaskFailureService(db)
        await create_test_history(db, task_id=10, admin_id=777, task_type="movie_crawl",
                                  task_params={"id": 10, "type": "movie_crawl", "douban_id": "12345"})
        fid = await create_test_failure(db, task_id=10)

        failure = await service.get_failure(fid)
        assert failure["admin_id"] == 777
        assert failure["task_type"] == "movie_crawl"
        assert failure["task_params"] == {"id": 10, "type": "movie_crawl", "douban_id": "12345"}

    async def test_query_join_none_when_no_history(self, db: DatabaseLayerV2):
        """TC-Query-01c: 无 task_history 关联时 LEFT JOIN 返回 NULL（不抛异常）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(db, task_id=99999)

        failure = await service.get_failure(fid)
        assert failure["id"] == fid
        assert failure["status"] == "pending"
        # LEFT JOIN 无匹配时 task_params 为 None
        assert failure["admin_id"] is None or failure["admin_id"] == 0
        assert failure["task_type"] is None or failure["task_type"] == ""

    async def test_query_list_by_status(self, db: DatabaseLayerV2):
        """TC-Query-02: 按 status 过滤查询。"""
        service = TaskFailureService(db)
        await create_test_failure(db, status="pending")
        await create_test_failure(db, status="pending")
        await create_test_failure(db, status="resolved")

        items, total = await service.list_task_failures(status="pending")

        assert total >= 2
        assert all(f["status"] == "pending" for f in items)

    async def test_query_pagination(self, db: DatabaseLayerV2):
        """TC-Query-03: 分页查询。"""
        service = TaskFailureService(db)
        for i in range(5):
            await create_test_failure(db)

        items1, total1 = await service.list_task_failures(page=1, page_size=2)
        items2, total2 = await service.list_task_failures(page=2, page_size=2)

        assert total1 == total2
        assert len(items1) == 2
        assert len(items2) == 2
        ids1 = {f["id"] for f in items1}
        ids2 = {f["id"] for f in items2}
        assert ids1 & ids2 == set()

    async def test_query_get_single_failure(self, db: DatabaseLayerV2):
        """TC-Query-04: 查询单个失败记录（成功路径）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(db)

        failure = await service.get_failure(fid)

        assert failure["id"] == fid
        assert failure["status"] == "pending"

    async def test_query_get_not_found(self, db: DatabaseLayerV2):
        """TC-Query-05: 查询不存在的失败记录（抛 NotFoundError）。"""
        service = TaskFailureService(db)

        with pytest.raises(NotFoundError):
            await service.get_failure(99999)

    # ==================== 场景 2：写入失败记录 ====================

    async def test_write_batch_failure(self, db: DatabaseLayerV2):
        """TC-Write-01: 写入 batch 级失败。"""
        service = TaskFailureService(db)

        fid = await service.write_batch_failure(
            task_id=1234,
            worker_id=1,
            kind="network",
            reason="测试 batch 失败",
            parent_failure_id=0,
            failure_layer="crawler",
            task_type="movie_crawl",
            douban_id="",
        )

        assert fid > 0
        row = await get_failure_by_id(db, fid)
        assert row["scope"] == "batch"
        assert row["status"] == "pending"
        assert row["kind"] == "network"
        assert row["failure_layer"] == "crawler"

    async def test_write_batch_failure_minimal(self, db: DatabaseLayerV2):
        """TC-Write-01b: 最少参数写入 batch 级失败。"""
        service = TaskFailureService(db)

        fid = await service.write_batch_failure(
            task_id=5678,
            worker_id=2,
            kind="timeout",
            reason="超时",
        )

        assert fid > 0
        row = await get_failure_by_id(db, fid)
        assert row["scope"] == "batch"
        assert row["failure_layer"] == "crawler"  # 默认值

    async def test_write_item_failure(self, db: DatabaseLayerV2):
        """TC-Write-02: 写入 item 级失败。"""
        service = TaskFailureService(db)

        fid = await service.write_item_failure(
            task_id=5678,
            admin_id=99,
            kind="parse",
            reason="解析失败",
            item_douban_id="123456",
            item_title="肖申克的救赎",
            parent_failure_id=0,
        )

        assert fid > 0
        row = await get_failure_by_id(db, fid)
        assert row["scope"] == "item"
        assert row["item_douban_id"] == "123456"
        assert row["item_title"] == "肖申克的救赎"

    async def test_insert_failure_entry(self, db: DatabaseLayerV2):
        """TC-Write-03: insert_failure 入口分发。"""
        service = TaskFailureService(db)

        fid_batch = await service.insert_failure(
            task_id=1,
            admin_id=100,
            kind="network",
            reason="batch test",
            scope="batch",
            task_type="movie_crawl",
        )
        fid_item = await service.insert_failure(
            task_id=2,
            admin_id=200,
            kind="parse",
            reason="item test",
            scope="item",
            item_douban_id="test123",
            item_title="测试电影",
        )

        row_batch = await get_failure_by_id(db, fid_batch)
        row_item = await get_failure_by_id(db, fid_item)
        assert row_batch["scope"] == "batch"
        assert row_item["scope"] == "item"
