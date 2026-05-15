"""
services/auth_service.py

认证授权业务层。

职责：
    1. create_user      — 创建用户（bcrypt 加密密码）
    2. authenticate     — 用户名+密码校验
    3. create_token     — JWT 签发
    4. verify_token     — JWT 校验，返回 user_id
    5. check_permission — 校验 user_id 是否拥有指定权限
    6. 用户 CRUD         — list_users / get_user / update_user / delete_user
    7. 权限管理          — grant_permissions / revoke_permission / get_user_permissions

错误处理：
    所有失败路径抛出 ServiceError 子类，路由层统一捕获。
    不再 return None / False / raise ValueError。

依赖：
    DatabaseLayerV2 — 注入，读写 MySQL users / permissions / user_permissions
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

import bcrypt
import jwt

from db.database_v2 import DatabaseLayerV2
from config.settings import settings
from models.user import UserCreate, UserUpdate, UserRead, UserLogin
from models.permission import PermissionRead
from models.user_permission import UserPermissionAssign, UserPermissionRead
from utils.errors import (
    DuplicateError, NotFoundError, AuthenticationError, UserDisabledError,
)
from utils.serializers import CST
from utils.snowflake import generate_id

logger = logging.getLogger(__name__)


class AuthService:
    """
    认证授权业务层。

    输入：DatabaseLayerV2 实例（依赖注入）
    副作用：读写 MySQL users / user_permissions
    """

    def __init__(self, db: DatabaseLayerV2):
        self.db = db

    # ═══════════════════════════════════════
    # 用户 CRUD
    # ═══════════════════════════════════════

    async def create_user(self, data: UserCreate, created_by: int = 0) -> UserRead:
        """
        创建用户（bcrypt 加密密码）。

        输入：
            data:       UserCreate（username / password / display_name）
            created_by: 操作的管理员 ID
        输出：UserRead
        副作用：INSERT INTO users
        异常：DuplicateError — username 已存在
        """
        existing = await self.db.find_one("users", {"username": data.username})
        if existing:
            raise DuplicateError("用户名", data.username)

        password_hash = bcrypt.hashpw(
            data.password.encode("utf-8"),
            bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS),
        ).decode("utf-8")

        display_name = data.display_name or data.username
        user_uuid = generate_id()

        user_id = await self.db.insert("users", {
            "uuid": user_uuid,
            "username": data.username,
            "password_hash": password_hash,
            "display_name": display_name,
            "avatar_url": settings.DEFAULT_AVATAR_URL,
        })
        logger.info(f"用户已创建: id={user_id} uuid={user_uuid} username='{data.username}'")
        return await self.get_user(user_id)

    async def get_user(self, user_id: int) -> UserRead:
        """
        输入：user_id
        输出：UserRead
        异常：NotFoundError — 用户不存在
        """
        row = await self.db.find_one("users", {"id": user_id})
        if not row:
            raise NotFoundError("用户", user_id)
        return UserRead(**row)

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        输入：username
        输出：raw dict 或 None（含 password_hash，仅内部使用）
        """
        return await self.db.find_one("users", {"username": username})

    async def list_users(self) -> List[UserRead]:
        """列出所有用户（空列表 = 无用户）。"""
        rows = await self.db.execute_raw("SELECT * FROM users")
        return [UserRead(**r) for r in rows]

    async def update_user(self, user_id: int, data: UserUpdate) -> UserRead:
        """
        更新用户（display_name / is_active / avatar_url）。

        输入：user_id, UserUpdate
        输出：更新后的 UserRead
        异常：NotFoundError — 用户不存在
        """
        values = {}
        if data.display_name is not None:
            values["display_name"] = data.display_name
        if data.is_active is not None:
            values["is_active"] = 1 if data.is_active else 0
        if data.avatar_url is not None:
            values["avatar_url"] = data.avatar_url
        if not values:
            return await self.get_user(user_id)  # 无变更，先查再返回（不存在会抛异常）

        await self.db.update("users", {"id": user_id}, values)
        return await self.get_user(user_id)

    async def delete_user(self, user_id: int) -> bool:
        """
        删除用户。

        输入：user_id
        输出：True=已删除
        异常：NotFoundError — 用户不存在
        副作用：DELETE FROM users（CASCADE 删除 user_permissions）
        """
        await self.get_user(user_id)  # 不存在则抛异常
        await self.db.execute_raw("DELETE FROM users WHERE id = %s", (user_id,))
        logger.info(f"用户已删除: id={user_id}")
        return True

    # ═══════════════════════════════════════
    # 认证
    # ═══════════════════════════════════════

    async def authenticate(self, data: UserLogin) -> Dict[str, Any]:
        """
        校验用户名和密码。

        输入：UserLogin
        输出：user raw dict（含 id, username, is_active 等）
        异常：AuthenticationError — 用户不存在或密码错误
              UserDisabledError   — 账户已被禁用
        """
        row = await self.get_user_by_username(data.username)
        if not row:
            logger.warning(f"登录失败: 用户名 '{data.username}' 不存在")
            raise AuthenticationError()

        if not row.get("is_active"):
            logger.warning(f"登录失败: 用户 '{data.username}' 已被禁用")
            raise UserDisabledError()

        ok = bcrypt.checkpw(
            data.password.encode("utf-8"),
            row["password_hash"].encode("utf-8"),
        )
        if not ok:
            logger.warning(f"登录失败: 用户 '{data.username}' 密码错误")
            raise AuthenticationError()
        return row

    def create_token(self, user_id: int) -> str:
        """
        签发 JWT token。

        输入：user_id
        输出：JWT 字符串
        """
        now = datetime.now(CST)
        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(seconds=settings.JWT_EXPIRE_SECONDS),
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    def verify_token(self, token: str) -> Optional[int]:
        """
        校验 JWT 并提取 user_id。

        输入：JWT 字符串
        输出：user_id 或 None（过期 / 签名无效 / 其他错误）
        """
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            return int(payload["sub"])
        except jwt.ExpiredSignatureError:
            return None
        except (jwt.InvalidTokenError, KeyError, ValueError):
            return None

    # ═══════════════════════════════════════
    # 权限
    # ═══════════════════════════════════════

    async def _has_permission(self, user_id: int, permission_code: str) -> bool:
        """纯数据库查询：用户是否拥有指定权限码。"""
        row = await self.db.find_one("user_permissions", {
            "user_id": user_id,
            "permission_code": permission_code,
        })
        return row is not None

    async def check_permission(self, user_id: int, permission_code: str) -> bool:
        """
        检查用户是否拥有指定权限。

        system:monitor 作为超级监控权限，自动涵盖所有 infra:* 子权限：
            infra:proxy:read / infra:proxy:manage
            infra:cookie:read / infra:cookie:manage
            infra:sensitive:read

        输入：user_id, permission_code（如 "crawler:manage"）
        输出：True=有权限, False=无
        """
        # system:monitor 持有者自动获得所有 infra:* 权限
        if permission_code.startswith("infra:"):
            if await self._has_permission(user_id, "system:monitor"):
                return True

        return await self._has_permission(user_id, permission_code)

    async def check_permissions(self, user_id: int, codes: List[str]) -> Dict[str, bool]:
        """
        批量检查多个权限 — 一次 SELECT IN 替代 N 次 check_permission。

        同样遵守 system:monitor → infra:* 的自动涵盖规则。

        输入：user_id, [permission_code, ...]
        输出：{code: True/False, ...}
        """
        if not codes:
            return {}

        # system:monitor 持有者对 infra:* 自动通过
        has_monitor = None
        infra_codes = [c for c in codes if c.startswith("infra:")]
        if infra_codes:
            has_monitor = await self._has_permission(user_id, "system:monitor")

        placeholders = ", ".join(["%s"] * len(codes))
        rows = await self.db.execute_raw(
            f"SELECT permission_code FROM user_permissions "
            f"WHERE user_id = %s AND permission_code IN ({placeholders})",
            (user_id, *codes),
        )
        existing = {r["permission_code"] for r in rows}

        return {
            code: True if (code in existing) else (
                True if (code.startswith("infra:") and has_monitor) else False
            )
            for code in codes
        }

    # ═══════════════════════════════════════
    # 权限管理（需 user:manage）
    # ═══════════════════════════════════════

    async def list_permissions(self) -> List[PermissionRead]:
        """列出所有可用权限。"""
        rows = await self.db.execute_raw("SELECT * FROM permissions")
        return [PermissionRead(**r) for r in rows]

    async def get_user_permissions(self, user_id: int) -> List[str]:
        """
        输入：user_id
        输出：该用户拥有的权限编码列表
        """
        rows = await self.db.execute_raw(
            "SELECT permission_code FROM user_permissions WHERE user_id = %s",
            (user_id,),
        )
        return [r["permission_code"] for r in rows]

    async def grant_permissions(self, data: UserPermissionAssign) -> int:
        """
        为用户分配权限（幂等 — 已存在的跳过）。

        优化：一次 SELECT IN 批量查询已有权限 → 只 INSERT 缺失的，
        而非逐条 find_one + insert (N+1 反模式)。

        输入：UserPermissionAssign
        输出：成功分配的条数
        """
        if not data.permission_codes:
            return 0

        # 批量查询已有权限 — 1 次 DB 往返替代 N 次 find_one
        placeholders = ", ".join(["%s"] * len(data.permission_codes))
        existing_rows = await self.db.execute_raw(
            f"SELECT permission_code FROM user_permissions "
            f"WHERE user_id = %s AND permission_code IN ({placeholders})",
            (data.user_id, *data.permission_codes),
        )
        existing_set = {r["permission_code"] for r in existing_rows}

        count = 0
        for code in data.permission_codes:
            if code in existing_set:
                continue
            await self.db.insert("user_permissions", {
                "user_id": data.user_id,
                "permission_code": code,
                "granted_by": data.granted_by,
            }, return_id=False)
            count += 1

        logger.info(
            f"权限分配完成: user_id={data.user_id} "
            f"granted={count}/{len(data.permission_codes)} by={data.granted_by}"
        )
        return count

    async def set_permissions(self, data: UserPermissionAssign) -> int:
        """
        全量替换用户权限 — 先清空再写入（原子事务），permission_codes=[] 即清空所有权限。

        输入：UserPermissionAssign（permission_codes 可为空列表）
        输出：成功写入的条数
        副作用：DELETE + INSERT 在同一事务中执行
        """
        async with self.db.transaction() as tx:
            await tx.delete("user_permissions", {"user_id": data.user_id})
            count = 0
            for code in data.permission_codes:
                await tx.insert("user_permissions", {
                    "user_id": data.user_id,
                    "permission_code": code,
                    "granted_by": data.granted_by,
                }, return_id=False)
                count += 1

        logger.info(
            f"权限替换完成: user_id={data.user_id} "
            f"set={count} by={data.granted_by}"
        )
        return count

    async def revoke_permission(self, user_id: int, permission_code: str) -> bool:
        """
        撤销单条权限。

        输入：user_id, permission_code
        输出：True
        """
        await self.db.execute_raw(
            "DELETE FROM user_permissions WHERE user_id = %s AND permission_code = %s",
            (user_id, permission_code),
        )
        return True


# ═══════════════════════════════════════
# 模块级单例
# ═══════════════════════════════════════

_auth_service: AuthService = None


def _get_auth_service() -> AuthService:
    if _auth_service is None:
        raise RuntimeError("AuthService 未初始化，请先调用 init_auth_service()")
    return _auth_service


def init_auth_service(db) -> AuthService:
    global _auth_service
    _auth_service = AuthService(db)
    logger.info("AuthService 已初始化")
    return _auth_service
