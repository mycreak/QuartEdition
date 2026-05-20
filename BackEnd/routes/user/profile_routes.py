"""
routes/user/profile_routes.py

用户个人中心 — 头像上传 / 标签画像。

端点：
    POST   /user/upload/avatar  — 上传用户头像到 TOS
    GET    /user/profile/tags    — 查询用户标签画像
    GET    /user/profile/tags/<dimension> — 按维度过滤画像

权限要求：登录即可访问，每个用户只能操作自己的数据。
"""

import logging

from quart import Blueprint, request, jsonify
from quart_schema import tag
from utils.auth import require_login

logger = logging.getLogger(__name__)

profile_bp = Blueprint("profile_routes", __name__)


def _get_auth_service():
    from services.auth_service import _get_auth_service as getter
    return getter()


@profile_bp.route("/upload/avatar", methods=["POST"])
@require_login
@tag(["用户个人中心"])
async def upload_avatar():
    """
    上传用户头像到 TOS 并返回公开访问 URL。

    请求：multipart/form-data，字段 file=图片文件
    校验：
        - 文件大小 ≤ 2MB
        - 文件格式仅限 png / jpg / webp
    存储：TOS Key = user-avatar/avatar_{user_uuid}.webp（覆盖旧头像）
    返回：{ success, message, data: { avatar_url } }
    """
    from quart import g
    from config.settings import settings
    from utils.tos_client import get_tos_client

    user_id = g.user_id
    svc = _get_auth_service()

    try:
        user = await svc.get_user(user_id)
    except Exception as e:
        return jsonify({"error": f"用户不存在: {e}"}), 404

    files = await request.files
    uploaded = files.get("file")
    if uploaded is None:
        return jsonify({"error": "请提供头像文件（字段名: file）"}), 400

    file_bytes = uploaded.read()

    max_size = settings.AVATAR_MAX_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_size:
        return jsonify({
            "error": f"文件大小超过限制（最大{settings.AVATAR_MAX_SIZE_MB}MB）"
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

    dest_key = f"user-avatar/avatar_{user.uuid}.webp"
    public_url = await tos.upload(dest_key, file_bytes, content_type="image/webp")
    if not public_url:
        return jsonify({"error": "上传失败，请稍后重试"}), 500

    from models.user import UserUpdate
    await svc.update_user(user_id, UserUpdate(avatar_url=public_url))

    logger.info(f"头像上传成功: user_id={user_id} uuid={user.uuid} url={public_url}")

    return jsonify({
        "success": True,
        "message": "上传成功",
        "data": {
            "avatar_url": public_url,
        },
    })


# ═══════════════════════════════════════════════════════════
# 标签画像
# ═══════════════════════════════════════════════════════════

@profile_bp.route("/profile/tags", methods=["GET"])
@require_login
@tag(["用户个人中心"])
async def get_user_tags():
    from quart import g
    from services.user_action_service import get_user_action_service

    user_id = g.user_id
    decayed = request.args.get("decayed", "false").lower() == "true"
    svc = get_user_action_service()
    result = await svc.get_user_tag_profile(user_id, decayed=decayed)
    return jsonify(result.model_dump()), 200


@profile_bp.route("/profile/tags/<dimension>", methods=["GET"])
@require_login
@tag(["用户个人中心"])
async def get_user_tags_by_dimension(dimension: str):
    from quart import g
    from services.user_action_service import get_user_action_service

    user_id = g.user_id
    decayed = request.args.get("decayed", "false").lower() == "true"
    svc = get_user_action_service()
    result = await svc.get_user_tag_profile(user_id, dimension=dimension, decayed=decayed)
    return jsonify(result.model_dump()), 200


# ═══════════════════════════════════════════════════════════
# 个人中心 — 我的电影列表（按行为类型）
# ═══════════════════════════════════════════════════════════

@profile_bp.route("/profile/movies", methods=["GET"])
@require_login
@tag(["用户个人中心"])
async def get_my_movies():
    """
    查询当前用户标记过的电影列表（按行为类型过滤）。

    参数:
        type: want_watch | watching | watched | favorite (必填)
        page: 默认 1
        page_size: 默认 20, 最大 50
    """
    from quart import g

    action = request.args.get("type", "").strip()
    if action not in ("want_watch", "watching", "watched", "favorite"):
        return jsonify({"error": "type 参数必须为 want_watch/watching/watched/favorite", "code": "INVALID_TYPE"}), 400

    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page = max(1, page)
    page_size = max(1, min(page_size, 50))

    user_id = g.user_id
    from quart import current_app
    raw = current_app.services.db.raw_mysql()

    offset = (page - 1) * page_size
    total_rows = await raw.execute_query(
        f"SELECT COUNT(1) AS cnt FROM user_movie_status WHERE user_id=%s AND {action}=1",
        (user_id,),
    )
    total = total_rows[0]["cnt"] if total_rows else 0

    rows = await raw.execute_query(
        f"""SELECT m.id AS movie_id, m.title, m.poster_url, m.release_year, m.douban_id,
                   mr.average AS rating, rs.full_summary AS ai_summary
            FROM user_movie_status ums
            JOIN movies m ON ums.movie_id = m.id
            LEFT JOIN movie_ratings mr ON m.id = mr.movie_id
            LEFT JOIN review_summary rs ON m.id = rs.movie_id
            WHERE ums.user_id=%s AND ums.{action}=1
            ORDER BY ums.updated_at DESC
            LIMIT %s OFFSET %s""",
        (user_id, page_size, offset),
    )

    items = [
        {
            "movie_id": r["movie_id"],
            "title": r["title"],
            "poster_url": r["poster_url"],
            "release_year": r["release_year"],
            "douban_id": r["douban_id"],
            "rating": float(r["rating"]) if r.get("rating") is not None else None,
            "ai_summary": r.get("ai_summary"),
        }
        for r in rows
    ]

    return jsonify({"items": items, "total": total, "page": page, "page_size": page_size})


# ═══════════════════════════════════════════════════════════
# 个人中心 — 我的评论列表
# ═══════════════════════════════════════════════════════════

@profile_bp.route("/profile/comments", methods=["GET"])
@require_login
@tag(["用户个人中心"])
async def get_my_comments():
    """
    查询当前用户发表的评论列表。

    参数:
        page: 默认 1
        page_size: 默认 20, 最大 50
    """
    from quart import g, current_app
    from services.review_service import _get_review_service

    user_id = g.user_id
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    page = max(1, page)
    page_size = max(1, min(page_size, 50))

    review_svc = _get_review_service()
    items, total = await review_svc.get_comments_by_user_id(user_id, page=page, page_size=page_size)

    # 批量补 movie title
    movie_ids = list(set(it["movie_id"] for it in items if it.get("movie_id")))
    title_map: dict = {}
    if movie_ids:
        from services.movie_service import MovieService
        raw = current_app.services.db.raw_mysql()
        placeholders = ",".join(["%s"] * len(movie_ids))
        rows = await raw.execute_query(
            f"SELECT id, title FROM movies WHERE id IN ({placeholders})",
            tuple(movie_ids),
        )
        title_map = {r["id"]: r["title"] for r in rows}

    result = [
        {
            "movie_id": it.get("movie_id"),
            "title": title_map.get(it.get("movie_id")),
            "text": it.get("text", ""),
            "rating": float(it["rating"]) if it.get("rating") else None,
            "date": it.get("date"),
        }
        for it in items
    ]

    return jsonify({"items": result, "total": total, "page": page, "page_size": page_size})
