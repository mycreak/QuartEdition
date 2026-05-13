"""
routes/admin/infra_routes.py

基础设施管理 — 代理池 + Cookie 登录态。

端点：
    GET    /admin/proxies              代理列表
    POST   /admin/proxies              添加代理
    DELETE /admin/proxies/<host>/<port> 删除/封禁代理
    POST   /admin/proxies/health-check 手动触发全量验证
    GET    /admin/cookies              账号列表
    POST   /admin/cookies              添加账号
    DELETE /admin/cookies/<id>         删除账号
    POST   /admin/cookies/<id>/ban     封禁账号
    POST   /admin/cookies/<id>/unban   恢复账号
    GET    /admin/cookies/status       Cookie 状态汇总
    POST   /admin/cookies/replace      替换主账号 Cookie

权限：全部需要 system:monitor
"""

import logging

from quart import Blueprint, jsonify, request
from quart_schema import tag
from utils.auth import require_permission
from crawler.proxy import get_proxy_pool, SourceType

logger = logging.getLogger(__name__)

infra_bp = Blueprint("infra_routes", __name__)


# ═══════════════════════════════════════
# 代理管理
# ═══════════════════════════════════════

@infra_bp.route("/proxies", methods=["GET"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def list_proxies():
    """代理池列表（含状态/来源/成功率/延迟）。"""
    try:
        pool = get_proxy_pool()
    except RuntimeError as e:
        return jsonify({"error": str(e), "proxies": [], "stats": {}}), 200

    proxies = pool.list_all()
    stats = pool.get_stats()
    return jsonify({"proxies": proxies, "stats": stats})


@infra_bp.route("/proxies", methods=["POST"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def add_proxy():
    """添加代理。"""
    try:
        body = await request.get_json()
        host = body.get("host", "").strip()
        port = body.get("port", 0)
        region = body.get("region", "")
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    if not host or not isinstance(port, int) or port < 1 or port > 65535:
        return jsonify({"error": "host 不能为空，port 必须为 1-65535"}), 400

    try:
        pool = get_proxy_pool()
        ok = await pool.add_proxy(host, port, source=SourceType.ADMIN, region=region)
        if not ok:
            return jsonify({"error": "代理已存在或在黑名单中"}), 409
        await pool.save_persisted()
        return jsonify({"success": True, "key": f"{host}:{port}"}), 201
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@infra_bp.route("/proxies/<host>/<int:port>", methods=["DELETE"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def delete_proxy(host: str, port: int):
    """封禁/删除代理。"""
    try:
        pool = get_proxy_pool()
        ok = await pool.ban_proxy(host, port)
        if not ok:
            return jsonify({"error": "代理不在池中"}), 404
        await pool.save_persisted()
        return jsonify({"success": True, "key": f"{host}:{port}"})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@infra_bp.route("/proxies/health-check", methods=["POST"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def health_check():
    """手动触发全量代理验证。"""
    try:
        pool = get_proxy_pool()
        result = await pool.health_check(concurrency=10)
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════
# Cookie 登录态管理（多账号）
# ═══════════════════════════════════════

def _get_cookie_manager():
    """获取已初始化的 CookieManager 单例。"""
    from crawler.cookie_manager import get_cookie_manager as _getter
    return _getter()


@infra_bp.route("/cookies", methods=["GET"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def list_cookies():
    """列出所有 Cookie 账号（状态/region/使用统计）。"""
    try:
        mgr = _get_cookie_manager()
        return jsonify({"items": mgr.list_all(), "stats": mgr.get_stats()})
    except RuntimeError as e:
        return jsonify({"error": str(e), "items": [], "stats": {}}), 503


@infra_bp.route("/cookies", methods=["POST"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def add_cookie():
    """
    添加 Cookie 账号。

    请求体：
        dbcl2:           必填，豆瓣 dbcl2 cookie 值
        allowed_regions: 必填，允许的地区代号列表，如 ["CN", "JP"]
        bid:             可选，豆瓣 bid cookie
        label:           可选，账号标签（如 "日本备用"）
    """
    try:
        body = await request.get_json()
        dbcl2 = (body.get("dbcl2") or "").strip()
        if not dbcl2:
            return jsonify({"error": "dbcl2 不能为空"}), 400
        allowed_regions = body.get("allowed_regions", [])
        if not isinstance(allowed_regions, list) or not allowed_regions:
            return jsonify({"error": "allowed_regions 必须是非空数组，如 [\"CN\"]"}), 400
        bid = (body.get("bid") or "").strip()
        label = (body.get("label") or "").strip()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    try:
        mgr = _get_cookie_manager()
        account_id = await mgr.add_account(
            dbcl2=dbcl2,
            allowed_regions=allowed_regions,
            bid=bid,
            label=label,
        )
        return jsonify({"success": True, "account_id": account_id}), 201
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@infra_bp.route("/cookies/<account_id>", methods=["DELETE"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def delete_cookie(account_id: str):
    """删除 Cookie 账号。"""
    try:
        mgr = _get_cookie_manager()
        ok = await mgr.remove_account(account_id)
        if ok:
            return jsonify({"success": True, "message": f"账号 {account_id} 已删除"})
        return jsonify({"error": "账号不存在", "code": "NOT_FOUND"}), 404
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@infra_bp.route("/cookies/<account_id>/ban", methods=["POST"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def ban_cookie(account_id: str):
    """手动封禁 Cookie 账号。"""
    try:
        mgr = _get_cookie_manager()
        ok = await mgr.set_account_state(account_id, "banned")
        if ok:
            return jsonify({"success": True, "message": f"账号 {account_id} 已封禁"})
        return jsonify({"error": "账号不存在", "code": "NOT_FOUND"}), 404
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@infra_bp.route("/cookies/<account_id>/unban", methods=["POST"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def unban_cookie(account_id: str):
    """恢复 Cookie 账号（banned → active）。"""
    try:
        mgr = _get_cookie_manager()
        ok = await mgr.set_account_state(account_id, "active")
        if ok:
            return jsonify({"success": True, "message": f"账号 {account_id} 已恢复"})
        return jsonify({"error": "账号不存在", "code": "NOT_FOUND"}), 404
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@infra_bp.route("/cookies/status", methods=["GET"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def cookie_status():
    """Cookie 汇总状态 — 委托 CookieManager。"""
    try:
        mgr = _get_cookie_manager()
        stats = mgr.get_stats()
        accounts = mgr.list_all()
        has_dbcl2 = any(a.get("dbcl2_preview") for a in accounts)
        return jsonify({
            "stats": stats,
            "accounts": accounts,
            "has_dbcl2": has_dbcl2,
            "cookie_valid": stats.get("active", 0) > 0,
        })
    except RuntimeError as e:
        return jsonify({"error": str(e), "stats": {}, "accounts": [], "has_dbcl2": False, "cookie_valid": False}), 503


@infra_bp.route("/cookies/replace", methods=["POST"])
@require_permission("system:monitor")
@tag(["基础设施"])
async def replace_cookie():
    """
    替换主账号 Cookie（兼容旧版单文件模式）。

    内部委托 CookieManager.add_account("main")，自动迁移到多账号体系。
    """
    try:
        body = await request.get_json()
        dbcl2 = (body.get("dbcl2") or "").strip()
        if not dbcl2:
            return jsonify({"error": "dbcl2 不能为空"}), 400
        bid = (body.get("bid") or "").strip()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    try:
        mgr = _get_cookie_manager()
        account_id = await mgr.add_account(
            dbcl2=dbcl2,
            allowed_regions=["CN"],
            bid=bid,
            label="主账号",
            account_id="main",
        )
        logger.info(f"Cookie 已替换: account_id={account_id} dbcl2={dbcl2[:8]}...")
        return jsonify({"success": True, "account_id": account_id})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
