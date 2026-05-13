
"""
错误处理 单元测试
"""

import pytest

# 导入被测试模块
from utils.errors import (
    ServiceError,
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    TooManyRequestsError,
    NotFoundError,
    ConflictError,
    DuplicateError,
    AuthenticationError,
    UserDisabledError,
    UserNotActiveError,
    ClaimConflictError,
    ClaimNotYoursError,
    ResourceNotFoundError,
    RetriesExceededError,
)


# ============================================================================
# 一、基类 ServiceError 测试
# ============================================================================

class TestServiceError:
    """ServiceError 基类测试"""

    def test_service_error_init_with_defaults(self):
        """测试使用默认参数初始化"""
        err = ServiceError("测试错误")
        assert err.message == "测试错误"
        assert err.code == "BAD_REQUEST"
        assert err.status_code == 400

    def test_service_error_init_with_custom_params(self):
        """测试使用自定义参数初始化"""
        err = ServiceError("自定义消息", code="CUSTOM_CODE", status_code=418)
        assert err.message == "自定义消息"
        assert err.code == "CUSTOM_CODE"
        assert err.status_code == 418

    def test_service_error_inherits_from_exception(self):
        """测试 ServiceError 继承自 Exception"""
        err = ServiceError("消息")
        assert isinstance(err, Exception)

    def test_service_error_message_in_str(self):
        """测试异常字符串包含 message"""
        err = ServiceError("测试错误消息")
        assert "测试错误消息" in str(err)


# ============================================================================
# 二、通用 HTTP 语义异常测试
# ============================================================================

class TestBadRequestError:
    """BadRequestError 400测试"""

    def test_bad_request_defaults(self):
        """测试默认参数"""
        err = BadRequestError()
        assert err.message == "请求参数错误"
        assert err.code == "BAD_REQUEST"
        assert err.status_code == 400

    def test_bad_request_custom_message(self):
        """测试自定义消息"""
        err = BadRequestError("用户名格式错误")
        assert err.message == "用户名格式错误"


class TestUnauthorizedError:
    """UnauthorizedError 401测试"""

    def test_unauthorized_defaults(self):
        """测试默认参数"""
        err = UnauthorizedError()
        assert err.message == "未登录或登录已过期"
        assert err.code == "UNAUTHORIZED"
        assert err.status_code == 401

    def test_unauthorized_custom_message(self):
        """测试自定义消息"""
        err = UnauthorizedError("Token已过期")
        assert err.message == "Token已过期"


class TestForbiddenError:
    """ForbiddenError 403测试"""

    def test_forbidden_defaults(self):
        """测试默认参数"""
        err = ForbiddenError()
        assert err.message == "无权限"
        assert err.code == "FORBIDDEN"
        assert err.status_code == 403

    def test_forbidden_custom_message(self):
        """测试自定义消息"""
        err = ForbiddenError("只有管理员才能操作")
        assert err.message == "只有管理员才能操作"


class TestNotFoundError:
    """NotFoundError 404测试"""

    def test_not_found_init(self):
        """测试 NotFoundError 初始化"""
        err = NotFoundError("用户", 123)
        assert err.message == "用户 不存在: 123"
        assert err.code == "NOT_FOUND"
        assert err.status_code == 404


class TestConflictError:
    """ConflictError 409测试"""

    def test_conflict_init(self):
        """测试 ConflictError 初始化"""
        err = ConflictError("状态冲突")
        assert err.message == "状态冲突"
        assert err.code == "CONFLICT"
        assert err.status_code == 409

    def test_conflict_custom_code(self):
        """测试自定义错误码"""
        err = ConflictError("自定义冲突", code="CUSTOM_CONFLICT")
        assert err.code == "CUSTOM_CONFLICT"


class TestTooManyRequestsError:
    """TooManyRequestsError 429测试"""

    def test_too_many_requests_defaults(self):
        """测试默认参数"""
        err = TooManyRequestsError()
        assert err.message == "请求过于频繁，请稍后再试"
        assert err.code == "RATE_LIMITED"
        assert err.status_code == 429

    def test_too_many_requests_custom_message(self):
        """测试自定义消息"""
        err = TooManyRequestsError("1分钟内只能请求10次")
        assert err.message == "1分钟内只能请求10次"


# ============================================================================
# 三、业务语义异常测试
# ============================================================================

class TestDuplicateError:
    """DuplicateError 测试"""

    def test_duplicate_error_init(self):
        """测试初始化"""
        err = DuplicateError("用户名", "testuser")
        assert err.message == "用户名 'testuser' 已存在"
        assert err.code == "DUPLICATE"
        assert err.status_code == 409

    def test_duplicate_inherits_from_conflict(self):
        """测试继承关系"""
        err = DuplicateError("邮箱", "test@test.com")
        assert isinstance(err, ConflictError)
        assert isinstance(err, ServiceError)


class TestAuthenticationError:
    """AuthenticationError 测试"""

    def test_authentication_error_defaults(self):
        """测试默认参数"""
        err = AuthenticationError()
        assert err.message == "用户名或密码错误"
        assert err.code == "UNAUTHORIZED"
        assert err.status_code == 401

    def test_authentication_error_custom_detail(self):
        """测试自定义详情"""
        err = AuthenticationError("密码错误")
        assert err.message == "密码错误"

    def test_authentication_inherits_from_unauthorized(self):
        """测试继承关系"""
        err = AuthenticationError()
        assert isinstance(err, UnauthorizedError)


class TestUserDisabledError:
    """UserDisabledError 测试"""

    def test_user_disabled_error(self):
        """测试用户已禁用错误"""
        err = UserDisabledError()
        assert err.message == "账户已被禁用"
        assert err.code == "USER_DISABLED"
        assert err.status_code == 401


class TestUserNotActiveError:
    """UserNotActiveError 测试"""

    def test_user_not_active_error(self):
        """测试用户未激活错误"""
        err = UserNotActiveError()
        assert err.message == "账户未激活"
        assert err.code == "FORBIDDEN"
        assert err.status_code == 403


class TestClaimConflictError:
    """ClaimConflictError 测试"""

    def test_claim_conflict_error(self):
        """测试认领冲突错误"""
        err = ClaimConflictError()
        assert err.message == "认领失败 — 已被别人抢走或记录不存在"
        assert err.code == "CLAIM_CONFLICT"
        assert err.status_code == 409


class TestClaimNotYoursError:
    """ClaimNotYoursError 测试"""

    def test_claim_not_yours_default(self):
        """测试默认参数"""
        err = ClaimNotYoursError()
        assert err.message == "操作失败 — 不是你认领的"
        assert err.code == "FORBIDDEN"
        assert err.status_code == 403

    def test_claim_not_yours_custom_action(self):
        """测试自定义操作名称"""
        err = ClaimNotYoursError("提交")
        assert err.message == "提交失败 — 不是你认领的"


class TestResourceNotFoundError:
    """ResourceNotFoundError 测试"""

    def test_resource_not_found_with_identifier(self):
        """测试带标识符的错误"""
        err = ResourceNotFoundError(12345)
        assert err.message == "资源 不存在: 12345"
        assert err.code == "NOT_FOUND"
        assert err.status_code == 404

    def test_resource_not_found_without_identifier(self):
        """测试不带标识符的错误"""
        err = ResourceNotFoundError()
        assert err.message == "资源 不存在: 未知"


class TestRetriesExceededError:
    """RetriesExceededError 测试"""

    def test_retries_exceeded_with_identifier(self):
        """测试带标识符的错误"""
        err = RetriesExceededError("failure-123", max_retries=5)
        assert err.message == "失败记录 failure-123 重试次数已达上限 (5次)"
        assert err.code == "RETRIES_EXCEEDED"
        assert err.status_code == 409

    def test_retries_exceeded_without_identifier(self):
        """测试不带标识符的错误"""
        err = RetriesExceededError()
        assert err.message == "重试次数已达上限 (2次)"


# ============================================================================
# 四、继承关系完整性测试
# ============================================================================

class TestErrorHierarchy:
    """错误继承关系测试"""

    def test_all_errors_inherit_from_service_error(self):
        """测试所有错误类都继承自 ServiceError"""
        test_cases = [
            (BadRequestError, []),
            (UnauthorizedError, []),
            (ForbiddenError, []),
            (NotFoundError, ["测试资源", "123"]),
            (ConflictError, ["冲突"]),
            (DuplicateError, ["字段", "值"]),
            (AuthenticationError, []),
            (UserDisabledError, []),
            (UserNotActiveError, []),
            (ClaimConflictError, []),
            (ClaimNotYoursError, []),
            (ResourceNotFoundError, [None]),
            (RetriesExceededError, []),
        ]
        for cls, args in test_cases:
            err = cls(*args)
            assert isinstance(err, ServiceError)

    def test_duplicate_inherits_conflict(self):
        """测试 DuplicateError 继承关系"""
        err = DuplicateError("字段", "值")
        assert isinstance(err, ConflictError)
        assert isinstance(err, ServiceError)

    def test_authentication_error_hierarchy(self):
        """测试 AuthenticationError 继承关系"""
        err = AuthenticationError()
        assert isinstance(err, UnauthorizedError)
        assert isinstance(err, ServiceError)

    def test_user_disabled_error_hierarchy(self):
        """测试 UserDisabledError 继承关系"""
        err = UserDisabledError()
        assert isinstance(err, UnauthorizedError)
        assert isinstance(err, ServiceError)

    def test_claim_conflict_error_hierarchy(self):
        """测试 ClaimConflictError 继承关系"""
        err = ClaimConflictError()
        assert isinstance(err, ConflictError)
        assert isinstance(err, ServiceError)

    def test_retries_exceeded_error_hierarchy(self):
        """测试 RetriesExceededError 继承关系"""
        err = RetriesExceededError()
        assert isinstance(err, ConflictError)
        assert isinstance(err, ServiceError)


# ============================================================================
# 五、实际使用场景测试
# ============================================================================

class TestErrorUsageScenarios:
    """错误使用场景测试"""

    def test_catch_service_error_can_catch_all(self):
        """测试 ServiceError 可以捕获所有子类"""
        # 抛出各种异常
        def raise_error(err_class, args):
            raise err_class(*args)

        # 测试用 ServiceError 捕获所有类型
        test_cases = [
            (BadRequestError, []),
            (UnauthorizedError, []),
            (NotFoundError, ["资源", "123"]),
        ]
        for cls, args in test_cases:
            with pytest.raises(ServiceError):
                raise_error(cls, args)

    def test_catch_specific_error_type(self):
        """测试捕获特定类型错误"""
        try:
            raise DuplicateError("用户名", "test")
        except ConflictError:
            # 可以捕获 ConflictError
            pass
        except Exception:
            pytest.fail("应该能被 ConflictError 捕获")

    def test_error_code_for_i18n_or_logic(self):
        """测试错误码可以用于i18n或逻辑分支"""
        # 模拟前端根据 code 进行处理
        def handle_error(err: ServiceError):
            if err.code == "NOT_FOUND":
                return "not_found"
            elif err.code == "DUPLICATE":
                return "duplicate"
            else:
                return "generic"

        err1 = ResourceNotFoundError(123)
        err2 = DuplicateError("用户名", "test")

        assert handle_error(err1) == "not_found"
        assert handle_error(err2) == "duplicate"

    def test_error_status_code_for_http_response(self):
        """测试 HTTP 状态码正确"""
        assert BadRequestError().status_code == 400
        assert UnauthorizedError().status_code == 401
        assert ForbiddenError().status_code == 403
        assert NotFoundError("资源", "id").status_code == 404
        assert ConflictError("冲突").status_code == 409
        assert TooManyRequestsError().status_code == 429
