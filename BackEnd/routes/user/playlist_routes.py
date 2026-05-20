"""
routes/user/playlist_routes.py

用户端片单浏览 — 轮播列表 + 详情页。

端点：
    GET /user/playlists         已发布片单列表（轮播用）
    GET /user/playlists/<id>    片单详情（含电影信息）

权限：登录即可访问
"""

import logging

from quart import Blueprint, request, jsonify
from quart_schema import tag
from utils.auth import require_login

logger = logging.getLogger(__name__)

playlist_user_bp = Blueprint("playlist_user_routes", __name__)


def _get_service():
    from services.playlist_service import get_playlist_service
    return get_playlist_service()


@playlist_user_bp.route("/playlists", methods=["GET"])
@require_login
@tag(["片单"])
async def list_published():
    """轮播用 — 已发布且在时间窗口内的片单列表"""
    svc = _get_service()
    items = await svc.list_published()
    return jsonify({"items": items, "total": len(items)})


@playlist_user_bp.route("/playlists/<int:playlist_id>", methods=["GET"])
@require_login
@tag(["片单"])
async def detail(playlist_id: int):
    """片单详情 — 含电影摘要列表"""
    svc = _get_service()
    try:
        result = await svc.detail(playlist_id)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e), "code": "NOT_FOUND"}), 404
