"""
routes/admin/review_routes.py

评论管理（MongoDB）。

端点：
    GET    /admin/reviews                     长评列表（支持电影属性+上下架过滤）
    GET    /admin/comments                    短评列表（支持电影属性+上下架过滤）
    GET    /admin/review-movies               有评论的电影下拉列表
    POST   /admin/reviews/<id>/publish        上架长评  [comment:manage]
    POST   /admin/reviews/<id>/unpublish      下架长评  [comment:manage]
    POST   /admin/comments/<id>/publish       上架短评  [comment:manage]
    POST   /admin/comments/<id>/unpublish     下架短评  [comment:manage]

方案A（先筛电影再筛评论）：
    当传了 type_num / region_id / release_year / interval_ids 时，
    先查 MySQL movies 表筛选出 movie_id 列表，再传 $in 给 MongoDB 查评论。
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


async def _resolve_movie_ids_by_filters(
    db,
    movie_id: int | None = None,
    type_num: int | None = None,
    region_id: int | None = None,
    release_year: int | None = None,
    interval_ids: str | None = None,
) -> list[int] | None:
    """
    根据电影属性筛选，从MySQL movies表查出匹配的movie_id列表。

    输入：
        movie_id:      已指定的单部电影ID（交集）
        type_num:      豆瓣类型编号（需匹配movie_genres关联表）
        region_id:     地区ID（需匹配movie_regions关联表）
        release_year:  发行年份
        interval_ids:  评分区间 "100:90,90:80"（对应 10分~9分, 9分~8分...）
    输出：
        匹配的movie_id列表；未传任何电影属性参数时返回None（表示无需过滤）
        空列表表示没有电影匹配（前端应显示空结果）

    副作用：读MySQL
    """
    has_movie_filter = any([
        movie_id is not None,
        type_num is not None,
        region_id is not None,
        release_year is not None,
        bool(interval_ids),
    ])
    if not has_movie_filter:
        return None

    where_clauses: list[str] = []
    params: list = []

    if movie_id is not None:
        where_clauses.append("m.id = %s")
        params.append(movie_id)

    if type_num is not None:
        where_clauses.append(
            "m.id IN (SELECT mg.movie_id FROM movie_genres mg WHERE mg.type_num = %s)"
        )
        params.append(type_num)

    if region_id is not None:
        where_clauses.append(
            "m.id IN (SELECT mr.movie_id FROM movie_regions mr WHERE mr.region_id = %s)"
        )
        params.append(region_id)

    if interval_ids:
        for part in interval_ids.split(","):
            part = part.strip()
            if ":" not in part:
                continue
            high_str, low_str = part.split(":", 1)
            try:
                high = float(high_str) / 10
                low = float(low_str) / 10
                where_clauses.append(
                    "(m.rating_avg >= %s AND m.rating_avg < %s)"
                )
                params.extend([low, high])
            except ValueError:
                logger.debug(f"跳过无效评分区间: {part}")

    if release_year is not None:
        where_clauses.append("m.release_year = %s")
        params.append(release_year)

    where_sql = " AND ".join(where_clauses)
    sql = f"SELECT m.id FROM movies m WHERE {where_sql}"
    rows = await db.execute_raw(sql, tuple(params))
    return [row["id"] for row in rows]


@review_bp.route("/reviews", methods=["GET"])
@require_permission("comment:read")
@tag(["评论管理"])
async def list_reviews():
    movie_id = request.args.get("movie_id", type=int)
    type_num = request.args.get("type_num", type=int)
    region_id = request.args.get("region_id", type=int)
    release_year = request.args.get("release_year", type=int)
    interval_ids = request.args.get("interval_ids")
    published = request.args.get("published", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)

    # ① 按电影属性筛选出movie_id列表
    from quart import current_app
    db = current_app.services.db
    resolved_ids = await _resolve_movie_ids_by_filters(
        db, movie_id=movie_id, type_num=type_num,
        region_id=region_id, release_year=release_year,
        interval_ids=interval_ids,
    )
    if resolved_ids is not None and len(resolved_ids) == 0:
        return jsonify({"items": [], "page": page, "page_size": page_size, "total": 0})

    svc = _get_review_service()
    items, total = await svc.list_reviews(
        movie_ids=resolved_ids,
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
    type_num = request.args.get("type_num", type=int)
    region_id = request.args.get("region_id", type=int)
    release_year = request.args.get("release_year", type=int)
    interval_ids = request.args.get("interval_ids")
    rating = request.args.get("rating", type=float)
    published = request.args.get("published", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)

    # ① 按电影属性筛选出movie_id列表
    from quart import current_app
    db = current_app.services.db
    resolved_ids = await _resolve_movie_ids_by_filters(
        db, movie_id=movie_id, type_num=type_num,
        region_id=region_id, release_year=release_year,
        interval_ids=interval_ids,
    )
    if resolved_ids is not None and len(resolved_ids) == 0:
        return jsonify({"items": [], "page": page, "page_size": page_size, "total": 0})

    svc = _get_review_service()
    items, total = await svc.list_comments(
        movie_ids=resolved_ids,
        rating=rating,
        published_only=bool(published) if published is not None and published != -1 else False,
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
