"""
routes/admin/user_routes.py

用户管理。

端点：
    GET  /admin/users                       — 用户列表
    POST /admin/users                       — 创建用户
    PATCH /admin/users/<id>                — 更新用户（is_active / display_name）
    POST /admin/users/<id>/permissions      — 分配权限（空数组=清空）
"""

import logging

from quart import Blueprint, request, jsonify, g
from quart_schema import tag
from utils.auth import require_permission
from utils.errors import ServiceError

logger = logging.getLogger(__name__)

user_bp = Blueprint("user_routes", __name__)


def _as_error(e: ServiceError):
    return jsonify({"error": e.message, "code": e.code}), e.status_code


@user_bp.route("/users", methods=["GET"])
@require_permission("user:manage")
@tag(["用户管理"])
async def list_users():
    from services.auth_service import _get_auth_service
    svc = _get_auth_service()
    users = [u.model_dump() for u in await svc.list_users()]

    # 用 LEFT JOIN + GROUP_CONCAT 一次性聚合权限，避免 page_size=99999 伪分页
    rows = await svc.db.execute_raw(
        "SELECT up.user_id, GROUP_CONCAT(up.permission_code) AS codes "
        "FROM user_permissions up "
        "WHERE up.user_id IN (SELECT id FROM users) "
        "GROUP BY up.user_id"
    )
    perms_by_user: dict[int, list[str]] = {}
    for p in rows:
        uid = p.get("user_id")
        codes = (p.get("codes") or "").split(",") if p.get("codes") else []
        perms_by_user.setdefault(uid, []).extend(codes)

    # 为每个用户注入 permissions 列表和 role 推导
    for u in users:
        perms = perms_by_user.get(u["id"], [])
        u["permissions"] = perms
        u["role"] = "admin" if perms else "user"

    return jsonify({"items": users})


@user_bp.route("/users", methods=["POST"])
@require_permission("user:manage")
@tag(["用户管理"])
async def create_user():
    from services.auth_service import _get_auth_service
    from models.user import UserCreate

    try:
        body = await request.get_json()
        data = UserCreate(**body)
    except Exception as e:
        return jsonify({"error": f"请求格式错误: {e}"}), 400

    svc = _get_auth_service()
    try:
        user = await svc.create_user(data, created_by=g.user_id)
        return jsonify(user.model_dump()), 201
    except ServiceError as e:
        return _as_error(e)


@user_bp.route("/users/<int:user_id>/permissions", methods=["POST"])
@require_permission("user:manage")
@tag(["用户管理"])
async def assign_permissions(user_id: int):
    """
    全量替换用户权限 — 先清空再写入。

    前端传 permission_codes=[] 即清空所有权限。
    """
    from services.auth_service import _get_auth_service
    from models.user_permission import UserPermissionAssign

    try:
        body = await request.get_json()
        codes = body.get("permission_codes", [])
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    svc = _get_auth_service()
    try:
        data = UserPermissionAssign(
            user_id=user_id,
            permission_codes=codes,
            granted_by=g.user_id,
        )
    except Exception as e:
        return jsonify({"error": f"参数校验失败: {e}"}), 400

    count = await svc.set_permissions(data)
    return jsonify({"set": count, "total": len(codes)})


@user_bp.route("/users/<int:user_id>/permissions/<permission_code>", methods=["DELETE"])
@require_permission("user:manage")
@tag(["用户管理"])
async def revoke_permission(user_id: int, permission_code: str):
    """
    撤销单条权限。

    路径参数:
        user_id:         目标用户 ID
        permission_code: 要撤销的权限编码（如 "movie:read"）

    返回:
        200 — 撤销成功
        400 — 无效的权限编码
        404 — 用户不存在
    """
    from services.auth_service import _get_auth_service
    from models.user_permission import VALID_PERMISSION_CODES

    if permission_code not in VALID_PERMISSION_CODES:
        return jsonify({"error": f"无效的权限编码: {permission_code}"}), 400

    svc = _get_auth_service()
    try:
        user = await svc.get_user(user_id)
        if not user.is_active:
            return jsonify({"error": "用户已被禁用", "code": "USER_DISABLED"}), 400
    except ServiceError as e:
        return _as_error(e)

    await svc.revoke_permission(user_id, permission_code)
    logger.info(f"权限已撤销: user_id={user_id} permission={permission_code} by={g.user_id}")
    return jsonify({"success": True, "message": f"权限 {permission_code} 已收回"})


@user_bp.route("/users/<int:user_id>", methods=["PATCH"])
@require_permission("user:manage")
@tag(["用户管理"])
async def update_user(user_id: int):
    """
    更新用户 — display_name / is_active。

    请求体: {"display_name": "新昵称", "is_active": false}
    仅更新传入的字段，未传入的字段保持不变。
    """
    from services.auth_service import _get_auth_service
    from models.user import UserUpdate
    from utils.errors import ServiceError

    try:
        body = await request.get_json()
        data = UserUpdate(
            is_active=body.get("is_active"),
            display_name=body.get("display_name"),
            avatar_url=body.get("avatar_url"),
        )
    except Exception as e:
        return jsonify({"error": f"请求格式错误: {e}"}), 400

    # 禁止自己禁用自己
    if data.is_active is False and user_id == g.user_id:
        return jsonify({"error": "不能禁用自己的账号", "code": "SELF_DISABLE_FORBIDDEN"}), 422

    svc = _get_auth_service()
    try:
        user = await svc.update_user(user_id, data)
        return jsonify(user.model_dump())
    except ServiceError as e:
        return _as_error(e)
