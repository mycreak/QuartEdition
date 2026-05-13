"""
routes/admin/history_routes.py

任务历史查询接口。

端点：
    GET /admin/task-history         分页历史列表（多维度过滤）
    GET /admin/task-history/<id>    单条详情（含关联失败记录）
"""

from quart import Blueprint, request, jsonify
from quart_schema import tag
from utils.auth import require_permission

history_bp = Blueprint("history_routes", __name__)


@history_bp.route("/task-history", methods=["GET"])
@require_permission("crawler:task:read")
@tag(["任务历史"])
async def list_history():
    """
    分页查询任务历史。

    参数: admin_id, task_type, status, keyword, since, until, page, page_size
    """
    from services.task_history_service import _get_history_service

    admin_id = request.args.get("admin_id", type=int)
    task_type = request.args.get("task_type")
    status = request.args.get("status")
    keyword = request.args.get("keyword")
    since = request.args.get("since")
    until = request.args.get("until")
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)

    svc = _get_history_service()
    result = await svc.list_history(
        admin_id=admin_id,
        task_type=task_type,
        status=status,
        keyword=keyword,
        since=since,
        until=until,
        page=page,
        page_size=page_size,
    )
    return jsonify(result)


@history_bp.route("/task-history/<int:task_id>", methods=["GET"])
@require_permission("crawler:task:read")
@tag(["任务历史"])
async def get_history(task_id: int):
    """
    单条任务历史详情（含关联失败记录）。
    """
    from services.task_history_service import _get_history_service

    svc = _get_history_service()
    result = await svc.get(task_id)
    if result is None:
        return jsonify({"error": "任务不存在", "code": "NOT_FOUND"}), 404
    return jsonify(result)
