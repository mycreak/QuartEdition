"""
routes/admin/style_tag_routes.py

电影风格标签审核管理。

端点：
    GET  /admin/style-tags/pending              — 待审核标签列表
    POST /admin/style-tags/<id>/confirm-merge   — 管理员确认合并
    POST /admin/style-tags/<id>/reject-merge    — 管理员拒绝合并

权限：comment:manage
"""

import logging

from quart import Blueprint, request, jsonify, g
from quart_schema import tag
from utils.auth import require_permission
from utils.errors import ServiceError

logger = logging.getLogger(__name__)

style_tag_bp = Blueprint("style_tag_routes", __name__)


def _get_service():
    from services.style_tag_service import _get_style_tag_service
    return _get_style_tag_service()


def _as_error(e: ServiceError):
    return jsonify({"error": e.message, "code": e.code}), e.status_code


@style_tag_bp.route("/style-tags/pending", methods=["GET"])
@require_permission("comment:manage")
@tag(["风格标签审核"])
async def list_pending():
    """
    待审核标签列表。

    查询参数：page（默认1）, page_size（默认20）
    返回：items 含 merged_to_tag_name / sample_movie / merged_sample_movie
    """
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    svc = _get_service()
    items, total = await svc.list_pending(page=page, page_size=page_size)
    return jsonify({"items": items, "total": total, "page": page, "page_size": page_size})


@style_tag_bp.route("/style-tags/<int:tag_id>/confirm-merge", methods=["POST"])
@require_permission("comment:manage")
@tag(["风格标签审核"])
async def confirm_merge(tag_id: int):
    """
    管理员确认合并风格标签。

    事务执行三步：迁移 movie_style 关联 → 删除旧关联 → 改 status=3
    """
    admin_id = g.user_id
    svc = _get_service()
    try:
        result = await svc.confirm_merge(tag_id, admin_id)
        return jsonify(result)
    except ServiceError as e:
        return _as_error(e)


@style_tag_bp.route("/style-tags/<int:tag_id>/reject-merge", methods=["POST"])
@require_permission("comment:manage")
@tag(["风格标签审核"])
async def reject_merge(tag_id: int):
    """
    管理员拒绝合并 — 标记为已确认无需合并（status=1，merged_to_tag_id=0）。
    """
    admin_id = g.user_id
    svc = _get_service()
    try:
        result = await svc.reject_merge(tag_id, admin_id)
        return jsonify(result)
    except ServiceError as e:
        return _as_error(e)
