"""
routes/admin/review_routes.py

评论管理（MongoDB）。

端点：
    GET    /admin/reviews                     长评列表（可选 movie_id/rating 过滤）
    GET    /admin/comments                    短评列表（可选 movie_id/rating 过滤）
    GET    /admin/review-movies               有评论的电影下拉列表
    POST   /admin/reviews/<id>/publish        上架长评  [comment:manage]
    POST   /admin/reviews/<id>/unpublish      下架长评  [comment:manage]
    POST   /admin/comments/<id>/publish       上架短评  [comment:manage]
    POST   /admin/comments/<id>/unpublish     下架短评  [comment:manage]
"""

import logging

from quart import Blueprint, request, jsonify, g
from quart_schema import tag
from utils.auth import require_permission
from utils.errors import ServiceError
from utils.service_access import get_review_service

logger = logging.getLogger(__name__)

review_bp = Blueprint("review_routes", __name__)


def _get_review_service():
    """⚠️ 已废弃，请使用 utils.service_access.get_review_service()。"""
    return get_review_service()


def _as_error(e: ServiceError):
    return jsonify({"error": e.message, "code": e.code}), e.status_code


@review_bp.route("/reviews", methods=["GET"])
@require_permission("comment:read")
@tag(["评论管理"])
async def list_reviews():
    movie_id = request.args.get("movie_id", type=int)
    published = request.args.get("published", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)

    svc = _get_review_service()
    items, total = await svc.list_reviews(
        movie_id=movie_id,
        published_only=bool(published) if published is not None else False,
        page=page,
        page_size=page_size,
    )
    return jsonify({"items": items, "page": page, "page_size": page_size, "total": total})


@review_bp.route("/comments", methods=["GET"])
@require_permission("comment:read")
@tag(["评论管理"])
async def list_comments():
    movie_id = request.args.get("movie_id", type=int)
    rating = request.args.get("rating", type=float)
    published = request.args.get("published", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)

    svc = _get_review_service()
    items, total = await svc.list_comments(
        movie_id=movie_id,
        rating=rating,
        published_only=bool(published) if published is not None else False,
        page=page,
        page_size=page_size,
    )
    return jsonify({"items": items, "page": page, "page_size": page_size, "total": total})


@review_bp.route("/review-movies", methods=["GET"])
@require_permission("comment:read")
@tag(["评论管理"])
async def list_review_movies():
    """
    获取有评论的电影下拉列表（供评论管理页按电影筛选使用）。

    查询逻辑：
        ① 从 MongoDB reviews + comments 两集合分别取 distinct movie_id
        ② 合并去重 → 批量查 MySQL movies 表获取 title
        ③ 返回 [{movie_id, title}, ...] 按 title 排序

    参数：
        keyword: 可选，按电影名模糊搜索（匹配 MySQL movies.title）
    """
    from quart import current_app
    from services.review_service import _get_review_service

    keyword = request.args.get("keyword", "").strip()

    svc = _get_review_service()
    movie_ids = await svc.get_distinct_movie_ids()

    if not movie_ids:
        return jsonify({"items": [], "total": 0})

    # 批量查 MySQL 获取电影名
    db = current_app.services.db
    placeholders = ",".join(["%s"] * len(movie_ids))

    if keyword:
        sql = (
            f"SELECT id AS movie_id, title FROM movies "
            f"WHERE id IN ({placeholders}) AND title LIKE %s "
            f"ORDER BY title ASC"
        )
        rows = await db.execute_raw(sql, tuple(movie_ids) + (f"%{keyword}%",))
    else:
        sql = (
            f"SELECT id AS movie_id, title FROM movies "
            f"WHERE id IN ({placeholders}) "
            f"ORDER BY title ASC"
        )
        rows = await db.execute_raw(sql, tuple(movie_ids))

    items = [dict(row) for row in rows]
    return jsonify({"items": items, "total": len(items)})


# ═══════════════════════════════════════
# 长评上下架
# ═══════════════════════════════════════

@review_bp.route("/reviews/<review_id>/publish", methods=["POST"])
@require_permission("comment:manage")
@tag(["评论管理"])
async def publish_review(review_id: str):
    svc = _get_review_service()
    try:
        await svc.publish_review(review_id)
        return jsonify({"success": True, "message": "长评已上架"})
    except ServiceError as e:
        return _as_error(e)


@review_bp.route("/reviews/<review_id>/unpublish", methods=["POST"])
@require_permission("comment:manage")
@tag(["评论管理"])
async def unpublish_review(review_id: str):
    svc = _get_review_service()
    try:
        await svc.unpublish_review(review_id)
        return jsonify({"success": True, "message": "长评已下架"})
    except ServiceError as e:
        return _as_error(e)


# ═══════════════════════════════════════
# 短评上下架
# ═══════════════════════════════════════

@review_bp.route("/comments/<comment_id>/publish", methods=["POST"])
@require_permission("comment:manage")
@tag(["评论管理"])
async def publish_comment(comment_id: str):
    svc = _get_review_service()
    try:
        await svc.publish_comment(comment_id)
        movie_id = await svc.get_comment_movie_id(comment_id)
        if movie_id:
            from db.redis import redis_delete
            await redis_delete(f"wordcloud:movie:{movie_id}")
        return jsonify({"success": True, "message": "短评已上架"})
    except ServiceError as e:
        return _as_error(e)


@review_bp.route("/comments/<comment_id>/unpublish", methods=["POST"])
@require_permission("comment:manage")
@tag(["评论管理"])
async def unpublish_comment(comment_id: str):
    svc = _get_review_service()
    try:
        await svc.unpublish_comment(comment_id)
        movie_id = await svc.get_comment_movie_id(comment_id)
        if movie_id:
            from db.redis import redis_delete
            await redis_delete(f"wordcloud:movie:{movie_id}")
        return jsonify({"success": True, "message": "短评已下架"})
    except ServiceError as e:
        return _as_error(e)
