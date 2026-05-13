"""
services/app_services.py

类型化服务容器。

⚠️ 当前仅包含 db + movie_service，其余服务（AuthService/ReviewService
/TaskFailureService/TaskHistoryService）通过模块级 `_get_*_service()` 函数获取。
此为有意设计 — 保持容器轻量，避免在 service 层造成循环依赖。

成员说明：
    db              DatabaseLayerV2  — 统一数据库中间层（MySQL/MongoDB/Redis）
    movie_service   MovieService     — 电影业务层

使用方式：
    from quart import current_app

    movies: MovieService = current_app.services.movie_service
    result = await movies.batch_list_movies(...)

    db_health = await current_app.services.db.ping_all()

与旧版对比：
    # ❌ 旧：动态属性，无类型提示，IDE 无自动补全
    app.movie_service = MovieService(app.db)
    current_app.movie_service.batch_list_movies(...)

    # ✅ 新：类型化容器，IDE 全程有类型推断
    app.services = AppServices(db=db, movie_service=MovieService(db))
    current_app.services.movie_service.batch_list_movies(...)
"""

from db.database_v2 import DatabaseLayerV2
from services.movie_service import MovieService


class AppServices:
    """Quart 应用运行时服务容器。"""

    def __init__(self, db: DatabaseLayerV2, movie_service: MovieService):
        self.db = db
        self.movie_service = movie_service
