"""
models/__init__.py

Pydantic 数据模型统一入口。

命名规范：
    *Create → 写入入参（不含 id/created_at）
    *Read   → 读出结果（含 id/created_at）
    *Detail → 聚合视图（多表拼装）
"""

from .movie_models import (
    MovieCreate, MovieUpdate, MovieRead,
    PeopleRead, GenreRead, RegionRead,
    RatingCreate, RatingRead,
    CreditRead, MovieDetail, GenreStat,
    RoleType,
)
from .user import UserCreate, UserUpdate, UserRead, UserLogin
from .permission import PermissionRead
from .user_permission import (
    UserPermissionAssign, UserPermissionRead, VALID_PERMISSION_CODES,
)

__all__ = [
    # movie
    "MovieCreate", "MovieUpdate", "MovieRead",
    "PeopleRead", "GenreRead", "RegionRead",
    "RatingCreate", "RatingRead",
    "CreditRead", "MovieDetail", "GenreStat",
    "RoleType",
    # user
    "UserCreate", "UserUpdate", "UserRead", "UserLogin",
    # permission
    "PermissionRead",
    "UserPermissionAssign", "UserPermissionRead", "VALID_PERMISSION_CODES",
]
