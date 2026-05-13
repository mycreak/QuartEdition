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
import asyncio
from datetime import datetime

from db.database_v2 import DatabaseLayerV2
from services.task_failure_service import TaskFailureService, MAX_RETRY
from utils.errors import (
    NotFoundError, ClaimConflictError, ClaimNotYoursError,
    RetriesExceededError, ServiceError,
)


# ==================== 测试辅助函数 ====================

async def create_test_failure(
    db: DatabaseLayerV2,
    status: str = "pending",
    claimed_by: int = 0,
    retry_count: int = 0,
    scope: str = "batch",
    item_douban_id: str = "",
    item_title: str = "",
    task_json: str = '{"id": 123, "type": "movie_crawl"}',
) -> int:
    """创建测试失败记录，返回 ID。"""
    sql = """
        INSERT INTO task_failures
        (task_id, worker_id, task_json, event_type, kind, reason,
         admin_id, status, claimed_by, retry_count, scope,
         item_douban_id, item_title)
        VALUES (1, 1, %s, 'failure', 'network', '测试失败',
                0, %s, %s, %s, %s, %s, %s)
    """
    raw = db.raw_mysql()
    return await raw.execute_insert(sql, (
        task_json, status, claimed_by, retry_count,
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
        fid1 = await create_test_failure(db, status="pending")
        fid2 = await create_test_failure(db, status="claimed")

        items, total = await service.list_task_failures(status=None)

        assert total >= 2
        assert any(f["id"] == fid1 for f in items)
        assert any(f["id"] == fid2 for f in items)

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
        # 验证不重复
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

    # ==================== 场景 2：认领失败任务 ====================

    async def test_claim_pending_success(self, db: DatabaseLayerV2):
        """TC-Claim-01: 认领 pending 状态的任务（成功）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(db, status="pending")
        admin_id = 1001

        result = await service.claim_failure(fid, admin_id)

        assert result is True
        row = await get_failure_by_id(db, fid)
        assert row["status"] == "claimed"
        assert row["claimed_by"] == admin_id
        assert row["claimed_at"] is not None

    async def test_claim_idempotent(self, db: DatabaseLayerV2):
        """TC-Claim-02: 重复认领（幂等返回 True）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(db, status="pending")
        admin_id = 1002

        await service.claim_failure(fid, admin_id)
        result = await service.claim_failure(fid, admin_id)

        assert result is True

    async def test_claim_not_found(self, db: DatabaseLayerV2):
        """TC-Claim-03: 认领不存在的任务（抛 ClaimConflictError）。"""
        service = TaskFailureService(db)

        with pytest.raises(ClaimConflictError):
            await service.claim_failure(99999, 1003)

    async def test_claim_conflict_others(self, db: DatabaseLayerV2):
        """TC-Claim-04: 认领已被别人认领的任务（抛 ClaimConflictError）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(db, status="claimed", claimed_by=2000)

        with pytest.raises(ClaimConflictError):
            await service.claim_failure(fid, 1004)

    async def test_claim_concurrent(self, db: DatabaseLayerV2):
        """TC-Claim-05: 并发认领测试（只有一个能成功）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(db, status="pending")

        success_count = 0
        errors = []

        async def claim_task(admin_id: int):
            nonlocal success_count
            try:
                await service.claim_failure(fid, admin_id)
                success_count += 1
            except ClaimConflictError:
                pass

        await asyncio.gather(
            claim_task(3001),
            claim_task(3002),
            claim_task(3003),
        )

        assert success_count == 1

    # ==================== 场景 3：释放认领 ====================

    async def test_release_success(self, db: DatabaseLayerV2):
        """TC-Release-01: 释放自己认领的任务（成功）。"""
        service = TaskFailureService(db)
        admin_id = 4001
        fid = await create_test_failure(
            db, status="claimed", claimed_by=admin_id
        )

        result = await service.release_failure(fid, admin_id)

        assert result is True
        row = await get_failure_by_id(db, fid)
        assert row["status"] == "pending"
        assert row["claimed_by"] == 0

    async def test_release_not_yours(self, db: DatabaseLayerV2):
        """TC-Release-02: 释放不是自己认领的任务（抛 ClaimNotYoursError）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(db, status="claimed", claimed_by=5000)

        with pytest.raises(ClaimNotYoursError):
            await service.release_failure(fid, 4002)

    async def test_release_not_found(self, db: DatabaseLayerV2):
        """TC-Release-03: 释放不存在的任务（抛 ClaimNotYoursError）。"""
        service = TaskFailureService(db)

        with pytest.raises(ClaimNotYoursError):
            await service.release_failure(99999, 4003)

    # ==================== 场景 4：解决失败任务 ====================

    async def test_resolve_success(self, db: DatabaseLayerV2):
        """TC-Resolve-01: 解决自己认领的任务（成功）。"""
        service = TaskFailureService(db)
        admin_id = 5001
        fid = await create_test_failure(
            db, status="claimed", claimed_by=admin_id
        )

        result = await service.resolve_failure(fid, admin_id)

        assert result is True
        row = await get_failure_by_id(db, fid)
        assert row["status"] == "resolved"
        assert row["resolved_at"] is not None

    async def test_resolve_not_yours(self, db: DatabaseLayerV2):
        """TC-Resolve-02: 解决不是自己认领的任务（抛 ClaimNotYoursError）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(db, status="claimed", claimed_by=6000)

        with pytest.raises(ClaimNotYoursError):
            await service.resolve_failure(fid, 5002)

    async def test_resolve_not_found(self, db: DatabaseLayerV2):
        """TC-Resolve-03: 解决不存在的任务（抛 ClaimNotYoursError）。"""
        service = TaskFailureService(db)

        with pytest.raises(ClaimNotYoursError):
            await service.resolve_failure(99999, 5003)

    # ==================== 场景 5：写入失败记录 ====================

    async def test_write_batch_failure(self, db: DatabaseLayerV2):
        """TC-Write-01: 写入 batch 级失败。"""
        service = TaskFailureService(db)
        task_json = '{"id": 1234, "type": "movie_crawl"}'

        fid = await service.write_batch_failure(
            task_id=1234,
            worker_id=1,
            task_json=task_json,
            event_type="failure",
            kind="network",
            reason="测试 batch 失败",
            admin_id=0,
            parent_failure_id=0,
        )

        assert fid > 0
        row = await get_failure_by_id(db, fid)
        assert row["scope"] == "batch"
        assert row["status"] == "pending"

    async def test_write_item_failure(self, db: DatabaseLayerV2):
        """TC-Write-02: 写入 item 级失败。"""
        service = TaskFailureService(db)
        task_json = '{"id": 5678, "type": "movie_crawl", "admin_id": 99}'

        fid = await service.write_item_failure(
            task_json=task_json,
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
            task='{"id": 1}',
            kind="network",
            reason="batch test",
            scope="batch",
        )
        fid_item = await service.insert_failure(
            task='{"id": 2}',
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

    # ==================== 场景 6：重爬任务构造 ====================

    async def test_build_retry_batch(self, db: DatabaseLayerV2):
        """TC-Retry-01: 从 batch 失败记录构造重爬任务。"""
        service = TaskFailureService(db)
        admin_id = 7001
        fid = await create_test_failure(
            db,
            status="claimed",
            claimed_by=admin_id,
            scope="batch",
            task_json='{"id": 999, "type": "movie_crawl"}',
        )

        retry_json = await service.build_retry_task(fid, admin_id)
        retry_data = json.loads(retry_json)

        assert retry_data["id"] == 999
        assert retry_data["type"] == "movie_crawl"
        assert retry_data["parent_failure_id"] == fid

    async def test_build_retry_item(self, db: DatabaseLayerV2):
        """TC-Retry-02: 从 item 失败记录构造重爬任务。"""
        service = TaskFailureService(db)
        admin_id = 7002
        fid = await create_test_failure(
            db,
            status="claimed",
            claimed_by=admin_id,
            scope="item",
            item_douban_id="12345678",
            item_title="阿甘正传",
        )

        retry_json = await service.build_retry_task(fid, admin_id)
        retry_data = json.loads(retry_json)

        assert retry_data["type"] == "director_crawl"
        assert retry_data["douban_id"] == "12345678"
        assert retry_data["parent_failure_id"] == fid

    async def test_build_retry_exceeded(self, db: DatabaseLayerV2):
        """TC-Retry-03: 重试次数超限（抛 RetriesExceededError）。"""
        service = TaskFailureService(db)
        admin_id = 7003
        fid = await create_test_failure(
            db,
            status="claimed",
            claimed_by=admin_id,
            retry_count=MAX_RETRY,
        )

        with pytest.raises(RetriesExceededError):
            await service.build_retry_task(fid, admin_id)

    async def test_build_retry_not_yours(self, db: DatabaseLayerV2):
        """TC-Retry-04: 重爬不是自己认领的任务（抛 ClaimNotYoursError）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(
            db, status="claimed", claimed_by=8000
        )

        with pytest.raises(ClaimNotYoursError):
            await service.build_retry_task(fid, 7004)

    async def test_build_retry_invalid_json(self, db: DatabaseLayerV2):
        """TC-Retry-05: 任务 JSON 解析失败（抛 ServiceError）。"""
        service = TaskFailureService(db)
        admin_id = 7005
        fid = await create_test_failure(
            db,
            status="claimed",
            claimed_by=admin_id,
            scope="batch",
            task_json="invalid-json-not-object",
        )

        with pytest.raises(ServiceError):
            await service.build_retry_task(fid, admin_id)

    # ==================== 场景 7：重试计数 ====================

    async def test_increment_retry_once(self, db: DatabaseLayerV2):
        """TC-Count-01: 递增重试计数（从 0 → 1）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(db, retry_count=0)

        count = await service.increment_retry_count(fid)

        assert count == 1
        row = await get_failure_by_id(db, fid)
        assert row["retry_count"] == 1

    async def test_increment_retry_multiple(self, db: DatabaseLayerV2):
        """TC-Count-02: 多次递增（从 0 → 1 → 2）。"""
        service = TaskFailureService(db)
        fid = await create_test_failure(db, retry_count=0)

        count1 = await service.increment_retry_count(fid)
        count2 = await service.increment_retry_count(fid)

        assert count1 == 1
        assert count2 == 2
