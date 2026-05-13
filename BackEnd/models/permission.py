"""
models/permission.py

权限字典 Pydantic 模型。

映射表：permissions
"""

from pydantic import BaseModel, Field


class PermissionRead(BaseModel):
    """权限读出模型。"""
    code:        str = Field(description="权限编码，如 'user:manage'")
    name:        str = Field(description="权限名称，如 '用户管理'")
    description: str = Field("", description="权限说明")
