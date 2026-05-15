"""
routes/admin/task_routes.py

爬虫任务提交与进度查询。

端点：
    POST /admin/tasks  — 提交任务（movie_crawl / movie_scrape_task / director_crawl / review_crawl / review_body_crawl / comment_crawl）
    GET  /admin/tasks  — 爬取进度列表（三指标：crawled_count / scraped_count / completed_count）
"""

import json
import logging
import time

from quart import Blueprint, request, jsonify, g
from quart_schema import tag
from utils.auth import require_permission

logger = logging.getLogger(__name__)

task_bp = Blueprint("task_routes", __name__)


@task_bp.route("/tasks", methods=["POST"])
@require_permission("crawler:task:write")
@tag(["爬虫任务"])
async def submit_task():
    try:
        body = await request.get_json()
    except Exception:
        return jsonify({"error": "请求体必须为 JSON"}), 400

    task_type = body.get("type", "").strip()
    if task_type not in ("movie_crawl", "review_crawl", "review_body_crawl",
                         "comment_crawl", "movie_scrape_task", "director_crawl"):
        return jsonify({"error": f"不支持的任务类型: {task_type}"}), 400

    from utils.snowflake import generate_id
    from quart import current_app

    task_id = generate_id()
    admin_id = g.user_id
    now = time.time()

    task_data = {"id": task_id, "type": task_type, "admin_id": admin_id, "created_at": now}

    if task_type == "movie_crawl":
        type_num = body.get("type_num")
        interval_id = body.get("interval_id", "").strip()
        if not type_num or not interval_id:
            return jsonify({"error": "movie_crawl 需要 type_num 和 interval_id"}), 400
        task_data["type_num"] = type_num
        task_data["interval_id"] = interval_id

    elif task_type == "movie_scrape_task":
        douban_id = body.get("douban_id", "").strip()
        cookie_id = body.get("cookie_id", "").strip()
        proxy_key = body.get("proxy_key", "").strip()
        if not douban_id:
            return jsonify({"error": "movie_scrape_task 需要 douban_id"}), 400
        task_data["douban_id"] = douban_id
        task_data["cookie_id"] = cookie_id
        task_data["proxy_key"] = proxy_key

    elif task_type in ("review_crawl", "review_body_crawl", "comment_crawl"):
        douban_id = (body.get("douban_id") or body.get("subject_id") or "").strip()
        if not douban_id:
            return jsonify({"error": f"{task_type} 需要 douban_id（或 subject_id）"}), 400
        task_data["douban_id"] = douban_id

        # 可选：显式指定身份（cookie + 代理），不传则游客 + ProxyPool 轮转
        cookie_id = body.get("cookie_id", "").strip()
        proxy_key = body.get("proxy_key", "").strip()
        task_data["cookie_id"] = cookie_id
        task_data["proxy_key"] = proxy_key

        movie_id = body.get("movie_id")
        if movie_id is not None:
            task_data["movie_id"] = movie_id

        if task_type == "review_crawl":
            task_data["url"] = f"https://movie.douban.com/subject/{douban_id}/reviews"
            # 兼容前端统一的 pages 参数 + 旧字段 review_pages
            pages = body.get("pages") or body.get("review_pages")
            if pages is not None:
                task_data["review_pages"] = pages  # 爬虫内统一用 review_pages
        elif task_type == "review_body_crawl":
            review_id = body.get("review_id", "").strip()
            task_data["review_id"] = review_id
            task_data["title"] = body.get("title", "")
            task_data["author"] = body.get("author", "")
            task_data["url"] = f"https://movie.douban.com/review/{review_id}/"

            # ── 去重逻辑 ──
            if review_id:
                # ① 查 MySQL：已爬取成功（status='done'）→ 跳过
                from quart import current_app
                raw = current_app.services.movie_service.db.raw_mysql()
                status_rows = await raw.execute_query(
                    "SELECT status FROM movie_review WHERE review_id = %s LIMIT 1",
                    (review_id,),
                )
                if status_rows and status_rows[0]["status"] == "done":
                    return jsonify({
                        "skipped": True,
                        "reason": "已爬取成功",
                        "review_id": review_id,
                    }), 200

                # ② 查 Redis：已在队列中 → 跳过
                try:
                    from db.redis import get_redis
                    r = get_redis()
                    dedup_key = f"crawler:dedup:review_body:{review_id}"
                    if await r.exists(dedup_key):
                        return jsonify({
                            "skipped": True,
                            "reason": "已在待执行队列中",
                            "review_id": review_id,
                        }), 200
                except Exception:
                    pass  # Redis 不可用不阻塞提交，降级为只查 MySQL

            max_count = body.get("max_count")
            if max_count is not None:
                task_data["max_count"] = max_count
        else:
            task_data["url"] = f"https://movie.douban.com/subject/{douban_id}/comments"
            # 兼容前端统一的 pages 参数 + 旧字段 comment_pages
            pages = body.get("pages") or body.get("comment_pages")
            if pages is not None:
                task_data["comment_pages"] = pages  # 爬虫内统一用 comment_pages

    elif task_type == "director_crawl":
        douban_id = body.get("douban_id", "").strip()
        movie_id = body.get("movie_id")
        if not douban_id or not movie_id:
            return jsonify({"error": "director_crawl 需要 douban_id 和 movie_id"}), 400
        task_data["douban_id"] = douban_id
        task_data["movie_id"] = movie_id
        cookie_id = body.get("cookie_id", "").strip()
        proxy_key = body.get("proxy_key", "").strip()
        task_data["cookie_id"] = cookie_id
        task_data["proxy_key"] = proxy_key

    task_json = json.dumps(task_data, ensure_ascii=False)

    app = current_app
    from config.puller_config import puller_config
    execute_at = await app.services.db.add_delayed_task_with_limit(
        task_json=task_json,
        cooldown_seconds=puller_config.task_cooldown_seconds,
    )

    logger.info(
        f"任务已提交: task_id={task_id} type={task_type} "
        f"admin_id={admin_id} execute_at={execute_at:.1f}"
    )

    try:
        from services.task_history_service import _get_history_service
        await _get_history_service().create(
            task_id=task_id,
            admin_id=admin_id,
            task_type=task_type,
            task_params=task_data,
            status="submitted",
        )
    except Exception:
        logger.exception("task_history 写入失败（不影响主流程）")

    # review_body_crawl 去重：写入 Redis key，防止重复提交
    if task_type == "review_body_crawl":
        review_id = task_data.get("review_id", "")
        if review_id:
            try:
                from db.redis import get_redis
                r = get_redis()
                dedup_key = f"crawler:dedup:review_body:{review_id}"
                await r.set(dedup_key, "1", ex=3600)  # 1 小时 TTL，覆盖任务生命周期
            except Exception:
                pass  # Redis 不可用不影响主流程

    return jsonify({
        "task_id": task_id,
        "type": task_type,
        "execute_at": execute_at,
        "url": task_data.get("url", ""),
        "message": f"{task_type} 任务已提交",
    }), 201


@task_bp.route("/tasks", methods=["GET"])
@require_permission("crawler:task:read")
@tag(["爬虫任务"])
async def list_tasks():
    """
    爬取进度列表 — 三指标单次查询，支持按类型和评分区间过滤。

    查询参数：
        type_num:    类型编号（可选）
        interval_id: 评分区间（可选，如 "100:90"）
        page:        页码（默认 1）
        page_size:   每页条数（默认 100）

    返回字段：
        crawled_count  — douban_ids 去重计数（该类型+区间已入库的独立 douban_id 数量）
        scraped_count  — movies 已入库的独立电影数（详情页爬取完成）
        completed_count — movie_credits 已有关联的独立电影数（演职人员爬取完成）
        done = crawled_count >= douban_total

    性能：
        单次 LEFT JOIN + GROUP BY（不是 N 个子查询），索引覆盖：
        douban_ids.idx_source(type_num,interval_id) → GROUP BY
        movies.idx_douban(douban_id) → JOIN
        movie_credits.PK(movie_id,person_id) → JOIN
    """
    type_num = request.args.get("type_num", type=int)
    interval_id = request.args.get("interval_id", "").strip()
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 100, type=int)

    from quart import current_app
    db = current_app.services.db
    raw = db.raw_mysql()

    where_clauses = []
    params = []
    if type_num:
        where_clauses.append("cp.type_num = %s")
        params.append(type_num)
    if interval_id:
        where_clauses.append("cp.interval_id = %s")
        params.append(interval_id)
    where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    count_sql = f"SELECT COUNT(*) AS total FROM crawl_progress cp {where}"
    count_rows = await raw.execute_query(count_sql, tuple(params))
    total = count_rows[0]["total"] if count_rows else 0

    offset = (page - 1) * page_size
    data_sql = (
        "SELECT cp.*, "
        "  COALESCE(agg.crawled_count, 0) AS crawled_count, "
        "  COALESCE(agg.scraped_count, 0) AS scraped_count, "
        "  COALESCE(agg.completed_count, 0) AS completed_count "
        "FROM crawl_progress cp "
        "LEFT JOIN ("
        "  SELECT di.type_num, di.interval_id, "
        "    COUNT(DISTINCT di.douban_id) AS crawled_count, "
        "    COUNT(DISTINCT m.id) AS scraped_count, "
        "    COUNT(DISTINCT CASE WHEN mc.movie_id IS NOT NULL THEN m.id END) AS completed_count "
        "  FROM douban_ids di "
        "  LEFT JOIN movies m ON di.douban_id = m.douban_id "
        "  LEFT JOIN movie_credits mc ON m.id = mc.movie_id "
        "  GROUP BY di.type_num, di.interval_id"
        f") agg ON cp.type_num = agg.type_num AND cp.interval_id = agg.interval_id "
        f"{where} "
        "ORDER BY cp.type_num ASC LIMIT %s OFFSET %s"
    )
    params.extend([page_size, offset])
    rows = await raw.execute_query(data_sql, tuple(params))

    items = []
    for r in rows:
        r["done"] = r["crawled_count"] >= r["douban_total"] if r.get("douban_total", 0) > 0 else False
        items.append(r)

    return jsonify({"items": items, "page": page, "page_size": page_size, "total": total})
