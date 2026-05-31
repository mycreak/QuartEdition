"""
routes/admin/infra_routes.py

基础设施管理 — 代理池 + Cookie 登录态。

端点（v2 — id 化代理管理）：
    GET    /admin/proxies              分页代理列表（按status/region/keyword过滤）
    POST   /admin/proxies              添加代理
    PATCH  /admin/proxies/<id>         修改代理
    DELETE /admin/proxies/<id>         封禁代理
    POST   /admin/proxies/test         单代理连通性测试
    GET    /admin/proxies/options      精简下拉选项列表
    POST   /admin/proxies/health-check 手动触发全量验证
     GET    /admin/cookies              分页账号列表（按status/keyword过滤）
    POST   /admin/cookies              添加账号
    PATCH  /admin/cookies/<id>         修改账号
    DELETE /admin/cookies/<id>         删除账号
    POST   /admin/cookies/test         测试 Cookie 有效性
    GET    /admin/cookies/options      精简下拉选项列表
    POST   /admin/cookies/<id>/ban     封禁账号
    POST   /admin/cookies/<id>/unban   恢复账号
    GET    /admin/cookies/status       Cookie 状态汇总
    POST   /admin/cookies/replace      替换主账号 Cookie

权限：
    - 代理查看：infra:proxy:read
    - 代理管理：infra:proxy:manage
    - Cookie查看：infra:cookie:read
    - Cookie管理：infra:cookie:manage
    - system:monitor 持有者拥有以上全部
"""

import logging

from quart import Blueprint, jsonify, request, g
from quart_schema import tag
from utils.auth import require_permission
from crawler.proxy import get_proxy_pool, SourceType

logger = logging.getLogger(__name__)

infra_bp = Blueprint("infra_routes", __name__)


# ═══════════════════════════════════════
# 代理管理（v2 — id 化）
# ═══════════════════════════════════════

@infra_bp.route("/proxies", methods=["GET"])
@require_permission("infra:proxy:read")
@tag(["基础设施"])
async def list_proxies():
    """
    分页代理列表。

    查询参数：
        page:      页码（默认 1）
        page_size: 每页条数（默认 20）
        status:    按状态过滤（alive/suspicious/banned，可选）
        region:    按地区过滤（可选）
        keyword:   模糊搜索 host/remark（可选）
    """
    try:
        pool = get_proxy_pool()
    except RuntimeError as e:
        return jsonify({"error": str(e), "items": [], "total": 0, "page": 1, "page_size": 20}), 200

    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    status = request.args.get("status", "").strip()
    region = request.args.get("region", "").strip()
    keyword = request.args.get("keyword", "").strip()

    all_proxies = pool.list_all()
    stats = pool.get_stats()

    # 前端筛选值映射：前端用 enabled/disabled/dead → 后端实际字段
    if status:
        if status == "enabled":
            all_proxies = [p for p in all_proxies if p.get("enabled")]
        elif status == "disabled":
            all_proxies = [p for p in all_proxies if not p.get("enabled")]
        elif status == "dead":
            all_proxies = [p for p in all_proxies if p.get("status") == "suspicious"]
        else:
            all_proxies = [p for p in all_proxies if p.get("status") == status]
    if region:
        all_proxies = [p for p in all_proxies if p.get("region") == region]
    if keyword:
        kw = keyword.lower()
        all_proxies = [
            p for p in all_proxies
            if kw in (p.get("remark") or "").lower() or kw in (p.get("host") or "").lower()
        ]

    total = len(all_proxies)
    start = (page - 1) * page_size
    items = all_proxies[start:start + page_size]

    return jsonify({"items": items, "total": total, "page": page, "page_size": page_size, "stats": stats})


@infra_bp.route("/proxies", methods=["POST"])
@require_permission("infra:proxy:manage")
@tag(["基础设施"])
async def add_proxy():
    """
    添加代理。

    请求体：
        host:     必填
        port:     必填（1-65535）
        username: 可选，认证用户名
        password: 可选，认证密码
        remark:   可选，管理员备注
        region:   可选，地区标识
    """
    try:
        body = await request.get_json()
        host = body.get("host", "").strip()
        port = body.get("port", 0)
        username = (body.get("username") or "").strip()
        password = (body.get("password") or "").strip()
        remark = (body.get("remark") or "").strip()
        region = (body.get("region") or "").strip()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    if not host or not isinstance(port, int) or port < 1 or port > 65535:
        return jsonify({"error": "host 不能为空，port 必须为 1-65535"}), 400

    try:
        pool = get_proxy_pool()
        ok = await pool.add_proxy(
            host=host, port=port,
            source=SourceType.ADMIN,
            username=username, password=password,
            remark=remark, region=region,
        )
        if not ok:
            return jsonify({"error": "代理已存在或在黑名单中"}), 409
        await pool.save_persisted()
        proxy = pool.get_by_key(f"{host}:{port}")
        return jsonify({"success": True, "id": proxy.id if proxy else 0, "key": f"{host}:{port}"}), 201
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@infra_bp.route("/proxies/<int:proxy_id>", methods=["PATCH"])
@require_permission("infra:proxy:manage")
@tag(["基础设施"])
async def update_proxy(proxy_id: int):
    """
    修改代理信息。

    请求体（全部可选，只更新传入的字段）：
        remark:    备注
        username:  认证用户名
        password:  认证密码
        region:    地区
        enabled:   是否启用
        proxy_type: 代理协议
    """
    try:
        body = await request.get_json()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    updatable = ["remark", "username", "password", "region", "enabled", "proxy_type"]
    kwargs = {k: body[k] for k in updatable if k in body}

    if not kwargs:
        return jsonify({"error": "无有效更新字段"}), 400

    try:
        pool = get_proxy_pool()
        ok = await pool.update_proxy(proxy_id, **kwargs)
        if not ok:
            return jsonify({"error": "代理不存在", "code": "NOT_FOUND"}), 404
        await pool.save_persisted()
        return jsonify({"success": True, "id": proxy_id, "message": "更新成功"})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@infra_bp.route("/proxies/<int:proxy_id>", methods=["DELETE"])
@require_permission("infra:proxy:manage")
@tag(["基础设施"])
async def delete_proxy_by_id(proxy_id: int):
    """按 ID 封禁代理。"""
    try:
        pool = get_proxy_pool()
        proxy = pool.get_by_id(proxy_id)
        if proxy is None:
            return jsonify({"error": "代理不存在", "code": "NOT_FOUND"}), 404
        ok = await pool.ban_proxy(proxy.host, proxy.port)
        await pool.save_persisted()
        return jsonify({"success": True, "key": proxy.key, "message": f"代理 {proxy.key} 已封禁"})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@infra_bp.route("/proxies/test", methods=["POST"])
@require_permission("infra:proxy:manage")
@tag(["基础设施"])
async def test_proxy():
    """
    单代理连通性测试。

    请求体（二选一）：
        { "id": 1 }                 按 ID 测试
        { "host": "1.2.3.4", "port": 8080 }  直接测试

    响应：
        { "success": true,  "latency_ms": 234, "exit_ip": "...", "message": "连接成功" }
        { "success": false, "latency_ms": 0,   "exit_ip": "",     "message": "连接超时" }
    """
    try:
        body = await request.get_json()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    import time as _time

    try:
        pool = get_proxy_pool()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    proxy = None
    if "id" in body:
        proxy = pool.get_by_id(body["id"])
    elif "host" in body and "port" in body:
        key = f"{body['host']}:{body['port']}"
        proxy = pool.get_by_key(key)

    if proxy is None:
        host = body.get("host", "")
        port = body.get("port", 0)
        username = (body.get("username") or "").strip()
        password = (body.get("password") or "").strip()
        if not host or not port:
            return jsonify({"error": "代理不存在，且未提供有效的 host/port 参数"}), 404
    else:
        host, port = proxy.host, proxy.port
        username, password = proxy.username, proxy.password

    start = _time.time()

    from quart import current_app
    browser = current_app.browser

    try:
        ok, message = await pool.verify_proxy_browser(
            host, port,
            browser=browser,
            playwright=getattr(current_app, 'playwright', None),
            username=username,
            password=password,
            timeout=15,
        )
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    latency = int((_time.time() - start) * 1000)

    if ok:
        if proxy is not None:
            await pool.report_success(proxy)
            await pool.save_persisted()
        return jsonify({
            "success": True,
            "latency_ms": latency,
            "exit_ip": host,
            "message": message,
        })
    else:
        return jsonify({
            "success": False,
            "latency_ms": latency,
            "exit_ip": "",
            "message": message,
        })


@infra_bp.route("/proxies/options", methods=["GET"])
@require_permission("infra:proxy:read")
@tag(["基础设施"])
async def proxy_options():
    """获取代理下拉选项列表（任务提交页用，仅返回 alive 代理）。"""
    try:
        pool = get_proxy_pool()
        return jsonify({"items": pool.options_list()})
    except RuntimeError as e:
        return jsonify({"error": str(e), "items": []}), 200


@infra_bp.route("/proxies/health-check", methods=["POST"])
@require_permission("infra:proxy:manage")
@tag(["基础设施"])
async def health_check():
    """手动触发全量代理验证（Playwright 真浏览器，非 aiohttp 直连）。"""
    try:
        pool = get_proxy_pool()
        from quart import current_app
        browser = current_app.browser
        result = await pool.health_check(browser=browser, concurrency=2)
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════
# Cookie 登录态管理（多账号 — v2 扩展）
# ═══════════════════════════════════════

def _get_cookie_manager():
    """获取已初始化的 CookieManager 单例。"""
    from crawler.cookie_manager import get_cookie_manager as _getter
    return _getter()


@infra_bp.route("/cookies", methods=["GET"])
@require_permission("infra:cookie:read")
@tag(["基础设施"])
async def list_cookies():
    """
    分页 Cookie 列表。

    查询参数：
        page:      页码（默认 1）
        page_size: 每页条数（默认 20）
        status:    按状态过滤（active/suspicious/banned，可选）
        keyword:   模糊搜索 label/remark（可选）
    """
    try:
        mgr = _get_cookie_manager()
    except RuntimeError as e:
        return jsonify({"error": str(e), "items": [], "total": 0, "page": 1, "page_size": 20}), 503

    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    status = request.args.get("status", "").strip()
    platform = request.args.get("platform", "").strip()
    keyword = request.args.get("keyword", "").strip()

    all_cookies = mgr.list_all()
    stats = mgr.get_stats()

    # 前端筛选值映射：前端用 enabled/disabled → 后端实际字段
    if status:
        if status == "enabled":
            all_cookies = [c for c in all_cookies if c.get("enabled")]
        elif status == "disabled":
            all_cookies = [c for c in all_cookies if not c.get("enabled")]
        else:
            all_cookies = [c for c in all_cookies if c["state"] == status]
    if platform:
        all_cookies = [c for c in all_cookies if c.get("platform") == platform]
    if keyword:
        kw = keyword.lower()
        all_cookies = [
            c for c in all_cookies
            if kw in (c.get("label") or "").lower() or kw in (c.get("remark") or "").lower()
        ]

    total = len(all_cookies)
    start = (page - 1) * page_size
    items = all_cookies[start:start + page_size]

    return jsonify({"items": items, "total": total, "page": page, "page_size": page_size, "stats": stats})


@infra_bp.route("/cookies", methods=["POST"])
@require_permission("infra:cookie:manage")
@tag(["基础设施"])
async def add_cookie():
    """
    添加 Cookie 账号。

    请求体：
        dbcl2:           必填，豆瓣 dbcl2 cookie 值
        allowed_regions: 必填，允许的地区代号列表，如 ["CN"]
        bid:             可选，豆瓣 bid cookie
        label:           可选，账号标签
        remark:          可选，备注
        platform:        可选，平台（默认 douban）
    """
    try:
        body = await request.get_json()
        dbcl2 = (body.get("dbcl2") or "").strip()
        if not dbcl2:
            return jsonify({"error": "dbcl2 不能为空"}), 400
        allowed_regions = body.get("allowed_regions", [])
        if not isinstance(allowed_regions, list) or not allowed_regions:
            return jsonify({"error": "allowed_regions 必须是非空数组"}), 400
        bid = (body.get("bid") or "").strip()
        label = (body.get("label") or "").strip()
        remark = (body.get("remark") or "").strip()
        platform = (body.get("platform") or "douban").strip()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    try:
        mgr = _get_cookie_manager()
        account_id = await mgr.add_account(
            dbcl2=dbcl2,
            allowed_regions=allowed_regions,
            bid=bid,
            label=label,
            remark=remark,
            platform=platform,
        )
        return jsonify({"success": True, "account_id": account_id}), 201
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@infra_bp.route("/cookies/<account_id>", methods=["PATCH"])
@require_permission("infra:cookie:manage")
@tag(["基础设施"])
async def update_cookie(account_id: str):
    """
    修改 Cookie 账号。

    请求体（全部可选）：
        label:           账号标签
        remark:          备注
        platform:        平台
        enabled:         是否启用
        allowed_regions: 允许的地区列表
    """
    try:
        body = await request.get_json()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    updatable = ["label", "remark", "platform", "enabled", "allowed_regions", "bound_admin_ids"]
    kwargs = {k: body[k] for k in updatable if k in body}

    if not kwargs:
        return jsonify({"error": "无有效更新字段"}), 400

    try:
        mgr = _get_cookie_manager()
        ok = await mgr.update_account(account_id, **kwargs)
        if not ok:
            return jsonify({"error": "账号不存在", "code": "NOT_FOUND"}), 404
        return jsonify({"success": True, "account_id": account_id, "message": "更新成功"})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@infra_bp.route("/cookies/<account_id>", methods=["DELETE"])
@require_permission("infra:cookie:manage")
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


@infra_bp.route("/cookies/test", methods=["POST"])
@require_permission("infra:cookie:manage")
@tag(["基础设施"])
async def test_cookie():
    """
    测试 Cookie 有效性（Playwright 真浏览器 + 代理 + IP 后验）。

    请求体：
        { "id": "main" }                             仅 Cookie（自动选可用代理）
        { "id": "main", "proxy_host": "1.2.3.4", "proxy_port": 8080 }  指定代理
        { "id": "main", "proxy_host": "1.2.3.4", "proxy_port": 8080, "proxy_username": "u", "proxy_password": "p" }

    响应：
        { "success": true,  "verdict": "ok",                 "message": "Cookie 有效" }
        { "success": false, "verdict": "cookie_expired",     "message": "Cookie 已过期" }
        { "success": false, "verdict": "ip_blocked",         "message": "IP 不可用" }
        { "success": false, "verdict": "ip_pass_cookie_unknown", "message": "IP 正常但 Cookie 不确定" }

    IP 后验：当代理疑似不可用时自动转入代理验证，失败时同步更新代理状态机。
    """
    try:
        body = await request.get_json()
        account_id = (body.get("id") or "").strip()
        if not account_id:
            return jsonify({"error": "id 不能为空"}), 400

        proxy_host = (body.get("proxy_host") or "").strip()
        proxy_port = body.get("proxy_port", 0) or 0
        proxy_username = (body.get("proxy_username") or "").strip()
        proxy_password = (body.get("proxy_password") or "").strip()
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    try:
        from quart import current_app
        browser = current_app.browser
        mgr = _get_cookie_manager()
        result = await mgr.verify_account_v2(
            account_id,
            browser=browser,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_username=proxy_username,
            proxy_password=proxy_password,
        )
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@infra_bp.route("/cookies/options", methods=["GET"])
@require_permission("infra:cookie:read")
@tag(["基础设施"])
async def cookie_options():
    """获取 Cookie 下拉选项列表（任务提交页用，仅 active + enabled + 按 bound_admin_ids 过滤）。"""
    try:
        mgr = _get_cookie_manager()
        return jsonify({"items": mgr.options_list(admin_id=g.user_id)})
    except RuntimeError as e:
        return jsonify({"error": str(e), "items": []}), 200


@infra_bp.route("/cookies/<account_id>/ban", methods=["POST"])
@require_permission("infra:cookie:manage")
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
@require_permission("infra:cookie:manage")
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
@require_permission("infra:cookie:read")
@tag(["基础设施"])
async def cookie_status():
    """Cookie 汇总状态。"""
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
@require_permission("infra:cookie:manage")
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
