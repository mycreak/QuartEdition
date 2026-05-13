"""
routes/admin/status_routes.py

系统实时状态。

端点：
    GET /admin/status       — Puller/Worker/Queue/CPU/内存/DB 健康
    GET /admin/tasks/queue  — 任务队列实时快照
    GET /admin/rate-limit-events — 限流事件查询
"""

import logging
import json
import time as _time
from typing import Optional, Tuple

from quart import Blueprint, jsonify, request
from quart_schema import tag
from utils.auth import require_permission

logger = logging.getLogger(__name__)

status_bp = Blueprint("status_routes", __name__)

# DB 健康检查缓存（减少 /admin/status 耗时 → 避免每次 ~1000ms）
# 模块级全局 — asyncio 单线程安全；若改用 hypercorn -w 4 多 worker，需改为 Redis 缓存
_db_health_cache: Optional[Tuple[float, dict]] = None
_DB_HEALTH_TTL = 10.0


async def _get_db_health() -> dict:
    """获取数据库健康状态，10 秒内缓存复用。"""
    global _db_health_cache
    from quart import current_app
    now = _time.time()
    if _db_health_cache and now - _db_health_cache[0] < _DB_HEALTH_TTL:
        return _db_health_cache[1]
    try:
        db_health = await current_app.services.db.ping_all()
        _db_health_cache = (now, db_health)
        return db_health
    except Exception:
        return {"mysql": False, "redis": False, "mongodb": False}


@status_bp.route("/status", methods=["GET"])
@require_permission("system:monitor")
@tag(["系统监控"])
async def system_status():
    from quart import current_app
    from background.puller import get_puller
    from background.worker import get_browser_pool
    from utils.system_monitor import get_system_health

    app = current_app
    status = {}

    try:
        puller = await get_puller()
        status["puller_state"] = puller.state
        status["puller_fetched"] = puller.stats.total_fetched
        status["puller_empty_polls"] = puller.stats.total_empty_polls
    except Exception as e:
        status["puller_error"] = str(e)

    try:
        queue = app.task_queue
        qsize = queue.qsize()
        status["queue_size"] = qsize
        status["queue_maxsize"] = queue.maxsize
        status["queue_saturation"] = round(qsize / queue.maxsize, 2) if queue.maxsize else 0
    except Exception:
        pass

    try:
        pool = get_browser_pool()
        health = pool.get_worker_health()
        status.update({
            "worker_alive": health["alive"],
            "worker_expected": health["expected"],
            "worker_dead": len(health["dead"]),
            "worker_stuck": len(health["stuck"]),
            "worker_busy": health["busy_count"],
            "worker_idle": health["idle_count"],
        })
    except Exception:
        pass

    try:
        system = await get_system_health()
        status["cpu_percent"] = system["cpu_percent"]
        status["memory_percent"] = system["memory_percent"]
    except Exception:
        pass

    try:
        db_health = await _get_db_health()
        status["db_mysql"] = db_health["mysql"]
        status["db_redis"] = db_health["redis"]
        status["db_mongodb"] = db_health["mongodb"]
    except Exception:
        pass

    # ── Cookie 健康 ──
    try:
        import os, json
        storage_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "douban_storage.json",
        )
        if os.path.exists(storage_file):
            with open(storage_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            status["cookie_saved_at"] = raw.get("saved_at", None)
            playwright_state = raw.get("playwright_state", raw)
            cookies = {c.get("name"): c.get("value", "") for c in playwright_state.get("cookies", [])}
            status["cookie_has_dbcl2"] = bool(cookies.get("dbcl2"))
            status["cookie_valid"] = bool(cookies.get("dbcl2"))
        else:
            status["cookie_saved_at"] = None
            status["cookie_has_dbcl2"] = False
            status["cookie_valid"] = False
    except Exception:
        pass

    # ── 代理池健康 ──
    try:
        from crawler.proxy import get_proxy_pool
        pool = get_proxy_pool()
        status["proxy"] = pool.get_stats()
    except Exception:
        pass

    return jsonify(status)


@status_bp.route("/tasks/queue", methods=["GET"])
@require_permission("system:monitor")
@tag(["系统监控"])
async def task_queue_status():
    """
    实时任务队列快照 — Redis ZSET 待拉取 + asyncio.Queue + Worker 状态。

    ?details=1 → 同时返回 redis_tasks / queue_tasks / in_flight 详情
    """
    from quart import current_app
    from background.worker import get_browser_pool
    from db.redis import get_redis as _get_redis
    from config.db_config import get_redis_config

    app = current_app
    result = {}
    include_details = request.args.get("details") == "1"

    try:
        redis_client = _get_redis()
        key = get_redis_config().delay_queue_key
        result["redis_size"] = await redis_client.zcard(key)

        if include_details:
            tasks = await redis_client.zrange(key, 0, 19)
            result["redis_tasks"] = [
                _summarize_task(t) for t in tasks if t
            ]
    except Exception:
        result["redis_size"] = -1

    try:
        queue = app.task_queue
        result["queue_size"] = queue.qsize()

        if include_details:
            result["queue_tasks"] = [
                _summarize_task(t) for t in list(queue._queue) if t
            ]
    except Exception:
        result["queue_size"] = -1

    try:
        pool = get_browser_pool()
        health = pool.get_worker_health()
        result["worker_busy"] = health["busy_count"]
        result["worker_idle"] = health["idle_count"]

        if include_details:
            in_flight = []
            for wid, task_str in pool._worker_current_task.items():
                summary = _summarize_task(task_str)
                summary["worker_id"] = wid
                summary["busy_seconds"] = round(_time.time() - pool._busy_since.get(wid, 0), 1)
                # 从 task_history 获取最新进度 message
                task_id = summary.get("task_id", 0)
                if task_id:
                    try:
                        from services.task_history_service import _get_history_service
                        record = await _get_history_service().get(task_id)
                        if record and record.get("message"):
                            summary["stage"] = record["message"]
                    except Exception:
                        pass
                in_flight.append(summary)
            result["in_flight"] = in_flight
    except Exception:
        pass

    return jsonify(result)


def _summarize_task(task_str: str) -> dict:
    """从任务 JSON 提取摘要信息。"""
    try:
        data = json.loads(task_str)
    except (json.JSONDecodeError, TypeError):
        return {}
    t = data.get("type", "")
    summary = {
        "type": t,
        "task_id": data.get("id", 0),
        "admin_id": data.get("admin_id", 0),
    }
    if t == "movie_crawl":
        summary["type_num"] = data.get("type_num")
        summary["interval_id"] = data.get("interval_id", "")
        summary["label"] = f"补充ID: type={data.get('type_num')} interval={data.get('interval_id','')}"
    elif t == "movie_scrape_task":
        douban_id = data.get("douban_id", "")
        summary["douban_id"] = douban_id
        summary["cookie_id"] = data.get("cookie_id", "")
        summary["proxy_key"] = data.get("proxy_key", "")
        summary["label"] = f"爬取影片: {data.get('title', douban_id)}"
    elif t == "review_crawl":
        summary["subject_id"] = data.get("douban_id") or data.get("subject_id", "")
        summary["movie_id"] = data.get("movie_id")
        summary["label"] = f"采集长评摘要: movie={data.get('movie_id')}"
    elif t == "review_body_crawl":
        summary["review_id"] = data.get("review_id", "")
        summary["label"] = f"爬取长评正文: {data.get('title', data.get('review_id',''))}"
    elif t == "comment_crawl":
        summary["subject_id"] = data.get("douban_id") or data.get("subject_id", "")
        summary["movie_id"] = data.get("movie_id")
        summary["label"] = f"爬取短评: movie={data.get('movie_id')}"
    else:
        summary["label"] = t
    return summary


@status_bp.route("/rate-limit-events", methods=["GET"])
@require_permission("system:monitor")
@tag(["系统监控"])
async def rate_limit_events():
    """
    限流事件查询 — 从 Redis ZSET 中读取最近事件。
    """
    from db.redis import get_redis as _get_redis
    import time as _time
    import json as _json

    minutes = min(max(int(request.args.get("minutes", 60)), 1), 1440)
    endpoint_filter = request.args.get("endpoint")

    endpoints = ["login", "register"]
    now = _time.time()
    since = now - minutes * 60

    events = []
    try:
        redis_client = _get_redis()
    except Exception:
        return jsonify({
            "endpoints": {"login": {"total": -1, "window_seconds": 60, "max_requests": 5},
                          "register": {"total": -1, "window_seconds": 60, "max_requests": 3}},
            "events": [],
            "total_events": 0,
        })

    for ep in endpoints:
        if endpoint_filter and ep != endpoint_filter:
            continue
        key = f"ratelimit:events:{ep}"
        try:
            raw = await redis_client.zrangebyscore(key, since, now)
            for member in raw:
                evt = _json.loads(member)
                evt["endpoint"] = ep
                events.append(evt)
        except Exception:
            pass

    events.sort(key=lambda e: e.get("ts", 0), reverse=True)

    endpoints_summary = {}
    for ep in endpoints:
        ep_events = [e for e in events if e.get("endpoint") == ep]
        sample = ep_events[0] if ep_events else {}
        endpoints_summary[ep] = {
            "total": len(ep_events),
            "window_seconds": sample.get("window_seconds", 60),
            "max_requests": sample.get("max_requests", 5 if ep == "login" else 3),
        }

    return jsonify({
        "endpoints": endpoints_summary,
        "events": events,
        "total_events": len(events),
    })
