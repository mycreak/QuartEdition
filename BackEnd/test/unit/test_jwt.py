
"""
JWT 工具单元测试
测试内容:
    - create_token 方法测试
    - verify_token 方法测试
    - Token 过期验证
    - Token 签名验证
    - Token 格式验证
"""

import pytest
import time
from unittest.mock import MagicMock

# 导入被测试模块
from services.auth_service import AuthService
from config.settings import settings
from db.database_v2 import DatabaseLayerV2


@pytest.fixture(autouse=True)
def setup_test_jwt_secret():
    original_secret = settings.JWT_SECRET
    settings.JWT_SECRET = "test_secret_key_for_jwt"
    yield
    settings.JWT_SECRET = original_secret


class TestAuthServiceTokenCreation:
    @pytest.fixture
    def auth_service(self):
        mock_db = MagicMock(spec=DatabaseLayerV2)
        return AuthService(mock_db)

    def test_create_token_returns_string(self, auth_service):
        token = auth_service.create_token(user_id=123)
        assert isinstance(token, str)
        assert len(token) != 0

    def test_create_token_basic(self, auth_service):
        token = auth_service.create_token(user_id=123)
        assert isinstance(token, str)
        assert len(token) != 0

    def test_create_token_different_users_different_tokens(self, auth_service):
        token1 = auth_service.create_token(user_id=123)
        token2 = auth_service.create_token(user_id=456)
        assert token1 != token2

    def test_create_token_same_user_different_times_different_tokens(self, auth_service):
        token1 = auth_service.create_token(user_id=123)
        time.sleep(1.01)  # 等待更长时间确保iat不同
        token2 = auth_service.create_token(user_id=123)
        assert token1 != token2

    def test_verify_token_valid_token(self, auth_service):
        token = auth_service.create_token(user_id=123)
        user_id = auth_service.verify_token(token)
        assert user_id == 123

    def test_verify_token_invalid_signature(self, auth_service):
        token = auth_service.create_token(user_id=123)
        tampered_token = token + "XXXXX"
        user_id = auth_service.verify_token(tampered_token)
        assert user_id is None

    def test_verify_token_wrong_secret(self, auth_service):
        token = auth_service.create_token(user_id=123)
        old_secret = settings.JWT_SECRET
        settings.JWT_SECRET = "wrong_secret"
        try:
            user_id = auth_service.verify_token(token)
            assert user_id is None
        finally:
            settings.JWT_SECRET = old_secret

    def test_verify_token_empty_string(self, auth_service):
        user_id = auth_service.verify_token("")
        assert user_id is None

    def test_verify_token_none(self, auth_service):
        user_id = auth_service.verify_token(None)
        assert user_id is None

    def test_verify_token_malformed_token(self, auth_service):
        user_id = auth_service.verify_token("malformed.token.string")
        assert user_id is None


class TestAuthServiceTokenExpiration:
    @pytest.fixture
    def auth_service(self):
        mock_db = MagicMock(spec=DatabaseLayerV2)
        return AuthService(mock_db)

    @pytest.mark.slow
    def test_verify_token_expired(self, auth_service):
        original_expire = settings.JWT_EXPIRE_SECONDS
        settings.JWT_EXPIRE_SECONDS = 0.01
        try:
            token = auth_service.create_token(user_id=123)
            time.sleep(0.02)
            user_id = auth_service.verify_token(token)
            assert user_id is None
        finally:
            settings.JWT_EXPIRE_SECONDS = original_expire


class TestJWTTokenStructure:
    @pytest.fixture
    def auth_service(self):
        mock_db = MagicMock(spec=DatabaseLayerV2)
        return AuthService(mock_db)

    def test_token_has_three_parts(self, auth_service):
        token = auth_service.create_token(user_id=123)
        parts = token.split('.')
        assert len(parts) == 3

    def test_token_payload_contains_required_fields(self, auth_service):
        import jwt
        token = auth_service.create_token(user_id=123)
        payload = jwt.decode(token, options={"verify_signature": False})
        assert 'sub' in payload
        assert 'iat' in payload
        assert 'exp' in payload
        assert payload['sub'] == str(123)


class TestJWTTokenEdgeCases:
    @pytest.fixture
    def auth_service(self):
        mock_db = MagicMock(spec=DatabaseLayerV2)
        return AuthService(mock_db)

    def test_create_token_user_id_zero(self, auth_service):
        token = auth_service.create_token(user_id=0)
        user_id = auth_service.verify_token(token)
        assert user_id == 0

    def test_create_token_large_user_id(self, auth_service):
        large_id = 9999999999
        token = auth_service.create_token(user_id=large_id)
        user_id = auth_service.verify_token(token)
        assert user_id == large_id

    def test_create_token_negative_user_id(self, auth_service):
        token = auth_service.create_token(user_id=-123)
        user_id = auth_service.verify_token(token)
        assert user_id == -123


class TestJWTTokenBatchGeneration:
    @pytest.fixture
    def auth_service(self):
        mock_db = MagicMock(spec=DatabaseLayerV2)
        return AuthService(mock_db)

    def test_batch_create_tokens_unique(self, auth_service):
        tokens = set()
        for i in range(100):
            token = auth_service.create_token(user_id=i)
            assert token not in tokens
            tokens.add(token)
        assert len(tokens) == 100

    def test_batch_verify_tokens_correctly(self, auth_service):
        tokens = [auth_service.create_token(user_id=i) for i in range(100)]
        for i, token in enumerate(tokens):
            user_id = auth_service.verify_token(token)
            assert user_id == i


