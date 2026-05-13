"""
services/task_history_service.py

任务历史管理 — 记录每个爬虫任务的生命周期（提交 → 执行 → 完成/失败）。

输入：DatabaseLayerV2 实例（依赖注入）
副作用：读写 MySQL task_history 表
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from db.database_v2 import DatabaseLayerV2
from utils.serializers import to_iso

logger = logging.getLogger(__name__)

_STATUS_VALUES = ("submitted", "running", "done", "failed")


class TaskHistoryService:
    """
    任务历史业务层。

    输入：DatabaseLayerV2 实例（依赖注入）
    副作用：读写 MySQL task_history 表
    """

    def __init__(self, db: DatabaseLayerV2):
        self.db = db

    async def create(
        self,
        task_id: int,
        admin_id: int,
        task_type: str,
        task_params: dict,
        status: str = "submitted",
    ) -> int:
        """
        创建任务历史记录 — 任务写入 Redis 成功后调用。

        输入：
            task_id:     snowflake 任务 ID
            admin_id:    提交人 user_id
            task_type:   movie_crawl / review_crawl / comment_crawl / director_crawl
            task_params: 完整任务 JSON dict（含 url / type_num / subject_id 等）
            status:      submitted（初始状态）
        输出：task_id（与输入一致）
        副作用：INSERT INTO task_history
        """
        params_json = json.dumps(task_params, ensure_ascii=False)
        sql = (
            "INSERT INTO task_history (id, admin_id, task_type, task_params, status) "
            "VALUES (%s, %s, %s, %s, %s)"
        )
        raw = self.db.raw_mysql()
        await raw.execute_insert(sql, (task_id, admin_id, task_type, params_json, status))
        logger.info(f"task_history 创建: id={task_id} type={task_type} status={status}")
        return task_id

    async def update_status(
        self,
        task_id: int,
        status: str,
        message: Optional[str] = None,
    ) -> bool:
        """
        更新任务状态 — Monitor / Worker 回调。

        输入：
            task_id:  任务 ID
            status:   done / failed
            message:  成功概述 / 失败原因
        输出：True=更新成功, False=记录不存在
        副作用：UPDATE task_history SET status, message, updated_at
        """
        if status not in _STATUS_VALUES:
            raise ValueError(f"status 必须是 {_STATUS_VALUES} 之一，收到: {status}")

        if message is not None:
            sql = (
                "UPDATE task_history SET status = %s, message = %s WHERE id = %s"
            )
            params = (status, message, task_id)
        else:
            sql = "UPDATE task_history SET status = %s WHERE id = %s"
            params = (status, task_id)

        raw = self.db.raw_mysql()
        affected = await raw.execute_update(sql, params)
        if affected:
            logger.info(f"task_history 更新: id={task_id} status={status} msg={message}")
        else:
            logger.debug(f"task_history 更新跳过（记录不存在）: id={task_id}")
        return affected > 0

    async def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        """
        查询单条任务历史（含关联的失败记录）。

        输入：task_id
        输出：dict 或 None
        """
        raw = self.db.raw_mysql()
        sql = (
            "SELECT th.*, "
            "  tf.id as failure_id, tf.reason as failure_reason, "
            "  tf.status as failure_status, tf.retry_count as failure_retry_count "
            "FROM task_history th "
            "LEFT JOIN task_failures tf ON tf.task_id = th.id "
            "  AND tf.scope = 'batch' AND tf.event_type = 'failure' "
            "WHERE th.id = %s "
            "ORDER BY tf.id DESC LIMIT 1"
        )
        rows = await raw.execute_query(sql, (task_id,))
        if not rows:
            return None

        row = dict(rows[0])
        related_failure = None
        if row.get("failure_id"):
            related_failure = {
                "failure_id": row.pop("failure_id"),
                "reason": row.pop("failure_reason", ""),
                "status": row.pop("failure_status", "pending"),
                "retry_count": row.pop("failure_retry_count", 0),
            }
        else:
            for k in ("failure_id", "failure_reason", "failure_status", "failure_retry_count"):
                row.pop(k, None)

        result = dict(row)
        result["related_failure"] = related_failure
        if isinstance(result.get("created_at"), datetime):
            result["created_at"] = to_iso(result["created_at"])
        if isinstance(result.get("updated_at"), datetime):
            result["updated_at"] = to_iso(result["updated_at"])
        return result

    async def list_history(
        self,
        admin_id: Optional[int] = None,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        分页查询任务历史。

        输入：多维度过滤 + 分页
        输出：{items, total, page, page_size}
        """
        where = []
        params = []

        if admin_id:
            where.append("th.admin_id = %s")
            params.append(admin_id)
        if task_type:
            where.append("th.task_type = %s")
            params.append(task_type)
        if status:
            where.append("th.status = %s")
            params.append(status)
        if keyword:
            where.append("th.task_params LIKE %s")
            params.append(f"%{keyword}%")
        if since:
            where.append("th.created_at >= %s")
            params.append(since)
        if until:
            where.append("th.created_at <= %s")
            params.append(until)

        where_sql = ""
        if where:
            where_sql = "WHERE " + " AND ".join(where)

        raw = self.db.raw_mysql()

        count_sql = f"SELECT COUNT(*) as cnt FROM task_history th {where_sql}"
        rows = await raw.execute_query(count_sql, tuple(params))
        total = rows[0]["cnt"] if rows else 0

        offset = (page - 1) * page_size
        list_sql = (
            f"SELECT th.* FROM task_history th "
            f"{where_sql} "
            f"ORDER BY th.created_at DESC "
            f"LIMIT %s OFFSET %s"
        )
        params.extend([page_size, offset])
        rows = await raw.execute_query(list_sql, tuple(params))

        items = []
        for row in rows:
            item = dict(row)
            if isinstance(item.get("created_at"), datetime):
                item["created_at"] = to_iso(item["created_at"])
            if isinstance(item.get("updated_at"), datetime):
                item["updated_at"] = to_iso(item["updated_at"])
            if isinstance(item.get("task_params"), str):
                try:
                    item["task_params"] = json.loads(item["task_params"])
                except (json.JSONDecodeError, TypeError):
                    pass
            items.append(item)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }


_history_service: Optional[TaskHistoryService] = None


def _get_history_service() -> TaskHistoryService:
    if _history_service is None:
        raise RuntimeError(
            "TaskHistoryService 未初始化，请先调用 init_task_history_service()"
        )
    return _history_service


def init_task_history_service(db: DatabaseLayerV2) -> TaskHistoryService:
    global _history_service
    _history_service = TaskHistoryService(db)
    logger.info("TaskHistoryService 已初始化")
    return _history_service
