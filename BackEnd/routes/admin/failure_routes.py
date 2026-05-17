"""
routes/admin/failure_routes.py

失败任务认领管理。

端点：
    GET  /admin/failures              — 失败任务列表
    GET  /admin/failures/<id>         — 单条详情
    POST /admin/failures/<id>/claim   — 认领（原子，先到先得）
    POST /admin/failures/<id>/release — 放弃认领
    POST /admin/failures/<id>/resolve — 标记已解决

注意：不再提供 /retry 端点 — 失败后由管理员人工排查后手动重新提交任务。
"""

import logging

from quart import Blueprint, request, jsonify, g
from quart_schema import tag
from utils.auth import require_permission
from utils.errors import ServiceError

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



