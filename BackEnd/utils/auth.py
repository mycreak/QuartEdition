"""
utils/auth.py

认证装饰器 — 替代旧的 X-Admin-Id 请求头机制。

使用方式：
    from utils.auth import require_permission, get_current_user

    @require_permission("crawler:manage")
    async def claim_failure(failure_id: int):
        ...

鉴权流程：
    1. 从 Authorization: Bearer <token> 提取 JWT
    2. verify_token → user_id
    3. 查 users.is_active → 确保未被禁用
    4. check_permission(user_id, code) → True/False
    5. 失败返回 401（未登录/已禁用）或 403（无权限）
"""

import asyncio
import logging
from functools import wraps

from quart import request, jsonify, g

logger = logging.getLogger(__name__)


def _get_auth_service():
    """延迟导入 AuthService 单例（避免循环依赖）。"""
    from services.auth_service import _get_auth_service as getter
    return getter()


async def get_current_user() -> int:
    """
    从当前请求提取 user_id。

    输出：user_id 或 0（未登录）
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        logger.debug("get_current_user: 无 Authorization header 或格式不正确")
        return 0

    token = header[7:]
    svc = _get_auth_service()
    user_id = svc.verify_token(token)
    if user_id is None:
        logger.debug("get_current_user: JWT 校验失败（过期/签名无效）")
        return 0

    # 校验用户未被禁用；用户不存在（已删除）也视为未登录
    try:
        user = await svc.get_user(user_id)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"get_current_user: 查询用户 {user_id} 失败: {e}")
        return 0

    if not user.is_active:
        logger.debug(f"get_current_user: 用户 {user_id} 已被禁用")
        return 0

    return user_id


def require_permission(permission_code: str):
    """
    装饰器：要求当前请求拥有指定权限。

    g.user_id 通过 Quart 的 g 对象传递 — g 是请求级别的 ContextVar，
    天然请求隔离，不存在跨请求污染。调用方用 `user_id = g.user_id` 提取。

    输入：permission_code — 权限编码（如 "crawler:manage"）
    输出：无（修饰后的 handler）
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user_id = await get_current_user()
            if not user_id:
                return jsonify({"error": "未登录或登录已过期"}), 401

            svc = _get_auth_service()
            if not await svc.check_permission(user_id, permission_code):
                return jsonify({"error": f"无权限: {permission_code}"}), 403

            g.user_id = user_id
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_login(func):
    """
    装饰器：要求当前请求已登录（JWT 有效 + 未禁用）。

    g.user_id 通过 Quart 的 g 对象传递 — 请求级别 ContextVar，天然隔离。

    与 require_permission 的区别：
        require_login       → 只校验登录状态，不校验权限
        require_permission  → 校验登录状态 + 指定权限

    输入：被装饰的 async handler
    输出：修饰后的 handler（未登录 → 401）
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        user_id = await get_current_user()
        if not user_id:
            return jsonify({"error": "未登录或登录已过期"}), 401
        g.user_id = user_id
        return await func(*args, **kwargs)
    return wrapper
