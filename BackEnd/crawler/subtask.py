"""
crawler/subtask.py

子任务注入器 — 统一封装子任务的构建、入队、history 写入。

设计（v1 — 三步注入）：
    1. 构建完整任务 JSON（若未传入 task_json 则由 task_type + task_data 合并）
    2. ZADD Redis ZSET（delay_queue，带限速 cooldown）
    3. INSERT task_history（status=submitted，parent_task_id 链接父任务）

    history 写入失败不影响主流程（已入 ZSET 的任务仍然会被 Puller 拉取执行，
    只是管理端暂时看不到历史记录；Monitor 执行完成后会 update_status 到 done）。

两种调用模式：
    ── 模式A：构建式（子任务自动生成，crawler 内部用）────────────────
    inject_subtask(db, task_type="director_crawl",
                   task_data={"douban_id": "1295644", "movie_id": 123},
                   admin_id=2906, parent_task_id=xxx)
    → 自动 generate_id() + 合并 task_data

    ── 模式B：透传式（task_json 已由调用方预构建，task_routes 用）─────
    inject_subtask(db, task_type="movie_crawl",
                   task_data={"type_num": 11, "interval_id": "90:80"},
                   task_id=pre_generated_id, admin_id=2906,
                   task_json=json.dumps({...}))
    → 使用传入的 task_id + task_json，history 写入 task_data
"""

import json as _json
import logging
import time
from typing import Any, Dict, Optional

from config.puller_config import puller_config
from utils.snowflake import generate_id

logger = logging.getLogger(__name__)


async def inject_subtask(
    db,
    task_type: str,
    task_data: Dict[str, Any],
    admin_id: int = 0,
    parent_task_id: int = 0,
    task_id: Optional[int] = None,
    task_json: Optional[str] = None,
) -> float:
    """
    统一注入任务到 Redis 延迟队列 + task_history。

    输入：
        db:              DatabaseLayerV2 实例
        task_type:       任务类型字符串
        task_data:       任务特有字段 dict（模式A合并到 JSON / 模式B只写 history）
        admin_id:        归属管理员 ID，0=系统自动
        parent_task_id:  父任务 ID，0=无父任务
        task_id:         可选，传入则不再 generate_id()
        task_json:       可选，传入则跳过 JSON 构建，直接 ZADD
    输出：
        execute_at — ZADD 写入的 score（任务计划执行时间戳）
    副作用：
        ZADD Redis crawler:delay_queue
        INSERT task_history (status=submitted)
    """
    sub_id = task_id or generate_id()
    now = int(time.time())

    if task_json is not None:
        task_json_value = task_json
    else:
        task_dict = {
            "id": sub_id,
            "type": task_type,
            "admin_id": admin_id,
            "parent_task_id": parent_task_id,
            "created_at": now,
            **task_data,
        }
        task_json_value = _json.dumps(task_dict, ensure_ascii=False)

    execute_at = await db.add_delayed_task_with_limit(
        task_json=task_json_value,
        cooldown_seconds=puller_config.task_cooldown_seconds,
    )

    try:
        from services.task_history_service import _get_history_service
        await _get_history_service().create(
            task_id=sub_id,
            admin_id=admin_id,
            task_type=task_type,
            task_params=task_data,
            status="submitted",
            parent_task_id=parent_task_id,
        )
    except Exception:
        logger.exception(
            "[任务注入] history 写入失败（不影响主流程）: type=%s id=%s", task_type, sub_id,
        )

    logger.info(
        "[任务注入] type=%s task_id=%s admin_id=%s parent=%s execute_at=%.1f",
        task_type, sub_id, admin_id, parent_task_id or '无', execute_at,
    )
    return execute_at
