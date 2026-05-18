"""
routes/admin/failure_routes.py

失败任务查询（只读）。

端点：
    GET  /admin/failures              — 失败任务列表
    GET  /admin/failures/<id>         — 单条详情

注意：不再提供 claim/release/resolve 端点。
失败任务天然归属提交者（admin_id），管理员通过 WebSocket 收到通知后，
可在爬虫面板的「历史」tab 中按状态过滤查看，自行决定重新提交或更换策略。
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



