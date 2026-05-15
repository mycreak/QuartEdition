"""
routes/admin/debug_routes.py

调试工具 — 模拟 WebSocket 推送事件（仅开发/演示用）。

端点：
    POST /admin/debug/ws-event — 推送 mock 事件到当前管理员的 WS 连接

权限：system:monitor
"""

import json
import logging

from quart import Blueprint, request, jsonify, g
from quart_schema import tag
from utils.auth import require_permission

logger = logging.getLogger(__name__)

debug_bp = Blueprint("debug_routes", __name__)


def _get_ws_manager():
    """从 current_app 获取已初始化的 WebSocketManager。"""
    from quart import current_app
    return current_app.ws_manager


@debug_bp.route("/debug/ws-event", methods=["POST"])
@require_permission("system:monitor")
@tag(["调试工具"])
async def push_mock_event():
    """
    推送 mock WebSocket 事件，用于演示/验证 WS 通信。

    请求体：{ "event_type": "task_failure" | "worker_crash" }

    触发效果：
        task_failure → 当前管理员前端弹出 ElNotification（红色"任务失败"）
        worker_crash → 全体管理员前端弹出 ElNotification（黄色"Worker 崩溃"）

    仅推 WS，不写数据库，不影响任何系统状态。

    响应 200：{ "success": true, "event_type": "...", "message": "已推送到 N 个连接" }
    响应 400：{ "error": "..." }
    """
    try:
        body = await request.get_json()
        event_type = (body.get("event_type") or "").strip()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    if event_type not in ("task_failure", "worker_crash"):
        return jsonify({"error": "event_type 必须是 task_failure 或 worker_crash"}), 400

    ws_manager = _get_ws_manager()

    if event_type == "task_failure":
        mock_msg = {
            "type": "task_failure",
            "event_type": "failure",
            "task": json.dumps({
                "type": "movie_scrape_task",
                "douban_id": "1292052",
                "cookie_id": "main",
                "proxy_key": "1.2.3.4:8080",
            }, ensure_ascii=False),
            "reason": "[调试] 模拟失败：连接超时 (mock timeout)",
            "timestamp": "2026-05-15T12:00:00+08:00",
        }
        await ws_manager.push(g.user_id, mock_msg)
        logger.info(f"[调试] task_failure 已推送给 admin_id={g.user_id}")
        return jsonify({
            "success": True,
            "event_type": "task_failure",
            "message": f"task_failure 已推送到 admin_id={g.user_id} 的所有连接",
        })

    else:  # worker_crash
        mock_msg = {
            "type": "worker_crash",
            "dead": [0, 2],
            "alive": 3,
            "expected": 5,
            "crashed_total": 2,
            "action": "[调试] 模拟：正在自动重启...",
        }
        await ws_manager.broadcast(mock_msg)
        logger.info("[调试] worker_crash 已广播到全体管理员")
        return jsonify({
            "success": True,
            "event_type": "worker_crash",
            "message": f"worker_crash 已广播到全体管理员 (共 {ws_manager.total_connections} 个 WS 连接)",
        })
