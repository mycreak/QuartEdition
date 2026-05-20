"""
routes/user/__init__.py

用户 API 路由入口。所有子模块在此注册为单一 user_bp 蓝图，
由 app.py 以 url_prefix="/user" 挂载。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
鉴权：全部端点需 JWT（@require_login），不需要管理员权限。
      任何已登录用户均可访问。

数据约束：只返回 is_published=True 的内容。
      管理员端（/admin/*）无此限制。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
子模块一览（按职责）：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

filter_routes.py — 过滤器数据包
    GET    /user/filter-packet      类型列表（含影片数）+ 评分区间（含影片数）
                                    数据限定 is_published=True
    依赖: crawl_progress, movies, movie_genres, movie_ratings

movie_routes.py — 电影浏览
    GET    /user/movies             电影列表（分页+搜索+类型过滤，按评分降序）
                                    每部附带 rating + genres 摘要
    GET    /user/movies/<id>        电影详情（聚合视图）
    依赖: MovieService

genre_routes.py — 类型与统计
    GET    /user/genres             类型列表
    GET    /user/genre-stats        类型统计（电影数 + 平均分）
    依赖: crawl_progress, movies, movie_genres, movie_ratings

review_routes.py — 评论浏览
    GET    /user/reviews            长评列表（按 movie_id 过滤 + 分页）
    GET    /user/comments           短评列表（按 movie_id 过滤 + 分页）
    依赖: MongoDB reviews / comments 集合

action_routes.py — 用户行为评分
    POST   /user/movies/<id>/want-watch     标记想看
    DELETE /user/movies/<id>/want-watch     取消想看
    POST   /user/movies/<id>/watching        标记在看
    DELETE /user/movies/<id>/watching        取消在看
    POST   /user/movies/<id>/watched         标记看过
    DELETE /user/movies/<id>/watched         取消看过
    POST   /user/movies/<id>/favorite        收藏电影
    DELETE /user/movies/<id>/favorite        取消收藏
    POST   /user/movies/<id>/comment         提交评论
    DELETE /user/movies/<id>/comment         删除评论
    GET    /user/movies/<id>/status          查询标记状态
    依赖: UserActionService, MovieContextService

profile_routes.py — 个人中心
    POST   /user/upload/avatar       上传头像
    GET    /user/profile/tags        标签画像
    GET    /user/profile/tags/<dim>  按维度画像
    依赖: TOS 图床, UserActionService

playlist_routes.py — 片单浏览
    GET    /user/playlists            已发布片单列表（轮播用）
    GET    /user/playlists/<id>      片单详情（含电影摘要）
    依赖: PlaylistService

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
注册: app.py 中:
      from routes.user import user_bp
      app.register_blueprint(user_bp, url_prefix="/user")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from quart import Blueprint

user_bp = Blueprint("user", __name__)

from .filter_routes import filter_bp
from .movie_routes import movie_bp
from .genre_routes import genre_bp
from .review_routes import review_bp
from .profile_routes import profile_bp
from .action_routes import action_bp
from .playlist_routes import playlist_user_bp

user_bp.register_blueprint(filter_bp)
user_bp.register_blueprint(movie_bp)
user_bp.register_blueprint(genre_bp)
user_bp.register_blueprint(review_bp)
user_bp.register_blueprint(profile_bp)
user_bp.register_blueprint(action_bp)
user_bp.register_blueprint(playlist_user_bp)
