"""
routes/admin/movie_routes.py

电影管理 — 查/编/上下架。

端点：
    GET    /admin/movies                   电影列表（分页+搜索+类型过滤+上下架）  [movie:read]
    GET    /admin/movies/<id>              电影详情（聚合视图）                [movie:read]
    PATCH  /admin/movies/<id>              编辑基本信息                          [movie:manage]
    POST   /admin/movies/<id>/publish      上架                                 [movie:manage]
    POST   /admin/movies/<id>/unpublish    下架                                 [movie:manage]
    POST   /admin/movies/<id>/credits      添加演职人员                          [movie:manage]
    DELETE /admin/movies/<id>/credits      移除演职人员                          [movie:manage]
    POST   /admin/movies/<id>/genres       添加类型                              [movie:manage]
    DELETE /admin/movies/<id>/genres/<type_num> 移除类型                        [movie:manage]
    POST   /admin/movies/<id>/regions      添加地区                              [movie:manage]
    DELETE /admin/movies/<id>/regions/<region_id> 移除地区                      [movie:manage]
    PUT    /admin/movies/<id>/rating       更新评分                              [movie:manage]
"""

import logging

from quart import Blueprint, request, jsonify, g
from quart_schema import tag
from utils.auth import require_permission
from utils.errors import ServiceError

logger = logging.getLogger(__name__)

movie_bp = Blueprint("movie_routes", __name__)

# 合法 role_type 白名单
_VALID_ROLES = {"director", "actor", "writer", "producer", "art_director", "music", "other"}


def _as_error(e: ServiceError):
    return jsonify({"error": e.message, "code": e.code}), e.status_code


@movie_bp.route("/movies", methods=["GET"])
@require_permission("movie:read")
@tag(["电影管理"])
async def list_movies():
    keyword = request.args.get("keyword", "").strip()
    type_num = request.args.get("type_num", type=int)
    published = request.args.get("published", type=int)
    release_year = request.args.get("release_year", type=int)
    region_id = request.args.get("region_id", type=int)
    douban_id = request.args.get("douban_id", "").strip()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)

    from quart import current_app
    result = await current_app.services.movie_service.batch_list_movies(
        keyword=keyword,
        type_num=type_num,
        published=published,
        release_year=release_year,
        region_id=region_id,
        douban_id=douban_id,
        page=page,
        page_size=page_size,
    )
    return jsonify(result)


@movie_bp.route("/movies/<int:movie_id>", methods=["GET"])
@require_permission("movie:read")
@tag(["电影管理"])
async def get_movie(movie_id: int):
    from quart import current_app
    try:
        detail = await current_app.services.movie_service.get_movie_detail(movie_id)
        return jsonify(detail.model_dump())
    except ServiceError as e:
        return _as_error(e)


# ═══════════════════════════════════════
# 编辑基本信息
# ═══════════════════════════════════════

@movie_bp.route("/movies/<int:movie_id>", methods=["PATCH"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def update_movie(movie_id: int):
    """
    编辑电影基本信息。

    请求体所有字段可选，只更新传入的非 null 字段：
        title, original_title, release_year, release_date, duration, poster_url, imdb_id, is_published
    """
    from quart import current_app
    from models.movie_models import MovieUpdate

    try:
        body = await request.get_json()
        if not body:
            return jsonify({"error": "请提供需要更新的字段"}), 400
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    try:
        data = MovieUpdate(**body)
    except Exception as e:
        return jsonify({"error": f"参数校验失败: {str(e)}"}), 400

    result = await current_app.services.movie_service.update_movie(
        movie_id, data, changed_by=str(g.user_id),
    )
    if result is None:
        return jsonify({"error": f"电影不存在: {movie_id}", "code": "NOT_FOUND"}), 404

    logger.info(f"电影已编辑: movie_id={movie_id} admin_id={g.user_id}")
    return jsonify({"success": True, "movie": result.model_dump()})


# ═══════════════════════════════════════
# 上下架
# ═══════════════════════════════════════

@movie_bp.route("/movies/<int:movie_id>/publish", methods=["POST"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def publish_movie(movie_id: int):
    from quart import current_app
    try:
        await current_app.services.movie_service.set_movie_published(movie_id, True, changed_by=str(g.user_id))
        return jsonify({"success": True, "message": "电影已上架"})
    except ServiceError as e:
        return _as_error(e)


@movie_bp.route("/movies/<int:movie_id>/unpublish", methods=["POST"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def unpublish_movie(movie_id: int):
    from quart import current_app
    try:
        await current_app.services.movie_service.set_movie_published(movie_id, False, changed_by=str(g.user_id))
        return jsonify({"success": True, "message": "电影已下架"})
    except ServiceError as e:
        return _as_error(e)


# ═══════════════════════════════════════
# 演职人员
# ═══════════════════════════════════════

@movie_bp.route("/movies/<int:movie_id>/credits", methods=["POST"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def add_credit(movie_id: int):
    """
    添加演职人员。

    请求体：
        person_id: 必填，人员 id（people 表）
        role_type: 必填，角色类型（director/actor/writer/producer/art_director/music/other）
    """
    from quart import current_app

    try:
        body = await request.get_json()
        person_id = body.get("person_id")
        role_type = (body.get("role_type") or "").strip()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    if not person_id:
        return jsonify({"error": "person_id 不能为空"}), 400
    if role_type not in _VALID_ROLES:
        return jsonify({
            "error": f"role_type 无效: {role_type}，合法值为 {sorted(_VALID_ROLES)}",
        }), 400

    try:
        result = await current_app.services.movie_service.add_credit(
            movie_id, int(person_id), role_type, changed_by=str(g.user_id),
        )
    except Exception as e:
        return jsonify({"error": f"添加失败: {str(e)}"}), 500

    logger.info(f"演职人员已添加: movie_id={movie_id} person_id={person_id} role={role_type}")
    return jsonify({"success": True, "affected": result}), 201


@movie_bp.route("/movies/<int:movie_id>/credits", methods=["DELETE"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def remove_credit(movie_id: int):
    """
    移除演职人员。

    请求体：
        person_id: 必填
        role_type: 必填
    """
    from quart import current_app

    try:
        body = await request.get_json()
        person_id = body.get("person_id")
        role_type = (body.get("role_type") or "").strip()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    if not person_id:
        return jsonify({"error": "person_id 不能为空"}), 400
    if role_type not in _VALID_ROLES:
        return jsonify({
            "error": f"role_type 无效: {role_type}，合法值为 {sorted(_VALID_ROLES)}",
        }), 400

    result = await current_app.services.movie_service.remove_credit(
        movie_id, int(person_id), role_type, changed_by=str(g.user_id),
    )

    if result == 0:
        return jsonify({"error": "关联不存在", "code": "NOT_FOUND"}), 404

    logger.info(f"演职人员已移除: movie_id={movie_id} person_id={person_id} role={role_type}")
    return jsonify({"success": True, "affected": result})


# ═══════════════════════════════════════
# 电影类型
# ═══════════════════════════════════════

@movie_bp.route("/movies/<int:movie_id>/genres", methods=["POST"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def add_genre(movie_id: int):
    """
    添加电影类型。

    请求体：
        type_num: 必填，豆瓣类型编号（需存在于 crawl_progress 表）
    """
    from quart import current_app
    from config.movie_type import TYPE_MAP

    try:
        body = await request.get_json()
        type_num = body.get("type_num")
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    if not type_num:
        return jsonify({"error": "type_num 不能为空"}), 400
    if int(type_num) not in TYPE_MAP:
        return jsonify({
            "error": f"type_num 无效: {type_num}，合法值为 {sorted(TYPE_MAP.keys())}",
        }), 400

    try:
        result = await current_app.services.movie_service.add_genre_to_movie(
            movie_id, int(type_num), changed_by=str(g.user_id),
        )
    except Exception as e:
        return jsonify({"error": f"添加失败（可能已存在）: {str(e)}"}), 409

    logger.info(f"类型已添加: movie_id={movie_id} type_num={type_num}")
    return jsonify({"success": True, "affected": result}), 201


@movie_bp.route("/movies/<int:movie_id>/genres/<int:type_num>", methods=["DELETE"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def remove_genre(movie_id: int, type_num: int):
    """移除电影类型。"""
    from quart import current_app

    result = await current_app.services.movie_service.remove_genre_from_movie(
        movie_id, type_num, changed_by=str(g.user_id),
    )

    if result == 0:
        return jsonify({"error": "关联不存在", "code": "NOT_FOUND"}), 404

    logger.info(f"类型已移除: movie_id={movie_id} type_num={type_num}")
    return jsonify({"success": True, "affected": result})


# ═══════════════════════════════════════
# 地区字典管理
# ═══════════════════════════════════════

@movie_bp.route("/regions", methods=["GET"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def list_regions():
    """
    获取全部地区列表（数量少，不分页）。

    返回: [{id: 1, name: "中国大陆"}, ...]
    """
    from quart import current_app
    regions = await current_app.services.movie_service.list_regions()
    return jsonify([r.model_dump() for r in regions])


@movie_bp.route("/regions", methods=["POST"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def create_region():
    """
    创建新地区（含唯一性校验）。

    请求体: {name: "日本"}
    返回:
        201 — 新创建  {success: true, region: {id, name}, is_new: true}
        200 — 已存在  {success: true, region: {id, name}, is_new: false, message: "该地区已存在"}
        400 — 名称无效
    """
    from quart import current_app
    from models.movie_models import RegionCreate

    try:
        body = await request.get_json()
        data = RegionCreate(**body)
    except Exception as e:
        return jsonify({"error": f"参数校验失败: {str(e)}"}), 400

    try:
        region, is_new = await current_app.services.movie_service.create_region(data.name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if is_new:
        logger.info("新地区已创建: id=%s name=%s", region.id, region.name)
        return jsonify({
            "success": True,
            "region": region.model_dump(),
            "is_new": True,
        }), 201
    else:
        return jsonify({
            "success": True,
            "region": region.model_dump(),
            "is_new": False,
            "message": "该地区已存在",
        }), 200


# ═══════════════════════════════════════
# 地区
# ═══════════════════════════════════════

@movie_bp.route("/movies/<int:movie_id>/regions", methods=["POST"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def add_region(movie_id: int):
    """
    添加电影地区。

    请求体：
        region_id: 必填，地区 id（regions 表）
    """
    from quart import current_app

    try:
        body = await request.get_json()
        region_id = body.get("region_id")
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    if not region_id:
        return jsonify({"error": "region_id 不能为空"}), 400

    try:
        result = await current_app.services.movie_service.add_region_to_movie(
            movie_id, int(region_id), changed_by=str(g.user_id),
        )
    except Exception as e:
        return jsonify({"error": f"添加失败（可能已存在）: {str(e)}"}), 409

    logger.info(f"地区已添加: movie_id={movie_id} region_id={region_id}")
    return jsonify({"success": True, "affected": result}), 201


@movie_bp.route("/movies/<int:movie_id>/regions/<int:region_id>", methods=["DELETE"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def remove_region(movie_id: int, region_id: int):
    """移除电影地区。"""
    from quart import current_app

    result = await current_app.services.movie_service.remove_region_from_movie(
        movie_id, region_id, changed_by=str(g.user_id),
    )

    if result == 0:
        return jsonify({"error": "关联不存在", "code": "NOT_FOUND"}), 404

    logger.info(f"地区已移除: movie_id={movie_id} region_id={region_id}")
    return jsonify({"success": True, "affected": result})


# ═══════════════════════════════════════
# 评分
# ═══════════════════════════════════════

@movie_bp.route("/movies/<int:movie_id>/rating", methods=["PUT"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def update_rating(movie_id: int):
    """
    更新电影评分（幂等，不存在则创建）。

    请求体：
        average: 必填，评分值 (0.0~10.0)
        count:   必填，评分人数
    """
    from quart import current_app
    from models.movie_models import RatingCreate

    try:
        body = await request.get_json()
        data = RatingCreate(**body)
    except Exception as e:
        return jsonify({"error": f"参数校验失败: {str(e)}"}), 400

    await current_app.services.movie_service.set_rating(movie_id, data)
    logger.info(f"评分已更新: movie_id={movie_id} average={data.average}")
    return jsonify({"success": True, "average": data.average, "count": data.count})


# ═══════════════════════════════════════
# 批量下发长评正文 — 查询接口
# ═══════════════════════════════════════

@movie_bp.route("/movies/with-pending-reviews", methods=["GET"])
@require_permission("crawler:task:write")
@tag(["爬虫任务"])
async def list_movies_with_pending_reviews():
    """
    返回 movie_review 中有 pending 长评的电影列表。

    按 pending 数量降序，方便管理员优先处理积压最多的电影。

    权限: crawler:task:write（复用提交任务的权限，无需新增权限点）
    """
    from quart import current_app

    raw = current_app.services.movie_service.db.raw_mysql()
    rows = await raw.execute_query(
        """SELECT m.id AS movie_id, m.douban_id, m.title,
                  COUNT(mr.review_id) AS pending_count
           FROM movies m
           JOIN movie_review mr ON m.id = mr.movie_id
           WHERE mr.status = 'pending'
           GROUP BY m.id, m.douban_id, m.title
           ORDER BY pending_count DESC"""
    )

    items = [
        {
            "movie_id": r["movie_id"],
            "douban_id": r.get("douban_id") or "",
            "title": r["title"],
            "pending_count": r["pending_count"],
        }
        for r in rows
    ]
    return jsonify({"items": items})


@movie_bp.route("/movies/<int:movie_id>/pending-reviews", methods=["GET"])
@require_permission("crawler:task:write")
@tag(["爬虫任务"])
async def list_pending_reviews(movie_id: int):
    """
    返回指定电影的 pending 长评列表（分页），用于批量勾选提交。

    参数:
        page:     页码，默认 1
        page_size: 每页条数，默认 10

    权限: crawler:task:write（复用提交任务的权限，无需新增权限点）
    """
    from quart import current_app

    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 10, type=int)
    offset = (page - 1) * page_size

    raw = current_app.services.movie_service.db.raw_mysql()

    count_rows = await raw.execute_query(
        "SELECT COUNT(1) AS total FROM movie_review WHERE movie_id = %s AND status = 'pending'",
        (movie_id,),
    )
    total = count_rows[0]["total"] if count_rows else 0

    rows = await raw.execute_query(
        """SELECT review_id, title, author, useful_count, `date`
           FROM movie_review
           WHERE movie_id = %s AND status = 'pending'
           ORDER BY useful_count DESC
           LIMIT %s OFFSET %s""",
        (movie_id, page_size, offset),
    )

    items = [
        {
            "review_id": r["review_id"],
            "title": r["title"],
            "author": r["author"],
            "useful_count": r["useful_count"],
            "date": str(r["date"]) if r.get("date") else "",
        }
        for r in rows
    ]
    return jsonify({"items": items, "total": total, "page": page, "page_size": page_size})
