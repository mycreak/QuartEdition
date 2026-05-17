"""
routes/user/review_routes.py

评论浏览（需登录，仅上架）。

端点：
    GET /user/reviews   长评列表
    GET /user/comments  短评列表
"""

import logging

from quart import Blueprint, request, jsonify
from quart_schema import tag
from utils.auth import require_login
from utils.service_access import get_review_service

logger = logging.getLogger(__name__)

review_bp = Blueprint("user_review_routes", __name__)


def _get_review_service():
    """⚠️ 已废弃，请使用 utils.service_access.get_review_service()。"""
    return get_review_service()


@review_bp.route("/reviews", methods=["GET"])
@require_login
@tag(["评论浏览"])
async def list_reviews():
    movie_id = request.args.get("movie_id", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)

    svc = _get_review_service()
    items, total = await svc.list_reviews(
        movie_ids=[movie_id] if movie_id else None,
        published_only=True,
        page=page,
        page_size=page_size,
    )
    return jsonify({"items": items, "page": page, "page_size": page_size, "total": total})


@review_bp.route("/comments", methods=["GET"])
@require_login
@tag(["评论浏览"])
async def list_comments():
    movie_id = request.args.get("movie_id", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)

    svc = _get_review_service()
    items, total = await svc.list_comments(
        movie_ids=[movie_id] if movie_id else None,
        published_only=True,
        page=page,
        page_size=page_size,
    )
    return jsonify({"items": items, "page": page, "page_size": page_size, "total": total})
