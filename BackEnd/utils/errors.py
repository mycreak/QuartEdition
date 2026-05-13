"""
utils/errors.py

统一业务异常体系。

用法：
    from utils.errors import NotFoundError, DuplicateError, ...

    # Service 层 — 失败时抛出，不 return None/False
    raise NotFoundError("用户", user_id)

    # 路由层 — 统一捕获
    try:
        result = await service.method(...)
    except ServiceError as e:
        return jsonify({"error": e.message, "code": e.code}), e.status_code

设计原则：
    1. 每个异常携带 message（人类可读）、code（机器可读）、status_code（HTTP 状态码）
    2. 继承层次按"通用 → 业务语义"组织
    3. 路由层只需一个 except ServiceError 即可处理所有业务异常
"""


class ServiceError(Exception):
    """Service 层业务异常基类。

    属性：
        message:     人类可读的错误描述
        code:        机器可读的错误编码（前端可用于 i18n 或逻辑判断）
        status_code: 对应的 HTTP 状态码
    """
    def __init__(self, message: str, code: str = "BAD_REQUEST", status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)


# ═══════════════════════════════════════
# 通用 HTTP 语义异常
# ═══════════════════════════════════════

class BadRequestError(ServiceError):
    """400 — 请求格式错误 / 参数校验失败"""
    def __init__(self, message: str = "请求参数错误"):
        super().__init__(message, "BAD_REQUEST", 400)


class UnauthorizedError(ServiceError):
    """401 — 未登录 / 登录已过期"""
    def __init__(self, message: str = "未登录或登录已过期"):
        super().__init__(message, "UNAUTHORIZED", 401)


class ForbiddenError(ServiceError):
    """403 — 无权限"""
    def __init__(self, message: str = "无权限"):
        super().__init__(message, "FORBIDDEN", 403)


class TooManyRequestsError(ServiceError):
    """429 — 请求频率超限"""
    def __init__(self, message: str = "请求过于频繁，请稍后再试", code: str = "RATE_LIMITED"):
        super().__init__(message, code, 429)


class NotFoundError(ServiceError):
    """404 — 资源不存在"""
    def __init__(self, resource: str, identifier):
        super().__init__(f"{resource} 不存在: {identifier}", "NOT_FOUND", 404)


class ConflictError(ServiceError):
    """409 — 资源冲突（已存在 / 状态冲突）"""
    def __init__(self, message: str, code: str = "CONFLICT"):
        super().__init__(message, code, 409)


# ═══════════════════════════════════════
# 业务语义异常（继承通用异常）
# ═══════════════════════════════════════

class DuplicateError(ConflictError):
    """资源已存在（如用户名重复 / 权限记录已存在）"""
    def __init__(self, field: str, value: str):
        super().__init__(f"{field} '{value}' 已存在", "DUPLICATE")


class AuthenticationError(UnauthorizedError):
    """认证失败（用户名或密码错误）"""
    def __init__(self, detail: str = "用户名或密码错误"):
        super().__init__(detail)


class UserDisabledError(UnauthorizedError):
    """账户已被禁用"""
    def __init__(self):
        super().__init__("账户已被禁用")
        self.code = "USER_DISABLED"


class UserNotActiveError(ForbiddenError):
    """账户未激活"""
    def __init__(self):
        super().__init__("账户未激活")


class ClaimConflictError(ConflictError):
    """认领冲突 — 已被别人认领或不存在"""
    def __init__(self):
        super().__init__("认领失败 — 已被别人抢走或记录不存在", "CLAIM_CONFLICT")


class ClaimNotYoursError(ForbiddenError):
    """非本人认领的操作"""
    def __init__(self, action: str = "操作"):
        super().__init__(f"{action}失败 — 不是你认领的")


class ResourceNotFoundError(NotFoundError):
    """通用资源不存在（当不需要精确区分资源类型时使用）"""
    def __init__(self, identifier=None):
        msg = f"资源不存在: {identifier}" if identifier else "资源不存在"
        super().__init__("资源", identifier or "未知")


class RetriesExceededError(ConflictError):
    """重试次数已超上限 — 达到 retry_count 阈值"""
    def __init__(self, identifier=None, max_retries: int = 2):
        detail = f"失败记录 {identifier} 重试次数已达上限 ({max_retries}次)" if identifier else f"重试次数已达上限 ({max_retries}次)"
        super().__init__(detail, "RETRIES_EXCEEDED")
