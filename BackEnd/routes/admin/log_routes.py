"""
routes/admin/log_routes.py

日志查询接口 — 读 logs/ 目录 JSON 日志，按层级/级别/时间过滤。

端点：
    GET /admin/logs  时间倒序日志列表
"""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from quart import Blueprint, request, jsonify
from utils.auth import require_permission

logger = logging.getLogger(__name__)

log_bp = Blueprint("log_routes", __name__)

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOG_ARCHIVE_PATTERN = re.compile(r"\.log\.\d{4}-\d{2}-\d{2}$")

# 东八区时区常量
CST = timezone(timedelta(hours=8))


def _parse_time(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _parse_since(raw: str | None) -> datetime | None:
    if not raw:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})$", raw)
    if m:
        return datetime.now(CST).replace(
            hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0
        )
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _load_log_entries(
    since: datetime | None,
    level: str | None,
    category: str | None,
    keyword: str | None,
    max_lines: int = 10000,
) -> tuple[list[dict], float | None]:
    entries = []
    latest_ts = 0.0

    if not LOG_DIR.is_dir():
        return entries, None

    cat_files = [f for f in LOG_DIR.iterdir() if f.suffix == ".log" or _LOG_ARCHIVE_PATTERN.search(f.name)]
    cat_files = [f for f in cat_files if "error" not in f.stem]

    for f in sorted(cat_files):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    ts = _parse_time(entry.get("timestamp", ""))
                    ts_val = ts.timestamp() if ts else 0.0
                    if ts_val > latest_ts:
                        latest_ts = ts_val

                    if since and ts and ts < since:
                        continue
                    if level and entry.get("level") != level:
                        continue
                    if category and entry.get("category") != category:
                        continue
                    if keyword and keyword.lower() not in entry.get("message", "").lower():
                        continue

                    entries.append(entry)
                    if len(entries) >= max_lines:
                        break
                if len(entries) >= max_lines:
                    break
        except Exception:
            continue

    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries, latest_ts if latest_ts > 0 else None


@log_bp.route("/logs", methods=["GET"])
@require_permission("system:monitor")
async def query_logs():
    level = request.args.get("level")
    if level and level not in ("ERROR", "WARNING", "INFO"):
        return jsonify({"error": "level 仅支持 ERROR/WARNING/INFO", "code": "BAD_REQUEST"}), 400

    category = request.args.get("category")
    if category and category not in ("access", "service", "infra"):
        return jsonify({"error": "category 仅支持 access/service/infra", "code": "BAD_REQUEST"}), 400

    since = _parse_since(request.args.get("since"))
    keyword = request.args.get("keyword")
    limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    offset = int(request.args.get("offset", 0))

    if not LOG_DIR.is_dir():
        return jsonify({"error": "日志目录不存在", "code": "SERVICE_UNAVAILABLE"}), 503

    entries, latest_ts = _load_log_entries(
        since=since, level=level, category=category, keyword=keyword,
        max_lines=10000,
    )

    total = len(entries)
    items = entries[offset:offset + limit]

    for item in items:
        if "exc_info" in item:
            del item["exc_info"]
        # 时间戳截断到秒（去掉毫秒/微秒）
        if "timestamp" in item:
            item["timestamp"] = re.sub(r"\.\d+", "", item["timestamp"])

    result = {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": limit,
    }
    if latest_ts and latest_ts > 0:
        result["latest_timestamp"] = (
            datetime.fromtimestamp(latest_ts, tz=CST)
            .replace(microsecond=0).isoformat()
        )

    return jsonify(result)
