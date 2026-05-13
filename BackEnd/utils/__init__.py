"""
utils/__init__.py

通用工具统一入口。
"""

from .auth import get_current_user, require_permission, require_login
from .errors import (
    ServiceError,
    BadRequestError, UnauthorizedError, ForbiddenError,
    TooManyRequestsError, NotFoundError, ConflictError,
    DuplicateError, AuthenticationError, UserDisabledError,
    ClaimConflictError, ClaimNotYoursError,
    ResourceNotFoundError, RetriesExceededError,
)
from .snowflake import init_snowflake, generate_id, SnowflakeGenerator
from .serializers import to_iso, serialize_datetime_fields, CST
from .rate_limit import check_rate_limit
from .system_monitor import get_system_health

__all__ = [
    # auth
    "get_current_user", "require_permission", "require_login",
    # errors
    "ServiceError",
    "BadRequestError", "UnauthorizedError", "ForbiddenError",
    "TooManyRequestsError", "NotFoundError", "ConflictError",
    "DuplicateError", "AuthenticationError", "UserDisabledError",
    "ClaimConflictError", "ClaimNotYoursError",
    "ResourceNotFoundError", "RetriesExceededError",
    # snowflake
    "init_snowflake", "generate_id", "SnowflakeGenerator",
    # serializers
    "to_iso", "serialize_datetime_fields", "CST",
    # rate_limit
    "check_rate_limit",
    # system_monitor
    "get_system_health",
]
