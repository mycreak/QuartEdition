"""
utils/websocket.py

WebSocket 连接管理器。

维护 admin_id → 多个 WebSocket 连接的映射。
一个管理员可能同时打开多个浏览器标签页，所以用 set 存储。
Monitor 不直接持有 WebSocket，而是通过此管理器推送消息。
"""

import logging

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    WebSocket 连接管理器。

    register/unregister 期望接收真实的 websocket 对象（已在调用方解析好），
    不再依赖 Werkzeug LocalProxy._get_current_object() 私有 API。

    使用示例：
        ws_manager = WebSocketManager()
        await ws_manager.register(admin_id, websocket)
        await ws_manager.push(admin_id, {"type": "task_failure", ...})
    """

    def __init__(self):
        self._connections: dict[int, set] = {}

    @property
    def total_connections(self) -> int:
        """当前总连接数。"""
        return sum(len(s) for s in self._connections.values())

    async def register(self, admin_id: int, websocket) -> None:
        """注册连接 — websocket 必须是已解析的真实对象。"""
        if admin_id not in self._connections:
            self._connections[admin_id] = set()
        self._connections[admin_id].add(websocket)
        logger.debug(f"WebSocket 注册: admin_id={admin_id}, 当前连接数={self.total_connections}")

    async def unregister(self, admin_id: int, websocket) -> None:
        """注销连接 — websocket 必须是已解析的真实对象。"""
        conn_set = self._connections.get(admin_id)
        if conn_set:
            conn_set.discard(websocket)
            if not conn_set:
                del self._connections[admin_id]
        logger.debug(f"WebSocket 注销: admin_id={admin_id}, 当前连接数={self.total_connections}")

    async def push(self, admin_id: int, message: dict) -> None:
        """
        向指定管理员推送消息。
        遍历该管理员的所有连接逐一发送，发送失败的连接自动移除。
        """
        conn_set = self._connections.get(admin_id)
        if not conn_set:
            logger.debug(f"WebSocket 推送跳过: admin_id={admin_id} 无活跃连接")
            return

        failed = set()
        for ws in list(conn_set):  # 迭代副本，discard 时不影响迭代安全
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning(f"WebSocket 推送失败: admin_id={admin_id}，已移除")
                failed.add(ws)

        for ws in failed:
            conn_set.discard(ws)
        if not conn_set:
            self._connections.pop(admin_id, None)  # del 改为 pop 防并发残留

    async def broadcast(self, message: dict) -> None:
        """
        向所有连接的管理员广播消息。
        """
        for admin_id in list(self._connections.keys()):
            await self.push(admin_id, message)


def init_ws_manager() -> WebSocketManager:
    """初始化全局 WebSocket 管理器单例。"""
    return WebSocketManager()
