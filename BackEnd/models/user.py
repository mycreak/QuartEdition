"""
models/user.py

用户 Pydantic 模型。

映射表：users
"""

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{6,32}$")

PASSWORD_PATTERN_UPPER = re.compile(r"[A-Z]")
PASSWORD_PATTERN_LOWER = re.compile(r"[a-z]")
PASSWORD_PATTERN_DIGIT = re.compile(r"\d")


class UserCreate(BaseModel):
    """
    创建用户入参。

    校验：
        username: 6-32 位字母数字下划线
        password: 6-128 位，必须包含大写字母、小写字母、数字
        display_name: 可选，为空则取 username
    """
    username:     str       = Field(min_length=6, max_length=32, description="用户名")
    password:     str       = Field(min_length=6, max_length=128, description="明文密码（后续由 service 层加密）")
    display_name: str       = Field("", description="显示名，为空则取 username")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not USERNAME_PATTERN.match(v):
            raise ValueError("用户名只能包含字母、数字、下划线，6-32 位")
        return v

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not PASSWORD_PATTERN_UPPER.search(v):
            raise ValueError("密码必须包含至少一个大写字母")
        if not PASSWORD_PATTERN_LOWER.search(v):
            raise ValueError("密码必须包含至少一个小写字母")
        if not PASSWORD_PATTERN_DIGIT.search(v):
            raise ValueError("密码必须包含至少一个数字")
        return v


class UserUpdate(BaseModel):
    """更新用户入参（全部可选）。"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=64)
    is_active:    Optional[bool] = None
    avatar_url:   Optional[str] = Field(None, max_length=2048)


class UserRead(BaseModel):
    """用户读出模型（不含密码哈希）。uuid 是对外标识，id 是内部主键（前端勿用）。"""
    id:           int
    uuid:         int
    username:     str
    display_name: str
    avatar_url:   str = ""
    is_active:    bool
    created_at:   datetime
    updated_at:   Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    """登录入参。"""
    username: str = Field(min_length=1, description="用户名")
    password: str = Field(min_length=1, description="明文密码")
