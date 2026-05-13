"""
utils/service_access.py

统一服务获取入口 — 消除路由文件中重复的 `_get_*_service()` 辅助函数。

使用方式：
    from utils.service_access import get_auth_service, get_review_service

    svc = get_review_service()
"""

from services.auth_service import _get_auth_service as _auth
from services.review_service import _get_review_service as _review


def get_auth_service():
    return _auth()


def get_review_service():
    return _review()
