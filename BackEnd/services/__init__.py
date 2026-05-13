"""
services/__init__.py

业务服务层统一入口。

通过模块级工厂函数获取单例：
    from services import _get_auth_service
    svc = _get_auth_service()
"""

from .app_services import AppServices
from .movie_service import MovieService
from .auth_service import _get_auth_service, init_auth_service
from .review_service import _get_review_service, init_review_service
from .task_failure_service import _get_failure_service, init_task_failure_service
from .task_history_service import _get_history_service, init_task_history_service

__all__ = [
    "AppServices",
    "MovieService",
    "_get_auth_service", "init_auth_service",
    "_get_review_service", "init_review_service",
    "_get_failure_service", "init_task_failure_service",
    "_get_history_service", "init_task_history_service",
]
