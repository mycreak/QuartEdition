
"""
user Pydantic 模型单元测试
覆盖: UserCreate, UserUpdate, UserRead, UserLogin
"""
import pytest
from datetime import datetime
from pydantic import ValidationError
from models.user import UserCreate, UserUpdate, UserRead, UserLogin


class TestUserCreate:
    """核心：创建用户入参验证测试"""

    def test_valid_full_input(self):
        """完整输入（含 display_name）- 正常通过"""
        user = UserCreate(
            username="valid_user_123",
            password="ValidPass123",
            display_name="My Display Name",
        )
        assert user.username == "valid_user_123"
        assert user.password == "ValidPass123"
        assert user.display_name == "My Display Name"

    def test_valid_minimal_input(self):
        """最小输入（仅必填，display_name 留空）- 正常通过"""
        user = UserCreate(username="valid_user_123", password="ValidPass123")
        assert user.username == "valid_user_123"
        assert user.display_name == ""

    def test_username_too_short(self):
        """用户名 <6 字符"""
        with pytest.raises(ValidationError):
            UserCreate(username="abcd", password="ValidPass123")

    def test_username_too_long(self):
        """用户名 >32 字符"""
        with pytest.raises(ValidationError):
            UserCreate(
                username="a" * 33,
                password="ValidPass123",
            )

    def test_username_invalid_chinese(self):
        """用户名含中文 - 不允许"""
        with pytest.raises(ValidationError):
            UserCreate(username="张三123456", password="ValidPass123")

    def test_username_invalid_space(self):
        """用户名含空格 - 不允许"""
        with pytest.raises(ValidationError):
            UserCreate(username="ab cdef", password="ValidPass123")

    def test_username_invalid_special_char(self):
        """用户名含 @ 等非法字符 - 不允许"""
        with pytest.raises(ValidationError):
            UserCreate(username="invalid@user", password="ValidPass123")

    def test_password_too_short(self):
        """密码 <6 字符"""
        with pytest.raises(ValidationError):
            UserCreate(username="valid_user_123", password="Va123")

    def test_password_too_long(self):
        """密码 >128 字符"""
        with pytest.raises(ValidationError):
            UserCreate(username="valid_user_123", password="V1a" * 43)

    def test_password_missing_uppercase(self):
        """密码缺少大写字母"""
        with pytest.raises(ValidationError):
            UserCreate(username="valid_user_123", password="validpass123")

    def test_password_missing_lowercase(self):
        """密码缺少小写字母"""
        with pytest.raises(ValidationError):
            UserCreate(username="valid_user_123", password="VALIDPASS123")

    def test_password_missing_digit(self):
        """密码缺少数字"""
        with pytest.raises(ValidationError):
            UserCreate(username="valid_user_123", password="ValidPass")

    def test_password_valid_complexity(self):
        """密码满足所有复杂度要求"""
        user = UserCreate(
            username="valid_user_123", password="ValidPass123!@#$%^&*()"
        )
        assert user.password == "ValidPass123!@#$%^&*()"


class TestUserLogin:
    """用户登录入参验证"""

    def test_valid_login(self):
        """正常登录输入"""
        login = UserLogin(username="valid_user_123", password="ValidPass123")
        assert login.username == "valid_user_123"
        assert login.password == "ValidPass123"

    def test_login_username_missing(self):
        """用户名缺失"""
        with pytest.raises(ValidationError, match="Field required"):
            UserLogin(password="ValidPass123")

    def test_login_password_missing(self):
        """密码缺失"""
        with pytest.raises(ValidationError, match="Field required"):
            UserLogin(username="valid_user_123")


class TestUserUpdate:
    """用户更新入参验证"""

    def test_update_no_fields(self):
        """空更新（不传任何字段）- 合法"""
        update = UserUpdate()
        assert update.display_name is None
        assert update.is_active is None

    def test_update_display_name_only(self):
        """只更新显示名"""
        update = UserUpdate(display_name="New Name")
        assert update.display_name == "New Name"
        assert update.is_active is None

    def test_update_is_active_only(self):
        """只更新激活状态"""
        update = UserUpdate(is_active=False)
        assert update.display_name is None
        assert update.is_active is False

    def test_update_both_fields(self):
        """同时更新显示名和激活状态"""
        update = UserUpdate(display_name="New Name", is_active=False)
        assert update.display_name == "New Name"
        assert update.is_active is False

    def test_update_display_name_too_short(self):
        """显示名长度 <1（空字符串）- 不合法"""
        with pytest.raises(ValidationError):
            UserUpdate(display_name="")

    def test_update_display_name_too_long(self):
        """显示名长度 >64 - 不合法"""
        with pytest.raises(ValidationError):
            UserUpdate(display_name="a" * 65)


class TestUserRead:
    """用户读出模型测试：ORM 转换/序列化"""

    def test_construct_from_dict(self):
        """从字典构造（模拟 model_validate）"""
        data = {
            "id": 1,
            "uuid": 123456789,
            "username": "valid_user_123",
            "display_name": "My Display",
            "is_active": True,
            "created_at": datetime(2024, 1, 1, 0, 0, 0),
        }
        user = UserRead(**data)
        assert user.id == 1
        assert user.uuid == 123456789
        assert user.username == "valid_user_123"
        assert user.display_name == "My Display"
        assert user.is_active is True
        assert user.created_at == datetime(2024, 1, 1, 0, 0, 0)
        assert user.updated_at is None

    def test_construct_with_updated_at(self):
        """带 updated_at 字段构造"""
        data = {
            "id": 1,
            "uuid": 123456789,
            "username": "valid_user_123",
            "display_name": "My Display",
            "is_active": True,
            "created_at": datetime(2024, 1, 1, 0, 0, 0),
            "updated_at": datetime(2024, 2, 1, 0, 0, 0),
        }
        user = UserRead(**data)
        assert user.updated_at == datetime(2024, 2, 1, 0, 0, 0)

    def test_model_dump(self):
        """模型转字典（序列化）"""
        data = {
            "id": 1,
            "uuid": 123456789,
            "username": "valid_user_123",
            "display_name": "My Display",
            "is_active": True,
            "created_at": datetime(2024, 1, 1, 0, 0, 0),
        }
        user = UserRead(**data)
        dump = user.model_dump()
        assert isinstance(dump, dict)
        # UserRead 包含 updated_at 字段，所以 dump 里有这个键，不管有没有值
        assert "id" in dump
        assert "uuid" in dump
        assert "username" in dump
        assert "display_name" in dump
        assert "is_active" in dump
        assert "created_at" in dump
        assert "updated_at" in dump

    def test_model_dump_json(self):
        """模型转 JSON 字符串"""
        data = {
            "id": 1,
            "uuid": 123456789,
            "username": "valid_user_123",
            "display_name": "My Display",
            "is_active": True,
            "created_at": datetime(2024, 1, 1, 0, 0, 0),
        }
        user = UserRead(**data)
        json_str = user.model_dump_json()
        assert isinstance(json_str, str)
        # 至少有 id/username
        assert '"id":1' in json_str
        assert '"username":"valid_user_123"' in json_str

