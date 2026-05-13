"""
services/task_failure_service.py

失败任务管理业务层。

职责：
    1. list_task_failures — 分页查询失败任务列表（支持按 status 过滤）
    2. claim_failure      — 原子认领（WHERE status='pending' 防并发抢）
    3. release_failure    — 放弃认领（status → pending）
    4. resolve_failure    — 标记已解决（status → resolved）
    5. build_retry_task   — 从失败记录构造重爬任务 JSON

错误处理：
    所有失败路径抛出 ServiceError 子类，路由层统一捕获。

依赖：
    DatabaseLayerV2 — 注入，读写 MySQL task_failures 表
"""

import json
import logging
from typing import Optional, List, Dict, Any

from db.database_v2 import DatabaseLayerV2
from utils.serializers import serialize_datetime_fields
from utils.errors import (
    ServiceError, NotFoundError, ClaimConflictError, ClaimNotYoursError,
    RetriesExceededError,
)

logger = logging.getLogger(__name__)

MAX_RETRY = 2  # 每个失败记录最多允许重试 2 次


class TaskFailureService:
    """
    失败任务管理。

    输入：DatabaseLayerV2 实例（依赖注入）
    副作用：读写 MySQL task_failures 表
    """

    def __init__(self, db: DatabaseLayerV2):
        self.db = db

    # ═══════════════════════════════════════
    # 查询
    # ═══════════════════════════════════════

    async def list_task_failures(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ):
        """
        分页查询失败任务列表，返回 (列表, total)。

        输入：
            status:    可选过滤 — 'pending' / 'claimed' / 'resolved' / None=全部
            page:      页码（从 1 开始）
            page_size: 每页条数
        输出：(items, total)
        """
        where_clause = ""
        params = []
        if status:
            where_clause = "WHERE status = %s"
            params.append(status)

        count_sql = f"SELECT COUNT(*) AS cnt FROM task_failures {where_clause}"
        count_rows = await self.db.execute_raw(count_sql, tuple(params))
        total = count_rows[0]["cnt"] if count_rows else 0

        offset = (page - 1) * page_size
        sql = (
            f"SELECT * FROM task_failures {where_clause} "
            f"ORDER BY created_at DESC LIMIT %s OFFSET %s"
        )
        params.extend([page_size, offset])

        rows = await self.db.execute_raw(sql, tuple(params))
        return [self._serialize_row(r) for r in rows], total

    async def get_failure(self, failure_id: int) -> Dict[str, Any]:
        """
        输入：failure_id — 失败记录 ID
        输出：dict
        异常：NotFoundError — 记录不存在
        """
        rows = await self.db.execute_raw(
            "SELECT * FROM task_failures WHERE id = %s", (failure_id,)
        )
        if not rows:
            raise NotFoundError("失败记录", failure_id)
        return self._serialize_row(rows[0])

    # ═══════════════════════════════════════
    # 认领 / 释放 / 解决
    # ═══════════════════════════════════════

    async def claim_failure(self, failure_id: int, admin_id: int) -> bool:
        """
        原子认领失败任务。

        输入：failure_id, admin_id
        输出：True
        异常：ClaimConflictError — 已被别人抢走或不存在
        """
        sql = (
            "UPDATE task_failures "
            "SET status = 'claimed', claimed_by = %s, claimed_at = NOW() "
            "WHERE id = %s AND status = 'pending'"
        )
        affected = await self._execute_update(sql, (admin_id, failure_id))
        if affected > 0:
            logger.info(f"失败任务认领成功: id={failure_id} admin_id={admin_id}")
            return True

        # 查询原因：是自己认领的 → 幂等成功，否则抛异常
        try:
            row = await self.get_failure(failure_id)
        except NotFoundError:
            raise ClaimConflictError()

        if row["status"] == "claimed" and row["claimed_by"] == admin_id:
            return True

        raise ClaimConflictError()

    async def release_failure(self, failure_id: int, admin_id: int) -> bool:
        """
        放弃认领。

        输入：failure_id, admin_id
        输出：True
        异常：ClaimNotYoursError — 不是你认领的或不存在
        """
        sql = (
            "UPDATE task_failures "
            "SET status = 'pending', claimed_by = 0, claimed_at = NULL "
            "WHERE id = %s AND claimed_by = %s AND status = 'claimed'"
        )
        affected = await self._execute_update(sql, (failure_id, admin_id))
        if affected > 0:
            logger.info(f"失败任务已释放: id={failure_id} admin_id={admin_id}")
            return True

        raise ClaimNotYoursError("放弃认领")

    async def resolve_failure(self, failure_id: int, admin_id: int) -> bool:
        """
        标记失败任务已解决。

        输入：failure_id, admin_id
        输出：True
        异常：ClaimNotYoursError — 不是你认领的或不存在
        """
        sql = (
            "UPDATE task_failures "
            "SET status = 'resolved', resolved_at = NOW() "
            "WHERE id = %s AND claimed_by = %s"
        )
        affected = await self._execute_update(sql, (failure_id, admin_id))
        if affected > 0:
            logger.info(f"失败任务已解决: id={failure_id} admin_id={admin_id}")
            return True

        raise ClaimNotYoursError("解决")

    # ═══════════════════════════════════════
    # 写入失败事件
    # ═══════════════════════════════════════

    async def write_batch_failure(
        self,
        task_id: int,
        worker_id: int,
        task_json: str,
        event_type: str,
        kind: str,
        reason: str,
        admin_id: int = 0,
        parent_failure_id: int = 0,
    ) -> int:
        """
        写入批次级失败事件（scope='batch'）。

        输入：
            task_id, worker_id, task_json, event_type, kind, reason,
            admin_id, parent_failure_id
        输出：自增 ID
        """
        sql = (
            "INSERT INTO task_failures "
            "(task_id, worker_id, task_json, event_type, kind, reason, "
            "admin_id, status, parent_failure_id, scope) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, 'batch')"
        )
        raw = self.db.raw_mysql()
        fid = await raw.execute_insert(sql, (
            task_id, worker_id, task_json, event_type, kind, reason,
            admin_id, parent_failure_id,
        ))
        logger.info(f"批次失败已记录: id={fid} kind={kind}")
        return fid

    async def write_item_failure(
        self,
        task_json: str,
        kind: str,
        reason: str,
        item_douban_id: str,
        item_title: str,
        parent_failure_id: int = 0,
    ) -> int:
        """
        写入单部电影级失败事件（scope='item'）。

        输入：
            task_json, kind, reason, item_douban_id, item_title, parent_failure_id
        输出：自增 ID
        """
        admin_id = 0
        task_id = 0
        try:
            data = json.loads(task_json)
            admin_id = data.get("admin_id", 0)
            task_id = data.get("id", 0)
        except Exception:
            pass

        sql = (
            "INSERT INTO task_failures "
            "(task_id, worker_id, task_json, event_type, kind, reason, "
            "admin_id, status, parent_failure_id, "
            "scope, item_douban_id, item_title) "
            "VALUES (%s, 0, %s, 'failure', %s, %s, "
            "%s, 'pending', %s, 'item', %s, %s)"
        )
        raw = self.db.raw_mysql()
        fid = await raw.execute_insert(sql, (
            task_id, task_json, kind, reason,
            admin_id, parent_failure_id,
            item_douban_id, item_title,
        ))
        logger.info(
            f"单部电影失败已记录: id={fid} douban_id={item_douban_id} "
            f"title='{item_title}' kind={kind}"
        )
        return fid

    async def insert_failure(
        self,
        *,
        task: str = "",
        admin_id: int = 0,
        kind: str = "unknown",
        reason: str = "",
        scope: str = "batch",
        item_douban_id: str = "",
        item_title: str = "",
    ) -> int:
        """
        crawler 调用入口 — 内部按 scope 分发到 batch/item 写入。

        输入（全部 keyword-only）：
            task:           任务 JSON 字符串
            admin_id:       操作管理员 ID
            kind:           错误分类
            reason:         错误详情
            scope:          'batch'（任务级）或 'item'（单部/单篇级）
            item_douban_id: scope='item' 时的标识（douban_id / review_id / comment_id）
            item_title:     scope='item' 时的摘要（电影名 / 评论标题）
        输出：自增 ID
        副作用：INSERT INTO task_failures
        """
        if scope == "item":
            return await self.write_item_failure(
                task_json=task,
                kind=kind,
                reason=reason,
                item_douban_id=item_douban_id,
                item_title=item_title,
            )
        else:
            task_id = 0
            try:
                data = json.loads(task)
                task_id = data.get("id", 0)
            except (json.JSONDecodeError, TypeError):
                pass
            return await self.write_batch_failure(
                task_id=task_id,
                worker_id=0,
                task_json=task,
                event_type="failure",
                kind=kind,
                reason=reason,
                admin_id=admin_id,
            )

    # ═══════════════════════════════════════
    # 重爬
    # ═══════════════════════════════════════

    async def build_retry_task(self, failure_id: int, admin_id: int) -> str:
        """
        从失败记录构造重爬任务 JSON 字符串。

        输入：failure_id, admin_id
        输出：JSON 字符串
        异常：
            NotFoundError        — 记录不存在
            ClaimNotYoursError   — 不是你认领的
            RetriesExceededError — 重试次数已超上限（MAX_RETRY=2）
            ServiceError         — 任务 JSON 解析失败
        """
        row = await self.get_failure(failure_id)  # 不存在则抛 NotFoundError

        if row["claimed_by"] != admin_id:
            raise ClaimNotYoursError("重爬")

        # 检查重试次数上限（兼容旧库 retry_count 列为 NULL → 0）
        retry_count = row.get("retry_count") or 0
        if retry_count >= MAX_RETRY:
            raise RetriesExceededError(failure_id, MAX_RETRY)

        scope = row.get("scope", "batch")
        item_douban_id = row.get("item_douban_id", "")
        item_title = row.get("item_title", "")

        if scope == "item" and item_douban_id:
            task_data = _build_item_retry_task(failure_id, item_douban_id, item_title)
            return json.dumps(task_data, ensure_ascii=False)

        # scope='batch' → 重新投整个 batch 任务
        try:
            task_data = json.loads(row["task_json"])
        except (json.JSONDecodeError, TypeError) as e:
            raise ServiceError(f"任务 JSON 解析失败: {e}", "INVALID_TASK_JSON", 500)

        task_data["parent_failure_id"] = failure_id
        return json.dumps(task_data, ensure_ascii=False)

    # ═══════════════════════════════════════
    # 重试计数
    # ═══════════════════════════════════════

    async def increment_retry_count(self, failure_id: int) -> int:
        """
        递增失败记录的重试计数（retry_count += 1）。

        输入：failure_id
        输出：递增后的 retry_count 值
        副作用：UPDATE task_failures SET retry_count = retry_count + 1
        兼容：列不存在时 db_test 中用 IFNULL 兜底
        """
        raw = self.db.raw_mysql()
        await raw.execute_update(
            "UPDATE task_failures SET retry_count = COALESCE(retry_count, 0) + 1 WHERE id = %s",
            (failure_id,)
        )
        rows = await raw.execute_query(
            "SELECT retry_count FROM task_failures WHERE id = %s", (failure_id,)
        )
        return (rows[0].get("retry_count") or 0) if rows else 0

    # ═══════════════════════════════════════
    # 内部工具
    # ═══════════════════════════════════════

    async def _execute_update(self, sql: str, params: tuple) -> int:
        """执行 UPDATE，返回 affected_rows。"""
        raw = self.db.raw_mysql()
        return await raw.execute_update(sql, params)

    @staticmethod
    def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        """将 MySQL row 序列化为 JSON 友好格式。"""
        return serialize_datetime_fields(
            row, ["created_at", "claimed_at", "resolved_at"]
        )


def _build_item_retry_task(failure_id: int, douban_id: str, title: str) -> Optional[Dict[str, Any]]:
    """
    从 item 级失败记录构造 director_crawl 小任务。

    输入：
        failure_id: 失败记录 ID（用于重爬链路追踪）
        douban_id:  豆瓣电影 ID
        title:      电影名（日志用）
    输出：director_crawl 任务 dict
    """
    from utils.snowflake import generate_id

    task_id = generate_id()
    return {
        "id": task_id,
        "type": "director_crawl",
        "douban_id": douban_id,
        "movie_id": 0,
        "parent_failure_id": failure_id,
        "item_title": title,
    }


# ═══════════════════════════════════════
# 模块级单例（routes/admin + crawler 共用）
# ═══════════════════════════════════════

_failure_service: TaskFailureService = None


def _get_failure_service() -> TaskFailureService:
    if _failure_service is None:
        raise RuntimeError("TaskFailureService 未初始化，请先调用 init_task_failure_service()")
    return _failure_service


def init_task_failure_service(db) -> TaskFailureService:
    global _failure_service
    _failure_service = TaskFailureService(db)
    logger.info("TaskFailureService 已初始化")
    return _failure_service
