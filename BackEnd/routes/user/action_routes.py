"""
routes/user/action_routes.py

用户行为评分端点 — 想看/在看/看过/收藏/评论 + 状态查询。

端点:
    POST   /user/movies/<int:movie_id>/want-watch     标记想看
    DELETE /user/movies/<int:movie_id>/want-watch     取消想看
    POST   /user/movies/<int:movie_id>/watching        标记在看
    DELETE /user/movies/<int:movie_id>/watching        取消在看
    POST   /user/movies/<int:movie_id>/watched         标记看过
    DELETE /user/movies/<int:movie_id>/watched         取消看过
    POST   /user/movies/<int:movie_id>/favorite        收藏电影
    DELETE /user/movies/<int:movie_id>/favorite        取消收藏
    POST   /user/movies/<int:movie_id>/review          提交评论
    DELETE /user/movies/<int:movie_id>/review          删除评论
    GET    /user/movies/<int:movie_id>/status          查询标记状态

权限: @require_login，user_id 从 JWT 解析，只能操作自己的数据。
"""

import logging
from typing import Optional

from quart import Blueprint, request, jsonify, g
from quart_schema import tag
from utils.auth import require_login

logger = logging.getLogger(__name__)

action_bp = Blueprint("action_routes", __name__)


def _get_service():
    from services.user_action_service import get_user_action_service
    return get_user_action_service()


async def _handle_action(action: str):
    svc = _get_service()
    user_id = g.user_id
    movie_id = request.view_args["movie_id"]

    try:
        result = await svc.execute_action(user_id, movie_id, action)
    except ValueError as e:
        code = "DUPLICATE_ACTION" if "已标记" in str(e) or "已评论" in str(e) else "INVALID_ACTION"
        return jsonify({"error": str(e), "code": code}), 400

    return jsonify(result.model_dump()), 200


async def _handle_rollback(action: str):
    svc = _get_service()
    user_id = g.user_id
    movie_id = request.view_args["movie_id"]

    try:
        result = await svc.rollback_action(user_id, movie_id, action)
    except ValueError as e:
        return jsonify({"error": str(e), "code": "NOT_FOUND"}), 400

    return jsonify(result.model_dump()), 200


# ═══════════════════════════════════════════════════════════
# 操作端点 — POST = 标记，DELETE = 取消
# ═══════════════════════════════════════════════════════════

@action_bp.route("/movies/<int:movie_id>/want_watch", methods=["POST"])
@require_login
@tag(["用户行为"])
async def mark_want_watch(movie_id: int):
    return await _handle_action("want_watch")


@action_bp.route("/movies/<int:movie_id>/want_watch", methods=["DELETE"])
@require_login
@tag(["用户行为"])
async def unmark_want_watch(movie_id: int):
    return await _handle_rollback("want_watch")


@action_bp.route("/movies/<int:movie_id>/watching", methods=["POST"])
@require_login
@tag(["用户行为"])
async def mark_watching(movie_id: int):
    return await _handle_action("watching")


@action_bp.route("/movies/<int:movie_id>/watching", methods=["DELETE"])
@require_login
@tag(["用户行为"])
async def unmark_watching(movie_id: int):
    return await _handle_rollback("watching")


@action_bp.route("/movies/<int:movie_id>/watched", methods=["POST"])
@require_login
@tag(["用户行为"])
async def mark_watched(movie_id: int):
    return await _handle_action("watched")


@action_bp.route("/movies/<int:movie_id>/watched", methods=["DELETE"])
@require_login
@tag(["用户行为"])
async def unmark_watched(movie_id: int):
    return await _handle_rollback("watched")


@action_bp.route("/movies/<int:movie_id>/favorite", methods=["POST"])
@require_login
@tag(["用户行为"])
async def mark_favorite(movie_id: int):
    return await _handle_action("favorite")


@action_bp.route("/movies/<int:movie_id>/favorite", methods=["DELETE"])
@require_login
@tag(["用户行为"])
async def unmark_favorite(movie_id: int):
    return await _handle_rollback("favorite")


@action_bp.route("/movies/<int:movie_id>/comment", methods=["POST"])
@require_login
@tag(["用户行为"])
async def submit_comment(movie_id: int):
    body = await request.get_json() if request.is_json else {}
    text = (body.get("review_text") or "").strip()
    rating = body.get("rating")
    if rating is not None:
        try:
            rating = float(rating)
        except (TypeError, ValueError):
            return jsonify({"error": "rating 格式无效", "code": "INVALID_RATING"}), 400
    if not text:
        return jsonify({"error": "评论正文不能为空", "code": "EMPTY_REVIEW_TEXT"}), 400

    svc = _get_service()
    user_id = g.user_id

    try:
        result = await svc.execute_action(user_id, movie_id, "comment", review_text=text, rating=rating)
    except ValueError as e:
        code = "DUPLICATE_ACTION" if "已评论" in str(e) else "INVALID_ACTION"
        return jsonify({"error": str(e), "code": code}), 400

    return jsonify(result.model_dump()), 200


@action_bp.route("/movies/<int:movie_id>/comment", methods=["DELETE"])
@require_login
@tag(["用户行为"])
async def delete_comment(movie_id: int):
    return await _handle_rollback("comment")


# ═══════════════════════════════════════════════════════════
# 状态查询
# ═══════════════════════════════════════════════════════════

@action_bp.route("/movies/<int:movie_id>/status", methods=["GET"])
@require_login
@tag(["用户行为"])
async def get_movie_status(movie_id: int):
    svc = _get_service()
    user_id = g.user_id

    result = await svc.get_movie_status(user_id, movie_id)
    return jsonify(result.model_dump()), 200
