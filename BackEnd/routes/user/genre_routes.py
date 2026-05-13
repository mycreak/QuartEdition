"""
routes/user/genre_routes.py

类型列表与统计（需登录，仅上架）。

端点：
    GET /user/genres        类型列表
    GET /user/genre-stats   类型统计（电影数 + 平均分）
"""

import logging

from quart import Blueprint, jsonify
from quart_schema import tag
from utils.auth import require_login

logger = logging.getLogger(__name__)

genre_bp = Blueprint("user_genre_routes", __name__)


@genre_bp.route("/genres", methods=["GET"])
@require_login
@tag(["分类与统计"])
async def list_genres():
    from quart import current_app
    genres = await current_app.services.movie_service.list_genres(published_only=True)
    return jsonify({"items": [g.model_dump() for g in genres]})


@genre_bp.route("/genre-stats", methods=["GET"])
@require_login
@tag(["分类与统计"])
async def genre_stats():
    from quart import current_app
    stats = await current_app.services.movie_service.get_genre_stats(published_only=True)
    return jsonify({"items": [s.model_dump() for s in stats]})
