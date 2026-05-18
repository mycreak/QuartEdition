"""
services/task_failure_service.py

失败任务管理 — 只读查询 + 写入。

职责：
    1. list_task_failures — 分页查询失败任务列表（支持按 status 过滤）
    2. get_failure        — 单条详情
    3. write_batch_failure — 写入批次级失败事件
    4. write_item_failure  — 写入 item 级失败事件

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
from typing import Optional, List, Dict, Any

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
        failure_layer: str = "crawler",
        snapshot: Optional[dict] = None,
    ) -> int:
        """
        写入批次级失败事件（scope='batch'），同时释放关联的 douban_id 认领。

        输入：
            task_id, worker_id, task_json, event_type, kind, reason,
            admin_id, parent_failure_id,
            failure_layer: crawler | storage | ai | system（错误来源层）
        输出：自增 ID

        副作用：
            1. INSERT task_failures
            2. 如果任务类型是 movie_scrape_task/movie_detail_crawl/director_crawl
               且 task_json 中包含 douban_id → UPDATE douban_ids 释放认领
               （is_scraped=-1, admin_id=NULL, acquired_at=NULL）
               释放失败不影响主流程（写日志即可）
        """
        import json as _json
        snapshot_json = _json.dumps(snapshot, ensure_ascii=False) if snapshot else None
        sql = (
            "INSERT INTO task_failures "
            "(task_id, worker_id, task_json, event_type, kind, failure_layer, reason, "
            "admin_id, status, parent_failure_id, scope, snapshot) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, 'batch', %s)"
        )
        raw = self.db.raw_mysql()
        fid = await raw.execute_insert(sql, (
            task_id, worker_id, task_json, event_type, kind, failure_layer, reason,
            admin_id, parent_failure_id, snapshot_json,
        ))
        logger.info(f"批次失败已记录: id={fid} kind={kind} layer={failure_layer}")

        # 释放 douban_id 认领（系统自动清理，失败不影响主流程）
        await self._release_douban_id_on_failure(task_json)

        return fid

    async def _release_douban_id_on_failure(self, task_json: str) -> None:
        """
        任务失败时释放关联的 douban_id 认领。

        解析 task_json → 提取 type + douban_id →
        如果 type 是涉及单部电影详情爬取的任务：
            UPDATE douban_ids SET is_scraped=-1, admin_id=NULL, acquired_at=NULL
            WHERE douban_id=%s AND is_scraped=0
            （幂等: is_scraped=0 确保只释放尚未完成的，已完成的不受影响）

        这是系统自动化操作，不涉及权限校验。
        """
        try:
            data = json.loads(task_json)
        except (json.JSONDecodeError, TypeError):
            return

        task_type = data.get("type", "")
        douban_id = data.get("douban_id", "")

        # 只处理直接操作 douban_id 的任务类型
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
                    f"douban_id={douban_id} kind=unknown task_type={task_type}"
                )
        except Exception:
            logger.exception(f"释放 douban_id 认领失败: douban_id={douban_id}")

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
