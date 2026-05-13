"""
routes/__init__.py

QuartEdition 全路由目录总览。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
蓝图注册（均在 app.py 的 startup 钩子中完成）：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  app.register_blueprint(auth_bp,  url_prefix="/auth")     # public/__init__.py (直接导出)
  app.register_blueprint(user_bp,  url_prefix="/user")     # user/__init__.py (父蓝图)
  app.register_blueprint(admin_bp, url_prefix="/admin")    # admin/__init__.py (父蓝图)
  register_websocket_routes(app, ws_manager)               # websocket.py → /ws/notifications

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
目录结构：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

routes/
├── public/                       公开（无需登录）
│   ├── __init__.py               重导出 auth_routes 蓝图
│   └── auth_routes.py            POST /auth/login  POST /auth/register  GET /auth/me
│   ↓ 详见 routes/public/__init__.py

├── user/                         用户端（需 JWT，只看上架）— 8 端点
│   ├── __init__.py               蓝图注册枢纽（文档在此）
│   ├── filter_routes.py          过滤器数据包
│   ├── movie_routes.py           电影浏览
│   ├── genre_routes.py           类型列表+统计
│   └── review_routes.py          评论浏览
│   ↓ 详见 routes/user/__init__.py

├── admin/                        管理端（需 JWT + 权限，看全部）— 16 端点
│   ├── __init__.py               蓝图注册枢纽（文档在此）
│   ├── failure_routes.py         失败任务认领（6）
│   ├── task_routes.py            任务提交+进度（2）
│   ├── movie_routes.py           电影管理（2）
│   ├── review_routes.py          评论管理（2）
│   ├── user_routes.py            用户管理（3）
│   └── status_routes.py          系统状态（1）
│   ↓ 详见 routes/admin/__init__.py

└── websocket.py                  WebSocket
    /ws/notifications             失败/成功/心跳/系统状态实时推送

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
认证模型：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  public:     无鉴权 — 只有登录和注册
  user:       JWT（@require_login）— is_published=True 限定
  admin:      JWT + @require_permission — 无 is_published 限定
  WebSocket:  当前 user_id 查询参数，待改为 JWT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
