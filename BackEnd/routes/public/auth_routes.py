"""
routes/public/auth_routes.py

认证端点 — 注册（公开）、登录（公开）、当前用户（需 JWT）。

端点：
    POST /auth/login    — 用户名+密码 → JWT（无鉴权）
    POST /auth/register — 创建普通用户（无鉴权）
    GET  /auth/me       — 当前用户信息 + 角色(user/admin) + 权限列表（需 JWT）

错误处理：
    所有 Service 层异常由 except ServiceError 统一捕获，
    不再用手动 if not 猜状态码。
"""

import logging

from quart import Blueprint, request, jsonify
from pydantic import ValidationError
from quart_schema import tag

from models.user import UserLogin, UserCreate
from utils.auth import get_current_user
from utils.errors import ServiceError, TooManyRequestsError

logger = logging.getLogger(__name__)

auth_bp = Blueprint("public_auth_routes", __name__)


def _get_auth_service():
    from services.auth_service import _get_auth_service as getter
    return getter()


def _as_error(e: ServiceError):
    """ServiceError → HTTP JSON 响应"""
    return jsonify({"error": e.message, "code": e.code}), e.status_code


@auth_bp.route("/login", methods=["POST"])
@tag(["认证"])
async def login():
    # ── 限流：同一 IP 每分钟最多 5 次登录请求 ──
    from quart import current_app
    from utils.rate_limit import check_rate_limit
    try:
        await check_rate_limit(
            db=current_app.services.db,
            key_prefix="ratelimit:login",
            identifier=request.remote_addr or "unknown",
            max_requests=5,
            window_seconds=60,
        )
    except TooManyRequestsError as e:
        return jsonify({"error": e.message, "code": e.code}), e.status_code

    try:
        body = await request.get_json()
        data = UserLogin(**body)
    except (ValidationError, TypeError) as e:
        return jsonify({"error": f"请求格式错误: {e}"}), 400

    svc = _get_auth_service()
    try:
        user = await svc.authenticate(data)
        token = svc.create_token(user["id"])
        permissions = await svc.get_user_permissions(user["id"])

        return jsonify({
            "token": token,
            "user": {
                "id": user["id"],
                "uuid": user["uuid"],
                "username": user["username"],
                "display_name": user["display_name"],
                "avatar_url": user.get("avatar_url", ""),
                "permissions": permissions,
            },
        })
    except ServiceError as e:
        return _as_error(e)


@auth_bp.route("/register", methods=["POST"])
@tag(["认证"])
async def register():
    # ── 限流：同一 IP 每分钟最多 3 次注册请求 ──
    from quart import current_app
    from utils.rate_limit import check_rate_limit
    try:
        await check_rate_limit(
            db=current_app.services.db,
            key_prefix="ratelimit:register",
            identifier=request.remote_addr or "unknown",
            max_requests=3,
            window_seconds=60,
        )
    except TooManyRequestsError as e:
        return jsonify({"error": e.message, "code": e.code}), e.status_code

    try:
        body = await request.get_json()
        data = UserCreate(**body)
    except ValidationError as e:
        return jsonify({"error": "请求格式错误", "code": "VALIDATION_ERROR", "details": e.errors()}), 400
    except Exception as e:
        return jsonify({"error": f"请求格式错误: {e}"}), 400

    svc = _get_auth_service()
    try:
        user = await svc.create_user(data, created_by=0)
        return jsonify({
            "uuid": user.uuid,
            "username": user.username,
            "display_name": user.display_name,
            "message": "注册成功",
        }), 201
    except ServiceError as e:
        return _as_error(e)


@auth_bp.route("/me", methods=["GET"])
@tag(["认证"])
async def me():
    user_id = await get_current_user()
    if not user_id:
        return jsonify({"error": "未登录或登录已过期", "code": "UNAUTHORIZED"}), 401

    svc = _get_auth_service()
    try:
        user = await svc.get_user(user_id)
    except ServiceError as e:
        return _as_error(e)

    permissions = await svc.get_user_permissions(user_id)
    role = "admin" if permissions else "user"

    return jsonify({
        "uuid": user.uuid,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url or "",
        "role": role,
        "permissions": permissions,
    })


@auth_bp.route("/me", methods=["PATCH"])
@tag(["认证"])
async def update_me():
    """
    登录用户修改自己的个人信息（display_name / avatar_url）。

    权限要求：登录即可访问，不需要额外权限。

    请求体：{ "display_name": "新昵称", "avatar_url": "新头像URL" }
    仅更新传入的字段，未传入的字段保持不变。
    """
    from models.user import UserUpdate

    user_id = await get_current_user()
    if not user_id:
        return jsonify({"error": "未登录或登录已过期", "code": "UNAUTHORIZED"}), 401

    try:
        body = await request.get_json()
        data = UserUpdate(
            display_name=body.get("display_name"),
            avatar_url=body.get("avatar_url"),
        )
    except Exception as e:
        return jsonify({"error": f"请求格式错误: {e}"}), 400

    if data.display_name is not None and (len(data.display_name) < 1 or len(data.display_name) > 64):
        return jsonify({"error": "昵称长度必须在1-64位之间"}), 400

    svc = _get_auth_service()
    try:
        user = await svc.update_user(user_id, data)
    except ServiceError as e:
        return _as_error(e)

    permissions = await svc.get_user_permissions(user_id)
    role = "admin" if permissions else "user"

    return jsonify({
        "success": True,
        "message": "更新成功",
        "data": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url or "",
            "is_active": user.is_active,
            "permissions": permissions,
        },
    })
