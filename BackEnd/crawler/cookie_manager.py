"""
crawler/cookie_manager.py

多账号 Cookie 管理器。

职责：
    1. 从 data/cookies/metadata.json 加载账号注册表
    2. 按 proxy.region 自动匹配最优账号
    3. 维护账号状态机（active ↔ suspicious → banned）
    4. 从旧版 douban_storage.json 自动迁移
    5. 提供管理 API 所需的状态查询和增删改接口

存储布局：
    data/cookies/
      ├── metadata.json              # 账号注册表
      ├── account_main.json          # Playwright storage_state
      ├── account_backup.json        # Playwright storage_state
      └── ...

约束：
    同一 Cookie 限定 IP 属地 — Account.allowed_regions 与 proxy.region 匹配
    地区内 1 对 N — 同 region 内多个 proxy 可绑定同 Cookie
    每 IP 只服务一个 Cookie — 由 ProxyPool 轮转自然保证
"""

import json
import logging
import os
import asyncio
import shutil
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

_COOKIES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data", "cookies",
)
_LEGACY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data", "douban_storage.json",
)
_METADATA_FILE = os.path.join(_COOKIES_DIR, "metadata.json")

_ACCOUNT_STATES = ("active", "suspicious", "banned")
_FAIL_THRESHOLD_ACCOUNT_BAN = 2


def _write_json_metadata(path: str, data: dict) -> None:
    """纯同步 I/O，供 asyncio.to_thread 在后台线程执行。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@dataclass
class Account:
    """
    单个豆瓣账号。

    v2 — 新增 remark/platform/enabled/usage_count，供管理端展示和过滤。
    """
    id: str
    label: str = ""
    file: str = ""
    allowed_regions: List[str] = field(default_factory=list)
    dbcl2_preview: str = ""
    saved_at: str = ""
    state: str = "active"
    last_used_at: float = 0.0
    fail_count: int = 0
    success_count: int = 0
    remark: str = ""
    platform: str = "douban"
    enabled: bool = True
    usage_count: int = 0

    @property
    def storage_state(self) -> dict:
        """延迟加载 Playwright storage_state。"""
        filepath = os.path.join(_COOKIES_DIR, self.file) if self.file else ""
        if not filepath or not os.path.exists(filepath):
            return {}
        with open(filepath, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw.get("playwright_state", raw)


class CookieManager:
    """
    多账号 Cookie 管理器。

    输入：无（从 data/cookies/ 自动加载）
    副作用：读取/写入 metadata.json 和账号 JSON 文件
    """

    def __init__(self, cookies_dir: str = _COOKIES_DIR):
        self._cookies_dir = cookies_dir
        self._accounts: Dict[str, Account] = {}
        self._loaded = False

    def _metadata_path(self) -> str:
        return os.path.join(self._cookies_dir, "metadata.json")

    # ── 加载 / 迁移 ──

    async def load(self) -> int:
        """
        从 metadata.json 加载账号列表。
        如果目录不存在且有旧版 douban_storage.json → 自动迁移。

        输出：加载的账号数
        副作用：填充 self._accounts
        """
        if self._loaded:
            return len(self._accounts)

        os.makedirs(self._cookies_dir, exist_ok=True)

        if not os.path.exists(self._metadata_path()):
            if os.path.exists(_LEGACY_FILE):
                await self._migrate_legacy()
            else:
                await self._save_metadata()
                self._loaded = True
                return 0

        try:
            with open(self._metadata_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"metadata.json 解析失败: {e}")
            await self._save_metadata()
            self._loaded = True
            return 0

        self._accounts.clear()
        for item in data.get("accounts", []):
            acc = Account(
                id=item.get("id", ""),
                label=item.get("label", ""),
                file=item.get("file", ""),
                allowed_regions=item.get("allowed_regions", []),
                dbcl2_preview=item.get("dbcl2_preview", ""),
                saved_at=item.get("saved_at", ""),
                state=item.get("state", "active"),
                last_used_at=item.get("last_used_at", 0.0),
                fail_count=item.get("fail_count", 0),
                success_count=item.get("success_count", 0),
                remark=item.get("remark", ""),
                platform=item.get("platform", "douban"),
                enabled=item.get("enabled", True),
                usage_count=item.get("usage_count", 0),
            )
            if acc.id:
                self._accounts[acc.id] = acc

        self._loaded = True
        logger.info(f"CookieManager 已加载 {len(self._accounts)} 个账号")
        return len(self._accounts)

    async def _migrate_legacy(self):
        """从旧版 douban_storage.json 迁移到 data/cookies/account_main.json。"""
        logger.info(f"检测到旧版 {_LEGACY_FILE}，自动迁移...")
        try:
            os.makedirs(self._cookies_dir, exist_ok=True)
            dest = os.path.join(self._cookies_dir, "account_main.json")
            shutil.copy2(_LEGACY_FILE, dest)

            with open(_LEGACY_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            playwright_state = raw.get("playwright_state", raw)
            cookies_list = playwright_state.get("cookies", [])
            dbcl2 = ""
            for c in cookies_list:
                if c.get("name") == "dbcl2":
                    dbcl2 = c.get("value", "")
                    break

            acc = Account(
                id="main",
                label="主账号",
                file="account_main.json",
                allowed_regions=["CN"],
                dbcl2_preview=dbcl2[:8] + "..." if dbcl2 else "",
                saved_at=raw.get("saved_at", ""),
                state="active",
            )
            self._accounts["main"] = acc
            await self._save_metadata()
            logger.info(f"迁移完成: {_LEGACY_FILE} → {dest}")
        except Exception as e:
            logger.warning(f"迁移失败: {e}")

    async def _save_metadata(self):
        """持久化 metadata.json（通过 asyncio.to_thread 避免阻塞事件循环）。"""
        data = {
            "version": 1,
            "accounts": [
                {
                    "id": a.id,
                    "label": a.label,
                    "file": a.file,
                    "allowed_regions": a.allowed_regions,
                    "dbcl2_preview": a.dbcl2_preview,
                    "saved_at": a.saved_at,
                    "state": a.state,
                    "last_used_at": a.last_used_at,
                    "fail_count": a.fail_count,
                    "success_count": a.success_count,
                    "remark": a.remark,
                    "platform": a.platform,
                    "enabled": a.enabled,
                    "usage_count": a.usage_count,
                }
                for a in self._accounts.values()
            ],
        }
        os.makedirs(self._cookies_dir, exist_ok=True)
        await asyncio.to_thread(_write_json_metadata, self._metadata_path(), data)

    # ── 选择 ──

    def select(self, region: str) -> Optional[Account]:
        """
        按地区选择一个活跃账号（最近最少使用策略）。

        输入：region — 代理的地区标识（如 "CN"）
        输出：Account 或 None（降级游客模式）
        """
        candidates = [
            a for a in self._accounts.values()
            if region in a.allowed_regions and a.state == "active"
        ]
        if not candidates:
            logger.debug(f"CookieManager.select: region={region} 无匹配账号")
            return None
        candidates.sort(key=lambda a: a.last_used_at)
        return candidates[0]

    # ── 状态上报 ──

    async def report_success(self, account_id: str):
        """
        上报账号使用成功。

        输入：account_id
        副作用：last_used_at + success_count + fail_count 归零 + 可疑恢复
        """
        acc = self._accounts.get(account_id)
        if not acc:
            return
        acc.last_used_at = _time.time()
        acc.success_count += 1
        acc.usage_count += 1
        acc.fail_count = 0
        if acc.state == "suspicious":
            acc.state = "active"
            logger.info(f"账号恢复: {account_id} (suspicious → active)")
        await self._save_metadata()

    async def report_failure(self, account_id: str):
        """
        上报账号使用失败。

        输入：account_id
        副作用：fail_count++，推进状态机（active→suspicious→banned）
        """
        acc = self._accounts.get(account_id)
        if not acc:
            return
        acc.last_used_at = _time.time()
        acc.fail_count += 1
        if acc.fail_count >= _FAIL_THRESHOLD_ACCOUNT_BAN:
            acc.state = "banned"
            logger.warning(f"账号已封禁: {account_id} (连续失败 {acc.fail_count} 次)")
        elif acc.fail_count == 1:
            acc.state = "suspicious"
            logger.debug(f"账号标记为可疑: {account_id}")
        await self._save_metadata()

    # ── 统计 ──

    def get_stats(self) -> dict:
        """{total, active, suspicious, banned, by_region}。"""
        stats = {"total": len(self._accounts), "active": 0, "suspicious": 0, "banned": 0, "by_region": {}}
        for a in self._accounts.values():
            stats[a.state] = stats.get(a.state, 0) + 1
            for r in a.allowed_regions:
                stats["by_region"][r] = stats["by_region"].get(r, 0) + 1
        return stats

    def list_all(self) -> list[dict]:
        """所有账号详情，时间戳转为 ISO 字符串对齐前端。"""
        def _ts_iso(ts: float) -> str:
            if not ts or ts <= 0:
                return ""
            return datetime.fromtimestamp(ts).isoformat()

        return [
            {
                "id": a.id,
                "label": a.label,
                "remark": a.remark,
                "platform": a.platform,
                "enabled": a.enabled,
                "allowed_regions": a.allowed_regions,
                "dbcl2_preview": a.dbcl2_preview,
                "saved_at": a.saved_at,
                "state": a.state,
                "last_used_at": _ts_iso(a.last_used_at),
                "usage_count": a.usage_count,
                "fail_count": a.fail_count,
                "success_count": a.success_count,
            }
            for a in self._accounts.values()
        ]

    def options_list(self) -> list[dict]:
        """
        供管理端下拉选择器使用的精简列表（仅 active + enabled 账号）。

        输出：[{id, label, platform, allowed_regions}, ...]
        """
        return [
            {
                "id": a.id,
                "label": a.label,
                "platform": a.platform,
                "allowed_regions": a.allowed_regions,
            }
            for a in self._accounts.values()
            if a.state == "active" and a.enabled
        ]

    # ── 增删改 ──

    async def add_account(
        self,
        dbcl2: str,
        allowed_regions: List[str],
        bid: str = "",
        label: str = "",
        remark: str = "",
        platform: str = "douban",
        account_id: str = "",
    ) -> str:
        """
        新增账号。

        输入：dbcl2, allowed_regions, bid（可选）, label（可选）, remark（可选）, platform（可选）, account_id（可选）
        输出：新建的 account_id
        副作用：写入 metadata.json + account_xxx.json
        """
        CST = timezone(timedelta(hours=8))

        if not account_id:
            import uuid
            account_id = f"account_{uuid.uuid4().hex[:8]}"

        cookies = [
            {
                "name": "dbcl2",
                "value": dbcl2,
                "domain": ".douban.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            },
        ]
        if bid:
            cookies.insert(0, {
                "name": "bid",
                "value": bid,
                "domain": ".douban.com",
                "path": "/",
                "httpOnly": False,
                "secure": False,
                "sameSite": "None",
            })

        saved_at = datetime.now(CST).isoformat()
        wrapper = {
            "saved_at": saved_at,
            "playwright_state": {"cookies": cookies, "origins": []},
        }

        file_name = f"{account_id}.json"
        filepath = os.path.join(self._cookies_dir, file_name)
        os.makedirs(self._cookies_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(wrapper, f, ensure_ascii=False, indent=2)

        acc = Account(
            id=account_id,
            label=label or account_id,
            file=file_name,
            allowed_regions=allowed_regions,
            dbcl2_preview=dbcl2[:8] + "...",
            saved_at=saved_at,
            state="active",
            remark=remark,
            platform=platform,
        )
        self._accounts[account_id] = acc
        await self._save_metadata()
        logger.info(f"账号已添加: id={account_id} label={acc.label} regions={allowed_regions}")
        return account_id

    async def remove_account(self, account_id: str) -> bool:
        """
        删除账号。

        输入：account_id
        输出：True=已删除，False=不存在
        副作用：删除 JSON 文件 + metadata
        """
        acc = self._accounts.pop(account_id, None)
        if not acc:
            return False
        filepath = os.path.join(self._cookies_dir, acc.file) if acc.file else ""
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        await self._save_metadata()
        logger.info(f"账号已删除: {account_id}")
        return True

    async def update_account(self, account_id: str, **kwargs) -> bool:
        """
        按 ID 更新账号属性。

        输入：account_id + 任意关键字参数
             可更新字段: label, remark, platform, enabled, allowed_regions
        输出：True=成功, False=不存在
        """
        acc = self._accounts.get(account_id)
        if acc is None:
            return False
        updatable = {"label", "remark", "platform", "enabled", "allowed_regions"}
        for field, value in kwargs.items():
            if field in updatable:
                setattr(acc, field, value)
        await self._save_metadata()
        logger.info(f"账号已更新: {account_id} fields={list(kwargs.keys())}")
        return True

    async def verify_account(self, account_id: str) -> dict:
        """
        验证 Cookie 账号是否仍有效（通过访问豆瓣检测是否被重定向到登录页）。

        输入：account_id
        输出：{"success": bool, "message": str, "error_type": str, "cookies_count": int}
        """
        acc = self._accounts.get(account_id)
        if acc is None:
            return {"success": False, "message": "账号不存在", "error_type": "NotFound"}

        try:
            import aiohttp
        except ImportError:
            return {"success": False, "message": "aiohttp 未安装", "error_type": "ImportError"}

        try:
            from yarl import URL
        except ImportError:
            return {"success": False, "message": "yarl 未安装（aiohttp 依赖缺失）", "error_type": "ImportError"}

        storage = acc.storage_state
        cookies_list = storage.get("cookies", [])

        try:
            jar = aiohttp.CookieJar()
            for c in cookies_list:
                jar.update_cookies(
                    {c["name"]: c.get("value", "")},
                    URL("https://movie.douban.com"),
                )
            async with aiohttp.ClientSession(cookie_jar=jar) as session:
                async with session.get(
                    "https://movie.douban.com/",
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers={"User-Agent": "Mozilla/5.0"},
                    allow_redirects=False,
                ) as resp:
                    if resp.status in (301, 302):
                        location = resp.headers.get("Location", "")
                        if "login" in location.lower():
                            return {
                                "success": False,
                                "message": "Cookie 已过期，被重定向到登录页",
                                "error_type": "CookieExpired",
                                "cookies_count": len(cookies_list),
                            }
                    if resp.status == 200:
                        return {
                            "success": True,
                            "message": "Cookie 有效，账号正常",
                            "cookies_count": len(cookies_list),
                        }
                    return {
                        "success": False,
                        "message": f"异常状态码: {resp.status}",
                        "error_type": "UnexpectedStatus",
                        "cookies_count": len(cookies_list),
                    }
        except aiohttp.ClientError as e:
            return {
                "success": False,
                "message": f"HTTP 请求失败: {e}",
                "error_type": type(e).__name__,
                "cookies_count": len(cookies_list),
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"验证异常: {type(e).__name__}: {e}",
                "error_type": type(e).__name__,
                "cookies_count": len(cookies_list),
            }

    async def set_account_state(self, account_id: str, state: str) -> bool:
        """
        管理员手动设置账号状态。

        输入：account_id, state（active / banned）
        输出：True=成功，False=账号不存在
        """
        if state not in _ACCOUNT_STATES:
            raise ValueError(f"state 必须是 {_ACCOUNT_STATES} 之一，收到: {state}")
        acc = self._accounts.get(account_id)
        if not acc:
            return False
        old_state = acc.state
        acc.state = state
        if state == "active":
            acc.fail_count = 0
        await self._save_metadata()
        logger.info(f"账号状态变更: {account_id} ({old_state} → {state})")
        return True

    def get(self, account_id: str) -> Optional[Account]:
        """按 ID 获取单账号。"""
        return self._accounts.get(account_id)


# ── 模块级单例 ──

_instance: Optional[CookieManager] = None


async def init_cookie_manager() -> CookieManager:
    """初始化 CookieManager 单例并加载。"""
    global _instance
    if _instance is None:
        _instance = CookieManager()
        await _instance.load()
    return _instance


def get_cookie_manager() -> CookieManager:
    """获取已初始化的 CookieManager 单例。"""
    if _instance is None:
        raise RuntimeError("CookieManager 未初始化，请先调用 init_cookie_manager()")
    return _instance
