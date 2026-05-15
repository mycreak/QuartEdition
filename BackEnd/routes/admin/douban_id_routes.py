"""
routes/admin/douban_id_routes.py

豆瓣电影 ID 资产管理。

端点：
    GET    /admin/douban-ids              列表（默认排除已爬取，支持 is_scraped/is_acquired/admin_id=me 过滤）
    POST   /admin/douban-ids              手动添加 ID（type_num + interval_id 必填）
    POST   /admin/douban-ids/<id>/acquire  认领（原子，先到先得）
    POST   /admin/douban-ids/<id>/release  释放（限本人操作，非本人释放返回 409）

权限：
    读: crawler:task:read
    写/认领: crawler:task:write
"""

import logging
import datetime
from quart import Blueprint, request, jsonify, g
from quart_schema import tag
from utils.auth import require_permission
from db.query_builder import ConditionBuilder

logger = logging.getLogger(__name__)

douban_id_bp = Blueprint("douban_id_routes", __name__)


@douban_id_bp.route("/douban-ids", methods=["GET"])
@require_permission("crawler:task:read")
@tag(["douban_id"])
async def list_douban_ids():
    """
    分页查询 douban_ids，默认排除已爬取成功的 ID。

    参数:
        page, page_size, keyword, is_acquired, type_num, interval_id
        is_scraped:   默认为 0（只返回未爬取的），传 1 或 -1 可查已爬取/全部
        admin_id:     "me" 时自动解析为当前登录用户 ID，过滤自己认领的 ID
    """
    from quart import current_app
    db = current_app.services.db

    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    keyword = request.args.get("keyword", "").strip()
    is_acquired = request.args.get("is_acquired")
    is_scraped_raw = request.args.get("is_scraped")
    type_num = request.args.get("type_num", type=int)
    interval_id = request.args.get("interval_id", "").strip()
    admin_id = request.args.get("admin_id", "").strip()

    where = []
    params = []

    if keyword:
        where.append("(di.douban_id LIKE %s OR di.title LIKE %s)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if is_acquired is not None:
        where.append("di.is_acquired = %s")
        params.append(1 if is_acquired in ("1", "true") else 0)
    # 默认排除已爬取成功的 ID（is_scraped=-1 时不过滤）
    if is_scraped_raw != "-1":
        where.append("di.is_scraped = %s")
        params.append(1 if is_scraped_raw == "1" else 0)
    if type_num:
        where.append("di.type_num = %s")
        params.append(type_num)
    if interval_id:
        where.append("di.interval_id = %s")
        params.append(interval_id)
    if admin_id == "me":
        where.append("di.admin_id = %s")
        params.append(g.user_id)

    where_sql = " AND ".join(where)
    if where_sql:
        where_sql = "WHERE " + where_sql

    count_sql = f"SELECT COUNT(*) AS total FROM douban_ids di {where_sql}"
    count_rows = await db.execute_raw(count_sql, tuple(params))
    total = count_rows[0]["total"] if count_rows else 0

    offset = (page - 1) * page_size
    list_sql = (
        "SELECT di.*, u.display_name AS claimed_by_name "
        "FROM douban_ids di "
        "LEFT JOIN users u ON di.admin_id = u.id "
        f"{where_sql} "
        "ORDER BY di.created_at DESC LIMIT %s OFFSET %s"
    )
    list_params = list(params) + [page_size, offset]
    rows = await db.execute_raw(list_sql, tuple(list_params))

    items = [dict(row) for row in rows]
    return jsonify({"items": items, "total": total, "page": page, "page_size": page_size})


@douban_id_bp.route("/douban-ids", methods=["POST"])
@require_permission("crawler:task:write")
@tag(["douban_id"])
async def add_douban_id():
    """
    手动添加 douban_id。

    请求体:
        douban_id:   必填，豆瓣电影 ID
        title:       必填，电影名
        type_num:    必填，豆瓣类型编号（如 11=剧情），必须存在于 TYPE_MAP
        interval_id: 必填，评分区间（如 "100:90" 表示 9.0~10.0），必须存在于 INTERVALS
    """
    try:
        body = await request.get_json()
        douban_id = (body.get("douban_id") or "").strip()
        title = (body.get("title") or "").strip()
        raw_type_num = body.get("type_num")
        interval_id = (body.get("interval_id") or "").strip() or None
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    if not douban_id or not title:
        return jsonify({"error": "douban_id 和 title 不能为空"}), 400

    # ── type_num 必填 + 合法性校验 ──
    from config.movie_type import TYPE_MAP
    try:
        type_num = int(raw_type_num)
    except (TypeError, ValueError):
        return jsonify({"error": "type_num 必须是整数"}), 400
    if type_num not in TYPE_MAP:
        valid_ids = sorted(TYPE_MAP.keys())
        return jsonify({
            "error": f"type_num 无效: {type_num}，合法值为 {valid_ids}",
            "code": "INVALID_TYPE_NUM",
        }), 400

    # ── interval_id 必填 + 合法性校验 ──
    from config.movie_type import INTERVALS as VALID_INTERVALS
    if not interval_id or interval_id not in VALID_INTERVALS:
        return jsonify({
            "error": f"interval_id 无效: {interval_id}，合法值为 {', '.join(VALID_INTERVALS)}",
            "code": "INVALID_INTERVAL_ID",
        }), 400

    from quart import current_app
    db = current_app.services.db

    try:
        # 用DB层封装的insert方法，自动参数化防注入
        await db.insert(
            "douban_ids",
            {
                "douban_id": douban_id,
                "title": title,
                "source": "manual",
                "admin_id": g.user_id,
                "type_num": type_num,
                "interval_id": interval_id
            }
        )
    except Exception as e:
        # MySQL 1062 Duplicate → douban_id 已存在
        # 1452 FK → type_num 不存在
        code = getattr(e, "args", (None,))[0]
        if code == 1062 or "1062" in str(e):
            return jsonify({
                "error": f"添加失败 — douban_id {douban_id} 已存在",
                "code": "DUPLICATE_DOUBAN_ID",
            }), 409
        elif code == 1452 or "1452" in str(e):
            return jsonify({
                "error": f"添加失败 — type_num={type_num} 不存在或无效",
                "code": "INVALID_TYPE_NUM",
            }), 400
        logger.exception(f"添加 douban_id 异常: {douban_id}")
        return jsonify({"error": "添加失败，服务器内部错误", "code": "INTERNAL_ERROR"}), 500
    except Exception:
        logger.exception(f"添加 douban_id 异常: {douban_id}")
        return jsonify({"error": "添加失败，服务器内部错误", "code": "INTERNAL_ERROR"}), 500

    logger.info(
        f"手动添加 douban_id: {douban_id} title='{title}' "
        f"type_num={type_num} interval={interval_id} admin_id={g.user_id}"
    )
    return jsonify({"success": True, "douban_id": douban_id}), 201


@douban_id_bp.route("/douban-ids/<id>/acquire", methods=["POST"])
@require_permission("crawler:task:write")
@tag(["douban_id"])
async def acquire_douban_id(id: str):
    """
    认领 douban_id — 原子操作，先到先得。

    约束：已爬取完成的 ID（is_scraped=1）不可再次认领。
    """
    from quart import current_app
    db = current_app.services.db

    affected = await db.raw_mysql().execute_update(
        "UPDATE douban_ids SET is_acquired=1, acquired_at=NOW(), admin_id=%s "
        "WHERE douban_id=%s AND is_acquired=0 AND is_scraped=0",
        (g.user_id, id),
    )

    if affected:
        logger.info(f"douban_id 已认领: {id} admin_id={g.user_id}")
        return jsonify({"success": True, "douban_id": id})
    else:
        return jsonify({
            "error": "认领失败 — ID 不存在、已被别人认领、或已爬取完成",
            "code": "ACQUIRE_CONFLICT",
        }), 409


@douban_id_bp.route("/douban-ids/<id>/release", methods=["POST"])
@require_permission("crawler:task:write")
@tag(["douban_id"])
async def release_douban_id(id: str):
    """
    释放 douban_id — 将已认领的电影 ID 恢复为未认领状态。

    校验：
        - 记录必须存在且 is_acquired=1 且 is_scraped=0
        - admin_id 必须与当前用户一致（只能释放自己认领的 ID）
        - 已爬取完成的 ID（is_scraped=1）禁止释放
    """
    from quart import current_app
    db = current_app.services.db

    affected = await db.raw_mysql().execute_update(
        "UPDATE douban_ids SET is_acquired=0, acquired_at=NULL, admin_id=NULL "
        "WHERE douban_id=%s AND is_acquired=1 AND is_scraped=0 AND admin_id=%s",
        (id, g.user_id),
    )

    if affected:
        logger.info(f"douban_id 已释放: {id} admin_id={g.user_id}")
        return jsonify({"success": True, "douban_id": id, "message": "已释放"})
    else:
        return jsonify({
            "error": "释放失败 — ID 不存在、未被认领、不是你认领的、或已爬取完成",
            "code": "RELEASE_CONFLICT",
        }), 409
