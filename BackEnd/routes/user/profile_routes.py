"""
routes/user/profile_routes.py

用户个人中心 — 头像上传。

端点：
    POST /user/upload/avatar — 上传用户头像到 TOS

权限要求：登录即可访问，每个用户只能上传自己的头像。
"""

import logging

from quart import Blueprint, request, jsonify
from quart_schema import tag
from utils.auth import require_login

logger = logging.getLogger(__name__)

profile_bp = Blueprint("profile_routes", __name__)


def _get_auth_service():
    from services.auth_service import _get_auth_service as getter
    return getter()


@profile_bp.route("/upload/avatar", methods=["POST"])
@require_login
@tag(["用户个人中心"])
async def upload_avatar():
    """
    上传用户头像到 TOS 并返回公开访问 URL。

    请求：multipart/form-data，字段 file=图片文件
    校验：
        - 文件大小 ≤ 2MB
        - 文件格式仅限 png / jpg / webp
    存储：TOS Key = user-avatar/avatar_{user_uuid}.webp（覆盖旧头像）
    返回：{ success, message, data: { avatar_url } }
    """
    from quart import g
    from config.settings import settings
    from utils.tos_client import get_tos_client

    user_id = g.user_id
    svc = _get_auth_service()

    try:
        user = await svc.get_user(user_id)
    except Exception as e:
        return jsonify({"error": f"用户不存在: {e}"}), 404

    files = await request.files
    uploaded = files.get("file")
    if uploaded is None:
        return jsonify({"error": "请提供头像文件（字段名: file）"}), 400

    file_bytes = uploaded.read()

    max_size = settings.AVATAR_MAX_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_size:
        return jsonify({
            "error": f"文件大小超过限制（最大{settings.AVATAR_MAX_SIZE_MB}MB）"
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

    dest_key = f"user-avatar/avatar_{user.uuid}.webp"
    public_url = await tos.upload(dest_key, file_bytes, content_type="image/webp")
    if not public_url:
        return jsonify({"error": "上传失败，请稍后重试"}), 500

    from models.user import UserUpdate
    await svc.update_user(user_id, UserUpdate(avatar_url=public_url))

    logger.info(f"头像上传成功: user_id={user_id} uuid={user.uuid} url={public_url}")

    return jsonify({
        "success": True,
        "message": "上传成功",
        "data": {
            "avatar_url": public_url,
        },
    })
