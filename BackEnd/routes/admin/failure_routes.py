"""
routes/admin/failure_routes.py

失败任务认领管理。

端点：
    GET  /admin/failures              — 失败任务列表
    GET  /admin/failures/<id>         — 单条详情
    POST /admin/failures/<id>/claim   — 认领（原子，先到先得）
    POST /admin/failures/<id>/release — 放弃认领
    POST /admin/failures/<id>/resolve — 标记已解决
    POST /admin/failures/<id>/retry   — 重爬（构造任务 → Push Redis）
"""

import logging

from quart import Blueprint, request, jsonify, g
from quart_schema import tag
from utils.auth import require_permission
from utils.errors import ServiceError, RetriesExceededError

logger = logging.getLogger(__name__)

failure_bp = Blueprint("failure_routes", __name__)


def _get_failure_service():
    from services.task_failure_service import _get_failure_service as getter
    return getter()


def _as_error(e: ServiceError):
    return jsonify({"error": e.message, "code": e.code}), e.status_code


@failure_bp.route("/failures", methods=["GET"])
@require_permission("crawler:failure:manage")
@tag(["失败任务管理"])
async def list_failures():
    status = request.args.get("status")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    svc = _get_failure_service()
    rows, total = await svc.list_task_failures(status=status, page=page, page_size=page_size)
    return jsonify({"items": rows, "total": total, "page": page, "page_size": page_size})


@failure_bp.route("/failures/<int:failure_id>", methods=["GET"])
@require_permission("crawler:failure:manage")
@tag(["失败任务管理"])
async def get_failure(failure_id: int):
    svc = _get_failure_service()
    try:
        row = await svc.get_failure(failure_id)
        return jsonify(row)
    except ServiceError as e:
        return _as_error(e)


@failure_bp.route("/failures/<int:failure_id>/claim", methods=["POST"])
@require_permission("crawler:failure:manage")
@tag(["失败任务管理"])
async def claim_failure(failure_id: int):
    svc = _get_failure_service()
    try:
        await svc.claim_failure(failure_id, g.user_id)
        return jsonify({"success": True, "message": "认领成功"})
    except ServiceError as e:
        return _as_error(e)


@failure_bp.route("/failures/<int:failure_id>/release", methods=["POST"])
@require_permission("crawler:failure:manage")
@tag(["失败任务管理"])
async def release_failure(failure_id: int):
    svc = _get_failure_service()
    try:
        await svc.release_failure(failure_id, g.user_id)
        return jsonify({"success": True, "message": "已放弃认领"})
    except ServiceError as e:
        return _as_error(e)


@failure_bp.route("/failures/<int:failure_id>/resolve", methods=["POST"])
@require_permission("crawler:failure:manage")
@tag(["失败任务管理"])
async def resolve_failure(failure_id: int):
    svc = _get_failure_service()
    try:
        await svc.resolve_failure(failure_id, g.user_id)
        return jsonify({"success": True, "message": "已标记为已解决"})
    except ServiceError as e:
        return _as_error(e)


@failure_bp.route("/failures/<int:failure_id>/retry", methods=["POST"])
@require_permission("crawler:failure:manage")
@tag(["失败任务管理"])
async def retry_failure(failure_id: int):
    svc = _get_failure_service()
    try:
        task_json = await svc.build_retry_task(failure_id, g.user_id)
    except RetriesExceededError as e:
        return jsonify({"error": e.message, "code": e.code}), e.status_code
    except ServiceError as e:
        return _as_error(e)

    try:
        from quart import current_app
        from config.puller_config import puller_config
        app = current_app
        execute_at = await app.services.db.add_delayed_task_with_limit(
            task_json=task_json,
            cooldown_seconds=puller_config.task_cooldown_seconds,
        )

        # 重爬提交成功后递增重试计数
        from services.task_failure_service import MAX_RETRY
        new_count = await svc.increment_retry_count(failure_id)
        remaining = MAX_RETRY - new_count

        logger.info(
            f"重爬任务已投回队列: failure_id={failure_id} user_id={g.user_id} "
            f"execute_at={execute_at:.1f} retry_count={new_count}/{MAX_RETRY} "
            f"(cooldown={puller_config.task_cooldown_seconds}s)"
        )
        return jsonify({
            "success": True,
            "message": "重爬任务已投回队列",
            "execute_at": execute_at,
            "retry_count": new_count,
            "remaining_retries": max(remaining, 0),
        })
    except Exception as e:
        logger.exception(f"重爬任务投递失败: {e}")
        return jsonify({"error": f"投递失败: {e}"}), 500
