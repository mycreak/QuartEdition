"""
routes/websocket.py

WebSocket 路由。
管理员通过 /ws/notifications 建立长连接，接收任务失败推送。
"""

import asyncio
import logging

from quart import websocket

logger = logging.getLogger(__name__)


async def _resolve_admin_id() -> int | None:
    """
    从当前 WebSocket 请求的 JWT token 参数中解析 admin_id。

    流程：
        1. 取 ?token=<JWT>
        2. AuthService.verify_token(token) → user_id
        3. 校验用户未被禁用
        4. 返回 user_id 或 None

    替换了旧的 ?user_id= 明文参数。
    """
    token = websocket.args.get("token", "")
    if not token:
        return None

    from services.auth_service import _get_auth_service
    svc = _get_auth_service()
    user_id = svc.verify_token(token)
    if user_id is None:
        return None

    user = await svc.get_user(user_id)
    if not user or not user.is_active:
        return None

    return user_id


def register_websocket_routes(app, ws_manager):
    """
    注册 WebSocket 路由到 Quart 应用。

    Args:
        app: Quart 应用实例。
        ws_manager: WebSocketManager 实例。
    """
    @app.websocket('/ws/notifications')
    async def ws_notifications():
        """
        管理员通知 WebSocket 端点。

        连接建立后从查询参数获取 token，解析出 admin_id，
        注册到 ws_manager，保持长连接直到断开。
        """
        admin_id = None
        resolved_ws = None
        try:
            admin_id = await _resolve_admin_id()
            if admin_id is None:
                await websocket.close(4001, "认证失败")
                return

            # 解析 LocalProxy 为真实 WebSocket 对象，避免 Manager 依赖 Werkzeug 私有 API
            resolved_ws = websocket._get_current_object()
            await ws_manager.register(admin_id, resolved_ws)
            logger.debug(f"WebSocket 已连接: admin_id={admin_id}")

            while True:
                data = await websocket.receive()
                if data == "ping":
                    await websocket.send("pong")

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(f"WebSocket 异常断开: admin_id={admin_id}")
        finally:
            if admin_id is not None and resolved_ws is not None:
                await ws_manager.unregister(admin_id, resolved_ws)
