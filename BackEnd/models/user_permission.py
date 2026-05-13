"""
models/user_permission.py

用户-权限关联 Pydantic 模型。

映射表：user_permissions
"""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, field_validator, ConfigDict

# 合法权限编码白名单（种子脚本预置）
VALID_PERMISSION_CODES = {
    "user:manage",
    "crawler:task:read",
    "crawler:task:write",
    "crawler:failure:manage",
    "movie:manage",
    "movie:read",
    "comment:read",
    "comment:manage",
    "system:monitor",
}


class UserPermissionAssign(BaseModel):
    """
    为用户设置权限（全量替换模式）。

    输入：
        user_id:         目标用户 ID
        permission_codes: 权限编码列表，如 ["movie:read", "movie:manage"]
                          传空列表 [] 即清空所有权限
        granted_by:       授权的管理员 ID
    """
    user_id:          int        = Field(gt=0, description="目标用户 ID")
    permission_codes: List[str]  = Field(default_factory=list, description="权限编码列表，空列表=清空")
    granted_by:       int        = Field(gt=0, description="授权的管理员 ID")

    @field_validator("permission_codes")
    @classmethod
    def validate_codes(cls, codes: List[str]) -> List[str]:
        invalid = [c for c in codes if c not in VALID_PERMISSION_CODES]
        if invalid:
            raise ValueError(f"无效的权限编码: {', '.join(invalid)}")
        return codes


class UserPermissionRead(BaseModel):
    """用户权限读出。"""
    user_id:         int
    permission_code: str
    granted_by:      int
    granted_at:      datetime

    model_config = ConfigDict(from_attributes=True)
