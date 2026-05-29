"""
services/task_failure_service.py

失败任务管理 — 只读查询 + 写入。

职责：
    1. list_task_failures — 分页查询失败任务列表（支持按 status 过滤）
    2. get_failure        — 单条详情
    3. write_batch_failure — 写入批次级失败事件
    4. write_item_failure  — 写入 item 级失败事件

设计原则：
    查询时通过 LEFT JOIN task_history 获取 task_params / admin_id，
    消除 task_failures 表中 task_json / admin_id / event_type 的冗余。

注意：不再提供 claim/release/resolve。
失败任务天然归属提交者（admin_id），管理员通过 WebSocket 收到通知后，
可在爬虫面板的「历史」tab 中按状态过滤查看，自行决定重新提交。

错误处理：
    所有失败路径抛出 ServiceError 子类，路由层统一捕获。

依赖：
    DatabaseLayerV2 — 注入，读写 MySQL task_failures 表
"""

import json
import logging
from typing import Optional, Dict, Any

from db.database_v2 import DatabaseLayerV2
from utils.serializers import serialize_datetime_fields
from utils.errors import (
    ServiceError, NotFoundError,
)

logger = logging.getLogger(__name__)


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

        查询通过 LEFT JOIN task_history 注入 task_params / admin_id / task_type，
        替代已删除的 task_json / admin_id 列。
        """
        where_clause = ""
        params = []
        if status:
            where_clause = "WHERE tf.status = %s"
            params.append(status)

        count_sql = f"SELECT COUNT(*) AS cnt FROM task_failures tf {where_clause}"
        count_rows = await self.db.execute_raw(count_sql, tuple(params))
        total = count_rows[0]["cnt"] if count_rows else 0

        offset = (page - 1) * page_size
        sql = (
            "SELECT tf.*, th.task_params, th.admin_id, th.task_type "
            "FROM task_failures tf "
            "LEFT JOIN task_history th ON th.id = tf.task_id "
            f"{where_clause} "
            f"ORDER BY tf.created_at DESC LIMIT %s OFFSET %s"
        )
        params.extend([page_size, offset])

        rows = await self.db.execute_raw(sql, tuple(params))
        return [self._serialize_row(r) for r in rows], total

    async def get_failure(self, failure_id: int) -> Dict[str, Any]:
        """
        输入：failure_id — 失败记录 ID
        输出：dict，包含 task_params / admin_id / task_type（来自 JOIN）
        异常：NotFoundError — 记录不存在
        """
        rows = await self.db.execute_raw(
            "SELECT tf.*, th.task_params, th.admin_id, th.task_type "
            "FROM task_failures tf "
            "LEFT JOIN task_history th ON th.id = tf.task_id "
            "WHERE tf.id = %s",
            (failure_id,),
        )
        if not rows:
            raise NotFoundError("失败记录", failure_id)
        return self._serialize_row(rows[0])

    # ═══════════════════════════════════════
    # 写入失败事件
    # ═══════════════════════════════════════

    async def write_batch_failure(
        self,
        task_id: int,
        worker_id: int,
        kind: str,
        reason: str,
        parent_failure_id: int = 0,
        failure_layer: str = "crawler",
        snapshot: Optional[dict] = None,
        task_type: str = "",
        douban_id: str = "",
    ) -> int:
        """
        写入批次级失败事件（scope='batch'），同时释放关联的 douban_id 认领。

        输入：
            task_id, worker_id,
            kind, reason,
            parent_failure_id,
            failure_layer: crawler | storage | ai | system（错误来源层）
            snapshot: AI 调用失败时的执行现场快照
            task_type: 任务类型字符串（用于 douban_id 释放判断）
            douban_id: 关联的豆瓣 ID（用于释放认领）
        输出：自增 ID

        副作用：
            1. INSERT task_failures
            2. 如果 task_type ∈ (movie_scrape_task, movie_detail_crawl, director_crawl)
               且 douban_id 非空 → UPDATE douban_ids 释放认领
               （is_scraped=-1, admin_id=NULL, acquired_at=NULL）
               释放失败不影响主流程（写日志即可）
        """
        import json as _json
        snapshot_json = _json.dumps(snapshot, ensure_ascii=False) if snapshot else None
        sql = (
            "INSERT INTO task_failures "
            "(task_id, worker_id, kind, failure_layer, reason, "
            "status, parent_failure_id, scope, snapshot) "
            "VALUES (%s, %s, %s, %s, %s, 'pending', %s, 'batch', %s)"
        )
        raw = self.db.raw_mysql()
        fid = await raw.execute_insert(sql, (
            task_id, worker_id, kind, failure_layer, reason,
            parent_failure_id, snapshot_json,
        ))
        logger.info(f"批次失败已记录: id={fid} kind={kind} layer={failure_layer}")

        await self._release_douban_id_on_failure(task_type, douban_id)

        return fid

    async def _release_douban_id_on_failure(
        self, task_type: str, douban_id: str
    ) -> None:
        """
        任务失败时释放关联的 douban_id 认领。

        输入：
            task_type: 任务类型字符串（来自 task_history 或调用方解析）
            douban_id: 豆瓣电影 ID
        副作用：
            UPDATE douban_ids SET is_scraped=-1, admin_id=NULL, acquired_at=NULL
            WHERE douban_id=%s AND is_scraped=0
            （幂等: is_scraped=0 确保只释放尚未完成的，已完成的不受影响）
        """
        if task_type not in ("movie_scrape_task", "movie_detail_crawl", "director_crawl"):
            return
        if not douban_id:
            return

        try:
            raw = self.db.raw_mysql()
            affected = await raw.execute_update(
                "UPDATE douban_ids "
                "SET is_scraped = -1, admin_id = NULL, acquired_at = NULL "
                "WHERE douban_id = %s AND is_scraped = 0",
                (douban_id,),
            )
            if affected:
                logger.info(
                    f"任务失败，已释放 douban_id 认领: "
                    f"douban_id={douban_id} task_type={task_type}"
                )
        except Exception:
            logger.exception(f"释放 douban_id 认领失败: douban_id={douban_id}")

    async def write_item_failure(
        self,
        task_id: int,
        admin_id: int,
        kind: str,
        reason: str,
        item_douban_id: str,
        item_title: str,
        parent_failure_id: int = 0,
    ) -> int:
        """
        写入单部电影级失败事件（scope='item'）。

        输入：
            task_id, admin_id — 显式传入（不再从 task_json 解析）
            kind, reason,
            item_douban_id: 失败的电影 douban_id
            item_title: 失败的电影名
            parent_failure_id: 关联的父失败记录 ID
        输出：自增 ID
        """
        sql = (
            "INSERT INTO task_failures "
            "(task_id, worker_id, kind, reason, status, parent_failure_id, "
            "scope, item_douban_id, item_title) "
            "VALUES (%s, 0, %s, %s, 'pending', %s, 'item', %s, %s)"
        )
        raw = self.db.raw_mysql()
        fid = await raw.execute_insert(sql, (
            task_id, kind, reason, parent_failure_id,
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
        task_id: int = 0,
        admin_id: int = 0,
        kind: str = "unknown",
        reason: str = "",
        scope: str = "batch",
        item_douban_id: str = "",
        item_title: str = "",
        task_type: str = "",
        douban_id: str = "",
    ) -> int:
        """
        crawler 调用入口 — 内部按 scope 分发到 batch/item 写入。

        输入（全部 keyword-only）：
            task_id:        任务 snowflake ID
            admin_id:       操作管理员 ID
            kind:           错误分类
            reason:         错误详情
            scope:          'batch'（任务级）或 'item'（单部/单篇级）
            item_douban_id: scope='item' 时的标识
            item_title:     scope='item' 时的摘要
            task_type:      scope='batch' 时的任务类型（用于 douban_id 释放）
            douban_id:      scope='batch' 时的豆瓣 ID（用于 douban_id 释放）
        输出：自增 ID
        副作用：INSERT INTO task_failures
        """
        if scope == "item":
            return await self.write_item_failure(
                task_id=task_id,
                admin_id=admin_id,
                kind=kind,
                reason=reason,
                item_douban_id=item_douban_id,
                item_title=item_title,
            )
        else:
            return await self.write_batch_failure(
                task_id=task_id,
                worker_id=0,
                kind=kind,
                reason=reason,
                task_type=task_type,
                douban_id=douban_id,
            )

    # ═══════════════════════════════════════
    # 内部工具
    # ═══════════════════════════════════════

    @staticmethod
    def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 MySQL row 序列化为 JSON 友好格式。

        注意：row 来自 LEFT JOIN task_history，包含:
            - task_failures.* 的所有列
            - th.task_params — JSON 字符串，从 task_history JOIN 注入
            - th.admin_id    — 从 task_history JOIN 注入
            - th.task_type   — 从 task_history JOIN 注入
        """
        result = serialize_datetime_fields(
            row, ["created_at", "claimed_at", "resolved_at"]
        )
        # MySQL JSON 列默认返回 str，统一转 Python dict
        if isinstance(result.get("task_params"), str):
            try:
                result["task_params"] = json.loads(result["task_params"])
            except (json.JSONDecodeError, TypeError):
                pass
        return result


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
