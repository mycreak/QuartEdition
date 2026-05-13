"""
routes/public/__init__.py

认证路由入口。由 app.py 以 url_prefix="/auth" 挂载。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

auth_routes.py — 认证（3 端点）
    POST   /auth/login               用户名+密码 → JWT        【公开，无鉴权】
    POST   /auth/register            创建普通用户（无权限）     【公开，无鉴权】
    GET    /auth/me                  当前用户信息 + 权限列表    【需 JWT 但无权限要求】
    依赖: AuthService

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
与其他包的关系：
    公开端只有登录和注册。登录后根据权限分流：
      - 管理员（有任意管理权限） → /admin/*
      - 普通用户（无管理权限）   → /user/*
    websocket.py 独立于包外，由 app.py 直接注册。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from .auth_routes import auth_bp