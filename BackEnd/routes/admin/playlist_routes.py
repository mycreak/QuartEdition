"""
routes/admin/playlist_routes.py

片单管理 — 创建/编辑/删除/上下架/列表/封面上传。

端点：
    POST   /admin/playlists                 创建片单
    PUT    /admin/playlists/<id>             编辑片单
    DELETE /admin/playlists/<id>             删除片单
    POST   /admin/playlists/<id>/publish     发布
    POST   /admin/playlists/<id>/unpublish   下架
    GET    /admin/playlists                  列表（含筛选）
    POST   /admin/upload/list-cover          上传片单封面

权限：movie:read（列表 / 详情）
     movie:manage（创建 / 编辑 / 删除 / 发布 / 下架 / 上传封面）
"""

import logging
import time
import secrets
from typing import Any, Dict

from quart import Blueprint, request, jsonify
from quart_schema import tag
from utils.auth import require_permission

logger = logging.getLogger(__name__)

playlist_admin_bp = Blueprint("playlist_admin_routes", __name__)


def _get_service():
    from services.playlist_service import get_playlist_service
    return get_playlist_service()


async def _parse_playlist_body() -> Dict[str, Any]:
    """
    输入: request body (JSON)
    输出: 解析后的参数字典（仅包含提交的字段）
    副作用: 读 request body
    """
    body = await request.get_json() if request.is_json else {}
    data: Dict[str, Any] = {}
    for key in ("title", "description", "cover_url"):
        if key in body:
            data[key] = (body[key] or "").strip() if isinstance(body[key], str) else body[key]
    if "movie_ids" in body:
        data["movie_ids"] = body["movie_ids"]
    if "sort_order" in body:
        data["sort_order"] = int(body["sort_order"])
    if "publish_at" in body:
        data["publish_at"] = body["publish_at"] or None
    if "unpublish_at" in body:
        data["unpublish_at"] = body["unpublish_at"] or None
    return data


# ═══════════════════════════════════════════════════════════
# 管理端 CRUD
# ═══════════════════════════════════════════════════════════

@playlist_admin_bp.route("/playlists", methods=["GET"])
@require_permission("movie:read")
@tag(["片单管理"])
async def list_playlists():
    """列表（含筛选）"""
    keyword = request.args.get("keyword", type=str)
    created_by = request.args.get("created_by", type=int)
    created_after = request.args.get("created_after", type=str)
    created_before = request.args.get("created_before", type=str)
    publish_after = request.args.get("publish_after", type=str)
    publish_before = request.args.get("publish_before", type=str)
    is_published = request.args.get("is_published", type=int)

    svc = _get_service()
    items = await svc.list_all(
        keyword=keyword or None,
        created_by=created_by,
        created_after=created_after or None,
        created_before=created_before or None,
        publish_after=publish_after or None,
        publish_before=publish_before or None,
        is_published=is_published,
    )
    return jsonify({"items": items, "total": len(items)})


@playlist_admin_bp.route("/playlists", methods=["POST"])
@require_permission("movie:manage")
@tag(["片单管理"])
async def create_playlist():
    """创建片单"""
    from quart import g

    body = await request.get_json() if request.is_json else {}
    title = (body.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title 不能为空", "code": "INVALID_TITLE"}), 400

    movie_ids = body.get("movie_ids", [])
    if not isinstance(movie_ids, list) or len(movie_ids) == 0:
        return jsonify({"error": "movie_ids 必须为非空数组", "code": "INVALID_MOVIE_IDS"}), 400

    svc = _get_service()
    try:
        result = await svc.create(
            title=title,
            movie_ids=movie_ids,
            description=(body.get("description") or "").strip(),
            cover_url=(body.get("cover_url") or "").strip(),
            sort_order=body.get("sort_order", 0),
            created_by=g.user_id,
            publish_at=body.get("publish_at") or None,
            unpublish_at=body.get("unpublish_at") or None,
        )
        return jsonify({"success": True, "data": result}), 201
    except ValueError as e:
        return jsonify({"error": str(e), "code": "INVALID_INPUT"}), 400


@playlist_admin_bp.route("/playlists/<int:playlist_id>", methods=["PUT"])
@require_permission("movie:manage")
@tag(["片单管理"])
async def update_playlist(playlist_id: int):
    """编辑片单"""
    data = await _parse_playlist_body()
    if "title" in data and not data["title"]:
        return jsonify({"error": "title 不能为空", "code": "INVALID_TITLE"}), 400

    svc = _get_service()
    try:
        result = await svc.update(playlist_id=playlist_id, **data)
        return jsonify({"success": True, "data": result})
    except ValueError as e:
        return jsonify({"error": str(e), "code": str(e)}), 400


@playlist_admin_bp.route("/playlists/<int:playlist_id>", methods=["DELETE"])
@require_permission("movie:manage")
@tag(["片单管理"])
async def delete_playlist(playlist_id: int):
    """删除片单"""
    svc = _get_service()
    try:
        await svc.delete(playlist_id)
        return jsonify({"success": True, "message": "已删除"})
    except ValueError as e:
        return jsonify({"error": str(e), "code": "NOT_FOUND"}), 404


@playlist_admin_bp.route("/playlists/<int:playlist_id>/publish", methods=["POST"])
@require_permission("movie:manage")
@tag(["片单管理"])
async def publish_playlist(playlist_id: int):
    """发布片单"""
    svc = _get_service()
    try:
        result = await svc.publish(playlist_id)
        return jsonify({"success": True, "data": result})
    except ValueError as e:
        return jsonify({"error": str(e), "code": "NOT_FOUND"}), 404


@playlist_admin_bp.route("/playlists/<int:playlist_id>/unpublish", methods=["POST"])
@require_permission("movie:manage")
@tag(["片单管理"])
async def unpublish_playlist(playlist_id: int):
    """下架片单"""
    svc = _get_service()
    try:
        result = await svc.unpublish(playlist_id)
        return jsonify({"success": True, "data": result})
    except ValueError as e:
        return jsonify({"error": str(e), "code": "NOT_FOUND"}), 404


@playlist_admin_bp.route("/upload/list-cover", methods=["POST"])
@require_permission("movie:manage")
@tag(["片单管理"])
async def upload_list_cover():
    """
    上传片单封面到 TOS。

    请求：multipart/form-data，字段 file=图片文件
    校验：
        - 文件大小 ≤ 5MB
        - 文件格式仅限 png / jpg / webp
    存储：TOS Key = list-covers/cover_{timestamp}_{6位随机}.webp
    返回：{ success, data: { cover_url } }
    """
    from config.settings import settings
    from utils.tos_client import get_tos_client

    files = await request.files
    uploaded = files.get("file")
    if uploaded is None:
        return jsonify({"error": "请提供封面文件（字段名: file）"}), 400

    file_bytes = uploaded.read()

    max_size = settings.POSTER_MAX_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_size:
        return jsonify({
            "error": f"文件大小超过限制（最大{settings.POSTER_MAX_SIZE_MB}MB）"
        }), 400

    content_type = uploaded.content_type or ""
    allowed = [t.strip() for t in settings.AVATAR_ALLOWED_TYPES.split(",")]
    if content_type not in allowed:
        return jsonify({
            "error": f"不支持的文件格式（仅支持{settings.AVATAR_ALLOWED_TYPES}）"
        }), 400

    tos = get_tos_client()
    if tos is None or not tos.enabled:
        return jsonify({"error": "上传失败，请稍后重试"}), 500

    rand_suffix = secrets.token_hex(3)
    dest_key = f"list-covers/cover_{int(time.time())}_{rand_suffix}.webp"
    public_url = await tos.upload(dest_key, file_bytes, content_type="image/webp")
    if not public_url:
        return jsonify({"error": "上传失败，请稍后重试"}), 500

    logger.info(f"片单封面上传成功: key={dest_key} url={public_url}")

    return jsonify({
        "success": True,
        "data": {
            "cover_url": public_url,
        },
    })
