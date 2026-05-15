"""
routes/admin/poster_routes.py

电影海报封面上传。

端点：
    POST /upload/poster — 上传电影海报到 TOS

权限要求：movie:manage（和编辑电影信息一致）
前端负责 16:9 裁剪 + webp 压缩，后端只存储不处理。
"""

import logging
import time
import secrets

from quart import Blueprint, request, jsonify
from quart_schema import tag
from utils.auth import require_permission

logger = logging.getLogger(__name__)

poster_bp = Blueprint("poster_routes", __name__)


@poster_bp.route("/upload/poster", methods=["POST"])
@require_permission("movie:manage")
@tag(["电影管理"])
async def upload_poster():
    """
    上传电影海报封面到 TOS。

    请求：multipart/form-data，字段 file=图片文件
    校验：
        - 文件大小 ≤ 5MB（POSTER_MAX_SIZE_MB）
        - 文件格式仅限 png / jpg / webp
    存储：TOS Key = covers/movie_{timestamp}_{6位随机}.webp
    返回：{ success, data: { poster_url } }
    """
    from config.settings import settings
    from utils.tos_client import get_tos_client

    files = await request.files
    uploaded = files.get("file")
    if uploaded is None:
        return jsonify({"error": "请提供海报文件（字段名: file）"}), 400

    file_bytes = uploaded.read()

    max_size = settings.POSTER_MAX_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_size:
        return jsonify({
            "error": f"文件大小超过限制（最大{settings.POSTER_MAX_SIZE_MB}MB）"
        }), 400

    content_type = uploaded.content_type or ""
    allowed = [t.strip() for t in settings.AVATAR_ALLOWED_TYPES.split(",")]
    if content_type not in allowed:
        return jsonify({
            "error": f"不支持的文件格式（仅支持{settings.AVATAR_ALLOWED_TYPES}）"
        }), 400

    tos = get_tos_client()
    if tos is None or not tos.enabled:
        return jsonify({"error": "上传失败，请稍后重试"}), 500

    rand_suffix = secrets.token_hex(3)
    dest_key = f"covers/movie_{int(time.time())}_{rand_suffix}.webp"
    public_url = await tos.upload(dest_key, file_bytes, content_type="image/webp")
    if not public_url:
        return jsonify({"error": "上传失败，请稍后重试"}), 500

    logger.info(f"海报上传成功: key={dest_key} url={public_url}")

    return jsonify({
        "success": True,
        "data": {
            "poster_url": public_url,
        },
    })
