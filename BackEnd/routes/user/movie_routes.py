"""
routes/user/movie_routes.py

电影浏览（需登录，仅上架）。

端点：
    GET /user/movies                        电影列表（分页+搜索+类型过滤，按评分降序）
    GET /user/movies/<id>                   电影详情
    GET /user/movies/<movie_id>/comment-wordcloud  短评词云
"""

import json
import logging
from datetime import datetime, timezone

from quart import Blueprint, request, jsonify
from quart_schema import tag
from utils.auth import require_login
from utils.errors import ServiceError

logger = logging.getLogger(__name__)

movie_bp = Blueprint("user_movie_routes", __name__)


@movie_bp.route("/movies", methods=["GET"])
@require_login
@tag(["电影浏览"])
async def list_movies():
    keyword = request.args.get("keyword", "").strip()
    type_num = request.args.get("type_num", type=int)
    interval_ids = request.args.get("interval_ids", "")
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)

    from quart import current_app
    result = await current_app.services.movie_service.batch_list_movies(
        keyword=keyword,
        type_num=type_num,
        published=1,
        interval_ids=interval_ids,
        page=page,
        page_size=page_size,
    )
    return jsonify(result)


@movie_bp.route("/movies/<int:movie_id>", methods=["GET"])
@require_login
@tag(["电影浏览"])
async def get_movie(movie_id: int):
    from quart import current_app

    try:
        detail = await current_app.services.movie_service.get_movie_detail(movie_id)
    except ServiceError as e:
        return jsonify({"error": e.message, "code": e.code}), e.status_code

    if not detail.movie.is_published:
        return jsonify({"error": "电影不存在", "code": "NOT_FOUND"}), 404

    # 白名单构建用户端响应 — 不暴露管理字段（is_published/douban_id 等）
    movie = detail.movie
    data = {
        "movie": {
            "id": movie.id,
            "title": movie.title,
            "original_title": movie.original_title,
            "release_year": movie.release_year,
            "release_date": movie.release_date,
            "duration": movie.duration,
            "poster_url": movie.poster_url,
        },
        "rating": detail.rating.model_dump() if detail.rating else None,
        "directors": [d.model_dump() for d in detail.directors],
        "actors": [a.model_dump() for a in detail.actors],
        "crew": detail.crew,
        "genres": [g.model_dump() for g in detail.genres],
        "regions": [r.model_dump() for r in detail.regions],
        # AI 聚合字段 — 与管理员接口一致
        "ai_summary": detail.ai_summary,
        "ai_tags": detail.ai_tags,
    }
    return jsonify(data)


@movie_bp.route("/movies/<int:movie_id>/comment-wordcloud", methods=["GET"])
@require_login
@tag(["电影浏览"])
async def get_comment_wordcloud(movie_id: int):
    """
    获取电影短评词云数据。

    数据流：
        ① Redis 缓存命中 → 直接返回
        ② 缓存未命中 → MongoDB 取短评 → DeepSeek 生成 → Redis 永久缓存 → 返回
        ③ 短评爬取入库 / 管理员上下架时主动删缓存，触发下次重新生成

    短评 < 10 条：返回空词云（不值得调用 AI）
    """
    from quart import current_app
    from db.redis import redis_get, redis_set
    from utils.ai_client import get_ai_client
    from services.review_service import _get_review_service

    cache_key = f"wordcloud:movie:{movie_id}"

    # 1. 查缓存（Redis 不可用时降级为实时生成，不报 500）
    try:
        cached = await redis_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
            except json.JSONDecodeError:
                logger.warning("词云缓存 JSON 解析失败 movie_id=%s，将删除损坏缓存", movie_id)
                try:
                    from db.redis import redis_delete
                    await redis_delete(cache_key)
                except Exception:
                    pass
            else:
                return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.warning("Redis 读取缓存失败 movie_id=%s: %s，降级为实时生成", movie_id, e)

    # 2. 取短评文本
    try:
        review_svc = _get_review_service()
        comments = await review_svc.get_comments_text_by_movie_id(movie_id, limit=200)
    except Exception as e:
        logger.error("获取短评文本失败 movie_id=%s: %s", movie_id, e)
        return jsonify({"success": False, "error": "获取短评数据失败，请稍后重试"}), 500

    if len(comments) < 10:
        empty_data = {"words": [], "total_words": 0, "updated_at": None}
        return jsonify({"success": True, "data": empty_data})

    # 3. 调用 AI 生成词云（内部已做重试+异常捕获，失败返回 None）
    ai_client = get_ai_client()
    words = await ai_client.generate_comment_wordcloud(comments)

    if not words:
        return jsonify({"success": False, "error": "词云生成失败，请稍后重试"}), 500

    # 4. 写缓存 + 返回（缓存写入失败不影响主流程）
    data = {
        "words": words,
        "total_words": len(words),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        await redis_set(cache_key, json.dumps(data, ensure_ascii=False))
    except Exception as e:
        logger.warning("Redis 写入词云缓存失败 movie_id=%s: %s", movie_id, e)

    return jsonify({"success": True, "data": data})
