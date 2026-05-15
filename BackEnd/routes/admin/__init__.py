"""
routes/admin/__init__.py

管理员 API 路由入口。所有子模块在此注册为单一 admin_bp 蓝图，
再由 app.py 以 url_prefix="/admin" 挂载。app.py 零改动。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
子模块一览（按职责）：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

failure_routes.py — 失败任务认领管理
    GET    /admin/failures             失败列表（分页，按 status 过滤）   [crawler:failure:manage]
    GET    /admin/failures/<id>        单条详情                          [crawler:failure:manage]
    POST   /admin/failures/<id>/claim  认领（原子，先到先得）            [crawler:failure:manage]
    POST   /admin/failures/<id>/release 放弃认领                        [crawler:failure:manage]
    POST   /admin/failures/<id>/resolve 标记已解决                      [crawler:failure:manage]
    POST   /admin/failures/<id>/retry  重爬 → Redis ZSET               [crawler:failure:manage]
    依赖: TaskFailureService

task_routes.py — 爬虫任务提交与进度
    POST   /admin/tasks                提交 movie_crawl / review_crawl / comment_crawl
                                       body: {type, type_num, interval_id, subject_id, ...}
                                       → 生成 snowflake ID → 限速写入 Redis ZSET
                                       [crawler:task:write]
    GET    /admin/tasks                爬取进度列表（按 type_num 过滤，含 done 计算字段）
                                       [crawler:task:read]
    依赖: crawl_progress 表

movie_routes.py — 电影数据管理（查/编/上下架）
    GET    /admin/movies               电影列表（分页 + keyword 搜索 + type_num 过滤 + 上下架）
                                       [movie:read]
    GET    /admin/movies/<id>          电影详情（聚合视图: movie + rating + directors + actors + genres + regions）
                                       [movie:read]
    PATCH  /admin/movies/<id>          编辑基本信息                              [movie:manage]
    POST   /admin/movies/<id>/publish  上架电影                                  [movie:manage]
    POST   /admin/movies/<id>/unpublish 下架电影                                 [movie:manage]
    POST   /admin/movies/<id>/credits  添加演职人员                              [movie:manage]
    DELETE /admin/movies/<id>/credits  移除演职人员                              [movie:manage]
    POST   /admin/movies/<id>/genres   添加类型                                  [movie:manage]
    DELETE /admin/movies/<id>/genres/<type_num> 移除类型                         [movie:manage]
    POST   /admin/movies/<id>/regions  添加地区                                  [movie:manage]
    DELETE /admin/movies/<id>/regions/<region_id> 移除地区                       [movie:manage]
    PUT    /admin/movies/<id>/rating   更新评分                                  [movie:manage]
    GET    /admin/regions              地区字典列表（id + name）                  [movie:manage]
    POST   /admin/regions              创建新地区（含唯一性校验）                [movie:manage]
    依赖: MovieService, movies / movie_genres / crawl_progress 等表

review_routes.py — 评论管理（MongoDB）
    GET    /admin/reviews              长评列表（按 movie_id 过滤 + 分页） [comment:read]
    POST   /admin/reviews/<id>/publish 上架长评                          [comment:manage]
    POST   /admin/reviews/<id>/unpublish 下架长评                        [comment:manage]
    GET    /admin/comments             短评列表（按 movie_id / rating 过滤 + 分页）
                                       [comment:read]
    POST   /admin/comments/<id>/publish 上架短评                         [comment:manage]
    POST   /admin/comments/<id>/unpublish 下架短评                       [comment:manage]
    依赖: ReviewService, MongoDB reviews / comments 集合

user_routes.py — 用户与权限管理
    GET    /admin/users                用户列表                           [user:manage]
    POST   /admin/users                创建用户 (username + password + display_name)
                                       [user:manage]
    PATCH  /admin/users/<id>           更新用户（is_active / display_name） [user:manage]
    POST   /admin/users/<id>/permissions 分配权限 (permission_codes: [...])
                                       [user:manage]
    依赖: AuthService, users / user_permissions 表

status_routes.py — 系统监控
    GET    /admin/status               Puller状态 / Worker存活+卡死 / 队列饱和度 / CPU内存 / DB健康
                                       [system:monitor]
    GET    /admin/tasks/queue          任务队列实时快照（Redis ZSET + asyncio.Queue + Worker）[system:monitor]
    GET    /admin/rate-limit-events    限流事件记录                               [system:monitor]
    依赖: Puller / BrowserPool / SystemMonitor 单例

log_routes.py — 日志查询
    GET    /admin/logs                 按层级/级别/时间过滤的日志列表              [system:monitor]
    依赖: logs/ 目录

infra_routes.py — 基础设施管理
    GET    /admin/proxies              代理池列表（状态/来源/成功率）           [system:monitor]
    POST   /admin/proxies              添加代理                                [system:monitor]
    DELETE /admin/proxies/<host>/<port> 封禁/删除代理                           [system:monitor]
    POST   /admin/proxies/health-check 手动触发全量验证                          [system:monitor]
    GET    /admin/cookies              列出所有 Cookie 账号                     [system:monitor]
    POST   /admin/cookies              添加 Cookie 账号                         [system:monitor]
    DELETE /admin/cookies/<id>         删除 Cookie 账号                         [system:monitor]
    POST   /admin/cookies/<id>/ban     封禁账号                                [system:monitor]
    POST   /admin/cookies/<id>/unban   恢复账号                                [system:monitor]
    GET    /admin/cookies/status       Cookie 状态汇总                          [system:monitor]
    POST   /admin/cookies/replace      替换主账号 Cookie（兼容旧版）             [system:monitor]
    依赖: ProxyPool 单例 / CookieManager 单例

douban_id_routes.py — douban_id 资产管理
    GET    /admin/douban-ids           列表（分页/搜索/未认领过滤，默认排除已爬取） [crawler:task:read]
    POST   /admin/douban-ids           手动添加 ID                              [crawler:task:write]
    POST   /admin/douban-ids/<id>/acquire 认领（原子，先到先得）                [crawler:task:write]
    POST   /admin/douban-ids/<id>/release 释放（限本人 + is_scraped=0）         [crawler:task:write]
    依赖: douban_ids 表 + MySQL 原子 UPDATE

history_routes.py — 任务历史查询
    GET    /admin/task-history          分页历史列表（admin_id/task_type/status/keyword/since/until 过滤）
                                       [crawler:task:read]
    GET    /admin/task-history/<id>     单条详情（含关联失败记录）               [crawler:task:read]
    依赖: TaskHistoryService

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
认证: 所有端点走 JWT（Authorization: Bearer <token>）
      require_permission 装饰器校验权限，无权限 → 403
      get_current_user 校验 token + is_active，未登录 → 401
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from quart import Blueprint

admin_bp = Blueprint("admin", __name__)

from .failure_routes import failure_bp
from .task_routes import task_bp
from .movie_routes import movie_bp
from .review_routes import review_bp
from .user_routes import user_bp
from .status_routes import status_bp
from .history_routes import history_bp
from .log_routes import log_bp
from .infra_routes import infra_bp
from .douban_id_routes import douban_id_bp
from .debug_routes import debug_bp

admin_bp.register_blueprint(failure_bp)
admin_bp.register_blueprint(task_bp)
admin_bp.register_blueprint(movie_bp)
admin_bp.register_blueprint(review_bp)
admin_bp.register_blueprint(user_bp)
admin_bp.register_blueprint(status_bp)
admin_bp.register_blueprint(history_bp)
admin_bp.register_blueprint(log_bp)
admin_bp.register_blueprint(infra_bp)
admin_bp.register_blueprint(douban_id_bp)
admin_bp.register_blueprint(debug_bp)

# 副作用导入（非直接引用）— 供 app.py 通过 `from routes.admin import init_task_failure_service` 访问
from services.task_failure_service import init_task_failure_service
