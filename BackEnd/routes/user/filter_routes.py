"""
routes/user/filter_routes.py

过滤器数据包 — 前端下拉框的数据源（需登录，仅上架）。

端点：
    GET /user/filter-packet   类型列表 + 评分区间（各含影片数）
"""

import logging

from quart import Blueprint, jsonify
from quart_schema import tag
from utils.auth import require_login

logger = logging.getLogger(__name__)

filter_bp = Blueprint("user_filter_routes", __name__)


@filter_bp.route("/filter-packet", methods=["GET"])
@require_login
@tag(["过滤器"])
async def filter_packet():
    from quart import current_app
    result = await current_app.services.movie_service.filter_packet(published_only=True)
    return jsonify(result)
