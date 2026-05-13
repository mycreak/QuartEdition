"""
AuthService 集成测试
"""

import pytest
import asyncio
import time
import random
from datetime import datetime, timedelta
from typing import Dict, Any

from db.database_v2 import DatabaseLayerV2
from services.auth_service import AuthService
from models.user import UserCreate, UserUpdate, UserLogin, UserRead
from models.user_permission import UserPermissionAssign
from utils.errors import (
    DuplicateError, NotFoundError, AuthenticationError, UserDisabledError,
)


# ==================== 测试辅助函数 ====================

# 合法的权限编码
VALID_PERMS = [
    "user:manage",
    "crawler:task:read",
    "crawler:task:write",
    "crawler:failure:manage",
    "movie:manage",
    "movie:read",
    "comment:read",
    "comment:manage",
    "system:monitor",
]

# 全局管理员用户 ID
admin_user_id: int | None = None

def create_test_user_data(
    username: str = "testuser01",
    password: str = "Test123",
    display_name: str = "",
) -> UserCreate:
    """创建测试用户数据"""
    return UserCreate(
        username=username,
        password=password,
        display_name=display_name,
    )


def create_test_user_login(
    username: str = "testuser01",
    password: str = "Test123",
) -> UserLogin:
    """创建测试登录数据"""
    return UserLogin(username=username, password=password)


async def create_test_user(auth_service: AuthService, username_prefix: str = "testuser01") -> UserRead:
    """创建并返回测试用户，使用随机后缀避免重复"""
    timestamp = str(int(time.time() * 1000))
    random_suffix = str(random.randint(1000, 9999))
    username = f"{username_prefix}_{timestamp}_{random_suffix}"
    
    # 确保用户名长度不超过限制
    if len(username) > 32:
        username = f"user_{timestamp}_{random_suffix}"
        
    user_data = create_test_user_data(username=username)
    return await auth_service.create_user(user_data)


async def get_admin_user_id(auth_service: AuthService) -> int:
    """获取或创建一个管理员用户"""
    global admin_user_id
    if admin_user_id is None:
        try:
            admin = await create_test_user(auth_service, "adminuser01")
            admin_user_id = admin.id
        except:
            # 用户可能已存在
            admin = await auth_service.get_user_by_username("adminuser01")
            admin_user_id = admin["id"]
    return admin_user_id


# ==================== SC-Auth-01 用户创建 ====================

@pytest.mark.integration
@pytest.mark.services
class TestAuthServiceCreateUser:
    """用户创建测试"""

    async def test_create_user_success(self, db: DatabaseLayerV2):
        """TC-Auth-01-01: 正常创建用户"""
        auth_service = AuthService(db)
        
        timestamp = str(int(time.time() * 1000))
        random_suffix = str(random.randint(1000, 9999))
        username = f"newuser_{timestamp}_{random_suffix}"
        
        user_data = create_test_user_data(username=username, display_name="新用户")
        user = await auth_service.create_user(user_data)
        
        assert user is not None
        assert user.id is not None
        assert user.uuid is not None
        assert user.username == username
        assert user.display_name == "新用户"
        assert user.is_active is True

    async def test_create_user_duplicate_username(self, db: DatabaseLayerV2):
        """TC-Auth-01-02: 重复用户名"""
        auth_service = AuthService(db)
        
        timestamp = str(int(time.time() * 1000))
        random_suffix = str(random.randint(1000, 9999))
        username = f"dupuser_{timestamp}_{random_suffix}"
        
        # 先创建用户
        user_data = create_test_user_data(username=username)
        await auth_service.create_user(user_data)
        
        # 再尝试创建同名用户
        with pytest.raises(DuplicateError):
            await auth_service.create_user(user_data)

    async def test_create_user_empty_display_name(self, db: DatabaseLayerV2):
        """TC-Auth-01-03: 创建时 display_name 为空"""
        auth_service = AuthService(db)
        
        timestamp = str(int(time.time() * 1000))
        random_suffix = str(random.randint(1000, 9999))
        username = f"emptydisplay_{timestamp}_{random_suffix}"
        
        user_data = create_test_user_data(username=username, display_name="")
        user = await auth_service.create_user(user_data)
        
        assert user.display_name == username


# ==================== SC-Auth-02 用户查询 ====================

@pytest.mark.integration
@pytest.mark.services
class TestAuthServiceQueryUser:
    """用户查询测试"""

    async def test_get_user_exists(self, db: DatabaseLayerV2):
        """TC-Auth-02-01: get_user 存在的用户"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "getuser")
        
        user = await auth_service.get_user(created_user.id)
        assert user is not None
        assert user.id == created_user.id
        assert user.username == created_user.username

    async def test_get_user_not_exists(self, db: DatabaseLayerV2):
        """TC-Auth-02-02: get_user 不存在的用户"""
        auth_service = AuthService(db)
        
        with pytest.raises(NotFoundError):
            await auth_service.get_user(999999)

    async def test_list_users_has_users(self, db: DatabaseLayerV2):
        """TC-Auth-02-03: list_users 有用户"""
        auth_service = AuthService(db)
        user1 = await create_test_user(auth_service, "listuser")
        user2 = await create_test_user(auth_service, "listuser")
        
        users = await auth_service.list_users()
        assert len(users) >= 2
        usernames = [u.username for u in users]
        assert user1.username in usernames
        assert user2.username in usernames

    async def test_list_users_no_users(self, db: DatabaseLayerV2):
        """TC-Auth-02-04: list_users 无用户"""
        # 先清理测试数据
        await db.execute_raw("DELETE FROM users WHERE username LIKE 'nouser%'")
        
        auth_service = AuthService(db)
        users = await auth_service.list_users()
        assert isinstance(users, list)

    async def test_get_user_by_username_exists(self, db: DatabaseLayerV2):
        """TC-Auth-02-05: get_user_by_username 存在的用户"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "byusername")
        
        user_dict = await auth_service.get_user_by_username(created_user.username)
        assert user_dict is not None
        assert user_dict["username"] == created_user.username
        assert "password_hash" in user_dict

    async def test_get_user_by_username_not_exists(self, db: DatabaseLayerV2):
        """TC-Auth-02-06: get_user_by_username 不存在的用户"""
        auth_service = AuthService(db)
        
        user_dict = await auth_service.get_user_by_username("notexistsuser000")
        assert user_dict is None


# ==================== SC-Auth-03 用户更新 ====================

@pytest.mark.integration
@pytest.mark.services
class TestAuthServiceUpdateUser:
    """用户更新测试"""

    async def test_update_display_name(self, db: DatabaseLayerV2):
        """TC-Auth-03-01: 更新 display_name"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "updatedisplay001")
        
        update_data = UserUpdate(display_name="新的显示名")
        updated_user = await auth_service.update_user(created_user.id, update_data)
        
        assert updated_user.display_name == "新的显示名"

    async def test_update_is_active(self, db: DatabaseLayerV2):
        """TC-Auth-03-02: 更新 is_active"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "updateactive001")
        assert created_user.is_active is True
        
        update_data = UserUpdate(is_active=False)
        updated_user = await auth_service.update_user(created_user.id, update_data)
        
        assert updated_user.is_active is False

    async def test_update_multiple_fields(self, db: DatabaseLayerV2):
        """TC-Auth-03-03: 同时更新多个字段"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "updatemulti001")
        
        update_data = UserUpdate(display_name="综合更新", is_active=False)
        updated_user = await auth_service.update_user(created_user.id, update_data)
        
        assert updated_user.display_name == "综合更新"
        assert updated_user.is_active is False

    async def test_update_no_fields(self, db: DatabaseLayerV2):
        """TC-Auth-03-04: 无更新字段"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "updatenone001")
        
        update_data = UserUpdate()
        updated_user = await auth_service.update_user(created_user.id, update_data)
        
        assert updated_user.display_name == created_user.display_name
        assert updated_user.is_active == created_user.is_active

    async def test_update_not_exists(self, db: DatabaseLayerV2):
        """TC-Auth-03-05: 更新不存在的用户"""
        auth_service = AuthService(db)
        
        update_data = UserUpdate(display_name="不存在用户")
        with pytest.raises(NotFoundError):
            await auth_service.update_user(999999, update_data)


# ==================== SC-Auth-04 用户删除 ====================

@pytest.mark.integration
@pytest.mark.services
class TestAuthServiceDeleteUser:
    """用户删除测试"""

    async def test_delete_user_exists(self, db: DatabaseLayerV2):
        """TC-Auth-04-01: 删除存在的用户"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "deleteuser001")
        
        result = await auth_service.delete_user(created_user.id)
        assert result is True
        
        # 验证用户已删除
        with pytest.raises(NotFoundError):
            await auth_service.get_user(created_user.id)

    async def test_delete_user_not_exists(self, db: DatabaseLayerV2):
        """TC-Auth-04-02: 删除不存在的用户"""
        auth_service = AuthService(db)
        
        with pytest.raises(NotFoundError):
            await auth_service.delete_user(999999)


# ==================== SC-Auth-05 认证登录 ====================

@pytest.mark.integration
@pytest.mark.services
class TestAuthServiceAuthenticate:
    """认证登录测试"""

    async def test_authenticate_success(self, db: DatabaseLayerV2):
        """TC-Auth-05-01: 正确用户名和密码"""
        auth_service = AuthService(db)
        timestamp = str(int(time.time() * 1000))
        random_suffix = str(random.randint(1000, 9999))
        username = f"loginsuccess_{timestamp}_{random_suffix}"
        password = "Test123"
        
        # 创建用户
        user_data = create_test_user_data(username=username, password=password)
        await auth_service.create_user(user_data)
        
        # 登录
        login_data = create_test_user_login(username=username, password=password)
        user_dict = await auth_service.authenticate(login_data)
        
        assert user_dict is not None
        assert user_dict["username"] == username
        assert "password_hash" in user_dict

    async def test_authenticate_wrong_password(self, db: DatabaseLayerV2):
        """TC-Auth-05-02: 错误密码"""
        auth_service = AuthService(db)
        timestamp = str(int(time.time() * 1000))
        random_suffix = str(random.randint(1000, 9999))
        username = f"wrongpass_{timestamp}_{random_suffix}"
        
        # 创建用户
        user_data = create_test_user_data(username=username)
        await auth_service.create_user(user_data)
        
        # 登录（错误密码）
        login_data = create_test_user_login(username=username, password="WrongPass1")
        with pytest.raises(AuthenticationError):
            await auth_service.authenticate(login_data)

    async def test_authenticate_user_not_exists(self, db: DatabaseLayerV2):
        """TC-Auth-05-03: 用户不存在"""
        auth_service = AuthService(db)
        
        login_data = create_test_user_login(username="notexists000", password="Test123")
        with pytest.raises(AuthenticationError):
            await auth_service.authenticate(login_data)

    async def test_authenticate_user_disabled(self, db: DatabaseLayerV2):
        """TC-Auth-05-04: 用户已禁用"""
        auth_service = AuthService(db)
        
        # 创建并禁用用户
        created_user = await create_test_user(auth_service, "disableduser")
        await auth_service.update_user(created_user.id, UserUpdate(is_active=False))
        
        # 尝试登录
        login_data = create_test_user_login(username=created_user.username, password="Test123")
        with pytest.raises(UserDisabledError):
            await auth_service.authenticate(login_data)


# ==================== SC-Auth-06 JWT 令牌 ====================

@pytest.mark.integration
@pytest.mark.services
class TestAuthServiceJWT:
    """JWT 令牌测试"""

    async def test_create_token(self, db: DatabaseLayerV2):
        """TC-Auth-06-01: create_token 有效用户"""
        auth_service = AuthService(db)
        token = auth_service.create_token(12345)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    async def test_verify_token_valid(self, db: DatabaseLayerV2):
        """TC-Auth-06-02: verify_token 有效 token"""
        auth_service = AuthService(db)
        user_id = 54321
        token = auth_service.create_token(user_id)
        
        verified_user_id = auth_service.verify_token(token)
        assert verified_user_id == user_id

    async def test_verify_token_expired(self, db: DatabaseLayerV2):
        """TC-Auth-06-03: verify_token 过期 token"""
        auth_service = AuthService(db)
        
        # 创建一个过去的 token
        from config.settings import settings
        import jwt
        from datetime import datetime, timedelta
        from utils.serializers import CST
        
        now = datetime.now(CST)
        expired_payload = {
            "sub": "99999",
            "iat": now - timedelta(seconds=settings.JWT_EXPIRE_SECONDS + 10),
            "exp": now - timedelta(seconds=10),
        }
        expired_token = jwt.encode(expired_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        
        verified_user_id = auth_service.verify_token(expired_token)
        assert verified_user_id is None

    async def test_verify_token_invalid(self, db: DatabaseLayerV2):
        """TC-Auth-06-04: verify_token 无效 token"""
        auth_service = AuthService(db)
        
        invalid_token = "invalid.token.string"
        verified_user_id = auth_service.verify_token(invalid_token)
        assert verified_user_id is None


# ==================== SC-Auth-07 权限检查 ====================

@pytest.mark.integration
@pytest.mark.services
class TestAuthServicePermissionCheck:
    """权限检查测试"""

    async def test_check_permission_has(self, db: DatabaseLayerV2):
        """TC-Auth-07-01: check_permission 有权限"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permcheck001")
        admin_id = await get_admin_user_id(auth_service)
        
        # 先授予权限
        await db.insert("user_permissions", {
            "user_id": created_user.id,
            "permission_code": "crawler:task:read",
            "granted_by": admin_id,
        }, return_id=False)
        
        has_perm = await auth_service.check_permission(created_user.id, "crawler:task:read")
        assert has_perm is True

    async def test_check_permission_no(self, db: DatabaseLayerV2):
        """TC-Auth-07-02: check_permission 无权限"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permcheck002")
        
        has_perm = await auth_service.check_permission(created_user.id, "crawler:task:read")
        assert has_perm is False

    async def test_check_permissions_batch(self, db: DatabaseLayerV2):
        """TC-Auth-07-03: check_permissions 批量检查"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permcheck003")
        admin_id = await get_admin_user_id(auth_service)
        
        # 授予部分权限
        await db.insert("user_permissions", {
            "user_id": created_user.id,
            "permission_code": "crawler:task:read",
            "granted_by": admin_id,
        }, return_id=False)
        await db.insert("user_permissions", {
            "user_id": created_user.id,
            "permission_code": "movie:read",
            "granted_by": admin_id,
        }, return_id=False)
        
        # 批量检查
        perm_dict = await auth_service.check_permissions(
            created_user.id,
            ["crawler:task:read", "movie:read", "user:manage", "comment:manage"]
        )
        
        assert perm_dict["crawler:task:read"] is True
        assert perm_dict["movie:read"] is True
        assert perm_dict["user:manage"] is False
        assert perm_dict["comment:manage"] is False

    async def test_check_permissions_empty(self, db: DatabaseLayerV2):
        """TC-Auth-07-04: check_permissions 空列表"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permcheck004")
        
        perm_dict = await auth_service.check_permissions(created_user.id, [])
        assert perm_dict == {}


# ==================== SC-Auth-08 权限管理 ====================

@pytest.mark.integration
@pytest.mark.services
class TestAuthServicePermissionManage:
    """权限管理测试"""

    async def test_list_permissions(self, db: DatabaseLayerV2):
        """TC-Auth-08-01: list_permissions"""
        auth_service = AuthService(db)
        
        # 先确保有一些权限（使用合法编码）
        await db.execute_raw("""
            INSERT IGNORE INTO permissions (code, name, description) 
            VALUES ('crawler:task:read', '爬虫任务读取', '读取爬虫任务'),
                   ('user:manage', '用户管理', '管理用户账户'),
                   ('system:monitor', '系统监控', '监控系统状态')
        """)
        
        permissions = await auth_service.list_permissions()
        assert isinstance(permissions, list)
        assert len(permissions) > 0

    async def test_grant_permissions_single(self, db: DatabaseLayerV2):
        """TC-Auth-08-02: grant_permissions 单权限"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permgrant001")
        admin_id = await get_admin_user_id(auth_service)
        
        assign_data = UserPermissionAssign(
            user_id=created_user.id,
            permission_codes=["crawler:task:read"],
            granted_by=admin_id,
        )
        
        count = await auth_service.grant_permissions(assign_data)
        assert count == 1
        
        # 验证权限已授予
        perms = await auth_service.get_user_permissions(created_user.id)
        assert "crawler:task:read" in perms

    async def test_grant_permissions_multiple(self, db: DatabaseLayerV2):
        """TC-Auth-08-03: grant_permissions 多权限"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permgrant002")
        admin_id = await get_admin_user_id(auth_service)
        
        assign_data = UserPermissionAssign(
            user_id=created_user.id,
            permission_codes=["crawler:task:read", "movie:read", "comment:read"],
            granted_by=admin_id,
        )
        
        count = await auth_service.grant_permissions(assign_data)
        assert count == 3
        
        perms = await auth_service.get_user_permissions(created_user.id)
        assert "crawler:task:read" in perms
        assert "movie:read" in perms
        assert "comment:read" in perms

    async def test_grant_permissions_duplicate(self, db: DatabaseLayerV2):
        """TC-Auth-08-04: grant_permissions 重复权限"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permgrant003")
        admin_id = await get_admin_user_id(auth_service)
        
        # 第一次授予
        assign_data = UserPermissionAssign(
            user_id=created_user.id,
            permission_codes=["crawler:task:read"],
            granted_by=admin_id,
        )
        count1 = await auth_service.grant_permissions(assign_data)
        assert count1 == 1
        
        # 第二次重复授予
        count2 = await auth_service.grant_permissions(assign_data)
        assert count2 == 0

    async def test_get_user_permissions(self, db: DatabaseLayerV2):
        """TC-Auth-08-05: get_user_permissions"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permget001")
        admin_id = await get_admin_user_id(auth_service)
        
        # 授予权限
        await db.insert("user_permissions", {
            "user_id": created_user.id,
            "permission_code": "crawler:task:read",
            "granted_by": admin_id,
        }, return_id=False)
        
        perms = await auth_service.get_user_permissions(created_user.id)
        assert isinstance(perms, list)
        assert "crawler:task:read" in perms

    async def test_set_permissions_replace(self, db: DatabaseLayerV2):
        """TC-Auth-08-06: set_permissions 全量替换"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permset001")
        admin_id = await get_admin_user_id(auth_service)
        
        # 先授予一些权限
        assign_data1 = UserPermissionAssign(
            user_id=created_user.id,
            permission_codes=["crawler:task:read"],
            granted_by=admin_id,
        )
        await auth_service.grant_permissions(assign_data1)
        
        # 全量替换
        assign_data2 = UserPermissionAssign(
            user_id=created_user.id,
            permission_codes=["movie:manage", "movie:read"],
            granted_by=admin_id,
        )
        count = await auth_service.set_permissions(assign_data2)
        assert count == 2
        
        # 验证
        perms = await auth_service.get_user_permissions(created_user.id)
        assert "crawler:task:read" not in perms
        assert "movie:manage" in perms
        assert "movie:read" in perms

    async def test_set_permissions_clear(self, db: DatabaseLayerV2):
        """TC-Auth-08-07: set_permissions 清空权限"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permset002")
        admin_id = await get_admin_user_id(auth_service)
        
        # 先授予权限
        assign_data1 = UserPermissionAssign(
            user_id=created_user.id,
            permission_codes=["crawler:task:read"],
            granted_by=admin_id,
        )
        await auth_service.grant_permissions(assign_data1)
        
        # 清空
        assign_data2 = UserPermissionAssign(
            user_id=created_user.id,
            permission_codes=[],
            granted_by=admin_id,
        )
        count = await auth_service.set_permissions(assign_data2)
        assert count == 0
        
        # 验证已清空
        perms = await auth_service.get_user_permissions(created_user.id)
        assert perms == []

    async def test_revoke_permission(self, db: DatabaseLayerV2):
        """TC-Auth-08-08: revoke_permission"""
        auth_service = AuthService(db)
        created_user = await create_test_user(auth_service, "permrevoke001")
        admin_id = await get_admin_user_id(auth_service)
        
        # 先授予权限
        assign_data = UserPermissionAssign(
            user_id=created_user.id,
            permission_codes=["crawler:task:read"],
            granted_by=admin_id,
        )
        await auth_service.grant_permissions(assign_data)
        
        # 撤销
        result = await auth_service.revoke_permission(created_user.id, "crawler:task:read")
        assert result is True
        
        # 验证已撤销
        perms = await auth_service.get_user_permissions(created_user.id)
        assert "crawler:task:read" not in perms
