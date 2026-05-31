"""
crawler/proxy.py

IP 代理池全生命周期管理。

职责：
    1. 维护代理状态机：UNKNOWN → ALIVE ↔ SUSPICIOUS → BANNED
    2. 线程安全的代理获取（asyncio.Lock）
    3. 管理员/付费代理持久化到 data/proxies.json
    4. 单代理校验（alive check）
    5. 批量 health_check

不负责：
    HTTP 请求封装（由 fetcher.py 负责）

设计要点：
    - 付费代理通过 .env PAID_PROXIES 注入，TTL 7 天
    - 管理员手动添加的代理持久化，TTL 7 天
    - _banned 不持久化——封了就封了
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

PERSIST_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "proxies.json")


class ProxyStatus(Enum):
    UNKNOWN = "unknown"
    ALIVE = "alive"
    SUSPICIOUS = "suspicious"    # 失败 1 次，再给一次机会
    BANNED = "banned"           # 永久封禁，不复用


class SourceType(Enum):
    ADMIN = "admin"   # 管理员手动添加或 .env 付费代理注入


@dataclass
class Proxy:
    """
    单个代理对象。

    v2 — 新增认证字段（username/password/id/remark/proxy_type/enabled），
         付费代理需要用户名密码认证。

    字段说明：
        host/port:        代理地址
        username/password: 认证凭据（空=无认证）
        id:               管理端标识（自增整数，不持久化）
        remark:           管理员备注（可选）
        proxy_type:       代理协议（http/https/socks5）
        enabled:          是否启用（管理员可手动禁用）
        status:           状态
        fail_count:       连续失败次数（触发状态转换）
        success_count:    累计成功次数
        last_used:        上次使用时间戳
        added_at:         加入时间戳
        source:           来源类型（ADMIN）
        region:           地区（可选）
    """
    host: str
    port: int
    username: str = ""
    password: str = ""
    id: int = 0
    remark: str = ""
    proxy_type: str = "http"
    enabled: bool = True
    status: ProxyStatus = ProxyStatus.UNKNOWN
    fail_count: int = 0
    success_count: int = 0
    last_used: float = 0.0
    added_at: float = field(default_factory=time.time)
    source: SourceType = SourceType.ADMIN
    region: str = ""

    @property
    def key(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def is_alive(self) -> bool:
        return self.status == ProxyStatus.ALIVE and self.enabled

    @property
    def has_auth(self) -> bool:
        return bool(self.username and self.password)


# 状态转换阈值
FAIL_THRESHOLD_BAN = 2       # 连续失败 N 次 → BANNED
SUSPICIOUS_RESET_ON_SUCCESS = True  # 可疑代理成功一次 → 恢复 ALIVE

# TTL 配置（秒）
ADMIN_TTL = 604800           # 管理员/付费代理默认 7 天

_proxy_id_counter: int = 0


def _next_proxy_id() -> int:
    """分配自增代理 ID（不持久化，重启重置不影响功能）。"""
    global _proxy_id_counter
    _proxy_id_counter += 1
    return _proxy_id_counter


async def _poll_verification_recovery(page, host: str, port: int) -> bool:
    """
    指数退避轮询：验证码点击后检测页面是否恢复。

    轮询节点：5s → 10s → 20s（从点击时起算，累计 35s）
    任一节点检测到页面标题含"豆瓣"且无异常跳转 → 立即返回 True
    全部节点失败 → 返回 False

    输入: page (Playwright Page 对象), host, port (仅日志)
    输出: True=验证通过, False=页面未恢复
    """
    checks = [5, 10, 20]
    for wait_sec in checks:
        await asyncio.sleep(wait_sec)
        try:
            await page.goto(
                "https://movie.douban.com/",
                wait_until="domcontentloaded",
                timeout=10000,
            )
            title = await page.title()
            if "豆瓣" in title:
                logger.debug(
                    f"代理测试 {host}:{port} — 验证轮询通过 "
                    f"(第 {checks.index(wait_sec) + 1}/{len(checks)} 次, "
                    f"等待 {sum(checks[:checks.index(wait_sec) + 1])}s)"
                )
                return True
        except Exception:
            continue
    logger.debug(f"代理测试 {host}:{port} — 验证轮询全部失败")
    return False


class ProxyPool:
    """
    IP 代理池。

    支持：
        - 按来源区分持久化策略
        - 状态机驱动（report_success / report_failure）
        - 从 data/proxies.json 加载/保存管理员添加的代理
        - asyncio.Lock 保护并发安全
        - v2: 支持代理认证（username/password）
    """

    def __init__(self):
        self._alive: list[Proxy] = []         # 可用代理
        self._suspicious: dict[str, Proxy] = {}  # 可疑代理（host:port → Proxy）
        self._banned: set[str] = set()        # 封禁黑名单（"host:port" 字符串）
        self._lock = asyncio.Lock()

    # ==================== 公共属性 ====================

    @property
    def alive_count(self) -> int:
        return len(self._alive)

    @property
    def suspicious_count(self) -> int:
        return len(self._suspicious)

    @property
    def banned_count(self) -> int:
        return len(self._banned)

    @property
    def total_count(self) -> int:
        return len(self._alive) + len(self._suspicious) + len(self._banned)

    # ==================== 加载/保存 ====================

    async def load_persisted(self) -> int:
        """
        从 data/proxies.json 加载持久化的代理（管理员手动添加的）。

        输入：无
        输出：加载成功数
        副作用：修改 _alive
        """
        if not os.path.exists(PERSIST_FILE):
            logger.info(f"持久文件不存在，跳过: {PERSIST_FILE}")
            return 0

        try:
            with open(PERSIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"持久文件读取失败: {e}")
            return 0

        loaded = 0
        now = time.time()
        for item in data.get("proxies", []):
            host = item.get("host")
            port = item.get("port")
            if not host or not port:
                continue

            added_at = item.get("added_at", 0)
            if now - added_at > ADMIN_TTL:
                logger.debug(f"管理员代理已过期: {host}:{port}")
                continue

            key = f"{host}:{port}"
            if key in self._banned:
                continue

            proxy = Proxy(
                host=host,
                port=port,
                id=_next_proxy_id(),
                status=ProxyStatus.UNKNOWN,
                username=item.get("username", ""),
                password=item.get("password", ""),
                success_count=item.get("success_count", 0),
                fail_count=item.get("fail_count", 0),
                added_at=added_at,
                source=SourceType.ADMIN,
                region=item.get("region", ""),
            )
            proxy.status = ProxyStatus.ALIVE  # 持久化的代理默认信任
            if key not in self._suspicious:
                self._alive.append(proxy)
                loaded += 1

        logger.info(f"从持久文件加载了 {loaded} 个管理员代理")
        return loaded

    async def save_persisted(self) -> int:
        """
        将来源为 ADMIN 的 _alive 代理写入 data/proxies.json。

        输入：无
        输出：保存数量
        副作用：写入磁盘
        """
        os.makedirs(os.path.dirname(PERSIST_FILE), exist_ok=True)

        data = {
            "version": 1,
            "proxies": [
                {
                    "host": p.host,
                    "port": p.port,
                    "username": p.username,
                    "password": p.password,
                    "source": "admin",
                    "added_at": p.added_at,
                    "success_count": p.success_count,
                    "fail_count": p.fail_count,
                    "region": p.region,
                }
                for p in self._alive
                if p.source == SourceType.ADMIN
            ]
        }

        try:
            with open(PERSIST_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"持久化 {len(data['proxies'])} 个管理员代理到 {PERSIST_FILE}")
            return len(data["proxies"])
        except IOError as e:
            logger.error(f"持久文件写入失败: {e}")
            return 0

    # ==================== 增删操作 ====================

    async def add_proxy(
        self,
        host: str,
        port: int,
        source: SourceType = SourceType.ADMIN,
        region: str = "",
        username: str = "",
        password: str = "",
        remark: str = "",
        prefer: bool = False,
    ) -> bool:
        """
        添加一个代理到池中。

        Args:
            host:     IP 地址
            port:     端口
            source:   来源类型
            region:   地区
            username: 认证用户名（可选）
            password: 认证密码（可选）
            remark:   管理员备注（可选）
            prefer:   True=优先插入到队列头部（付费代理推荐使用），默认 False 追加尾部

        Returns:
            True 表示添加成功，False 表示已在池中或黑名单中
        """
        key = f"{host}:{port}"
        if key in self._banned:
            logger.info(f"代理 {key} 在黑名单中，拒绝添加")
            return False

        async with self._lock:
            for p in self._alive:
                if p.key == key:
                    return False
            if key in self._suspicious:
                return False

            proxy = Proxy(
                host=host, port=port, source=source, region=region,
                username=username, password=password, remark=remark,
                id=_next_proxy_id(),
            )
            proxy.status = ProxyStatus.ALIVE
            if prefer:
                self._alive.insert(0, proxy)
            else:
                self._alive.append(proxy)

        logger.info(f"代理已添加: {key} (来源: {source.value}, prefer={prefer})")
        return True

    def get_by_key(self, key: str) -> Optional["Proxy"]:
        """按 key (host:port) 查找可用代理。"""
        for p in self._alive:
            if p.key == key:
                return p
        return None

    def get_by_id(self, proxy_id: int) -> Optional["Proxy"]:
        """按管理端 ID 查找代理（alive + suspicious）。"""
        for p in self._alive:
            if p.id == proxy_id:
                return p
        for p in self._suspicious.values():
            if p.id == proxy_id:
                return p
        return None

    def options_list(self) -> list[dict]:
        """
        供管理端下拉选择器使用的精简列表（仅 alive + enabled 代理）。
        """
        return [
            {
                "id": p.id,
                "key": p.key,
                "label": p.remark or p.key,
                "has_auth": p.has_auth,
                "region": p.region,
            }
            for p in self._alive
            if p.enabled
        ]

    async def update_proxy(self, proxy_id: int, **kwargs) -> bool:
        """
        按 ID 更新代理属性。

        输入：proxy_id + 任意关键字参数（remark/username/password/region/enabled/proxy_type）
        输出：True=成功, False=不存在
        """
        proxy = self.get_by_id(proxy_id)
        if proxy is None:
            return False
        async with self._lock:
            for field, value in kwargs.items():
                if hasattr(proxy, field):
                    setattr(proxy, field, value)
        logger.info(f"代理已更新: id={proxy_id} fields={list(kwargs.keys())}")
        return True

    async def ban_proxy(self, host: str, port: int) -> bool:
        """
        管理员主动封禁一个代理。

        Args:
            host: IP 地址
            port: 端口

        Returns:
            True 表示封禁成功，False 表示不在池中
        """
        key = f"{host}:{port}"

        async with self._lock:
            # 从 alive 中找
            for i, p in enumerate(self._alive):
                if p.key == key:
                    self._alive.pop(i)
                    p.status = ProxyStatus.BANNED
                    self._banned.add(key)
                    logger.info(f"管理员封禁代理: {key}")
                    return True
            # 从 suspicious 中找
            if key in self._suspicious:
                p = self._suspicious.pop(key)
                p.status = ProxyStatus.BANNED
                self._banned.add(key)
                logger.info(f"管理员封禁可疑代理: {key}")
                return True

        logger.warning(f"代理 {key} 不在池中，无法封禁")
        return False

    # ==================== 代理获取 ====================

    async def get_proxy(self) -> Optional[Proxy]:
        """
        获取一个 ALIVE 代理。

        策略：简单轮转——取头放尾。

        输入：无
        输出：Proxy 或 None（池空）
        副作用：修改 _alive 顺序（轮转）
        """
        async with self._lock:
            if not self._alive:
                return None
            # 跳过已禁用的代理（最多重试一圈避免死循环）
            for _ in range(len(self._alive)):
                proxy = self._alive.pop(0)
                self._alive.append(proxy)
                if proxy.enabled:
                    proxy.last_used = time.time()
                    return proxy
            return None

    def get_stats(self) -> dict:
        """
        代理池统计（非阻塞，直接读计数器）。

        输出：{alive, dead(→suspicious), suspicious, banned, total}
        """
        return {
            "alive": self.alive_count,
            "dead": self.suspicious_count,        # 前端 ProxyStats.dead 的兼容别名
            "suspicious": self.suspicious_count,
            "banned": self.banned_count,
            "total": self.total_count,
        }

    def list_all(self) -> list[dict]:
        """
        列出所有代理的详情（alive + suspicious + banned）。

        输出字段对齐前端 ProxyItem 接口：
            id, host, port, key, has_auth, remark, proxy_type, enabled,
            status, is_alive, success_rate, avg_latency_ms,
            source, success_count, fail_count, region,
            last_used, added_at（ISO 字符串格式）
        """
        def _ts_iso(ts: float) -> str:
            """将 Unix 时间戳（秒）转为 ISO 字符串，0 或 None 返回空串。"""
            if not ts or ts <= 0:
                return ""
            return datetime.fromtimestamp(ts).isoformat()

        def _success_rate(sc: int, fc: int) -> float:
            """计算成功率（百分比，保留1位小数）"""
            total = sc + fc
            return round(sc / total * 100, 1) if total > 0 else 0.0

        def _proxy_dict(p, status_override: str = "") -> dict:
            status_val = status_override or p.status.value
            return {
                "id": p.id,
                "host": p.host,
                "port": p.port,
                "key": p.key,
                "has_auth": p.has_auth,
                "remark": p.remark,
                "proxy_type": p.proxy_type,
                "enabled": p.enabled,
                "status": status_val,
                "is_alive": status_val == "alive" and p.enabled,
                "success_rate": _success_rate(p.success_count, p.fail_count),
                "avg_latency_ms": 0,
                "source": p.source.value if p.source else "",
                "success_count": p.success_count,
                "fail_count": p.fail_count,
                "region": p.region,
                "last_used": _ts_iso(p.last_used),
                "added_at": _ts_iso(p.added_at),
            }

        result = []
        for p in self._alive:
            result.append(_proxy_dict(p))
        for p in self._suspicious.values():
            result.append(_proxy_dict(p))
        for key_str in self._banned:
            parts = key_str.split(":", 1)
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 0
            result.append({
                "id": 0,
                "host": host,
                "port": port,
                "key": key_str,
                "has_auth": False,
                "remark": "",
                "proxy_type": "",
                "enabled": False,
                "status": "banned",
                "is_alive": False,
                "success_rate": 0.0,
                "avg_latency_ms": 0,
                "source": "",
                "success_count": 0,
                "fail_count": 0,
                "region": "",
                "last_used": "",
                "added_at": "",
            })
        return result

    def get_snapshot(self) -> Dict[str, Any]:
        """获取代理池快照（供管理员 API 查询，不加锁，近似值）。"""
        return {
            "alive": len(self._alive),
            "suspicious": len(self._suspicious),
            "banned": len(self._banned),
            "total": self.total_count,
            "alive_list": [p.key for p in self._alive],
            "banned_list": list(self._banned),
        }

    # ==================== 状态上报 ====================

    async def report_success(self, proxy: Proxy) -> None:
        """
        上报代理使用成功。

        副作用：
            - success_count++
            - fail_count 重置为 0
            - 如果来自 _suspicious 或处于 SUSPICIOUS 状态 → 恢复 ALIVE
        """
        async with self._lock:
            proxy.success_count += 1
            proxy.fail_count = 0

            if proxy.key in self._suspicious:
                recovered = self._suspicious.pop(proxy.key)
                recovered.status = ProxyStatus.ALIVE
                self._alive.append(recovered)
                logger.debug(f"可疑代理恢复: {proxy.key}")
            elif proxy.status == ProxyStatus.SUSPICIOUS:
                proxy.status = ProxyStatus.ALIVE
                logger.debug(f"可疑代理恢复（单代理模式）: {proxy.key}")

    async def report_failure(self, proxy: Proxy) -> None:
        """
        上报代理使用失败。

        副作用：
            - fail_count++
            - 首次失败 → 移入 _suspicious（但如果 _alive 只剩它一个，则留在池中给 retry 机会）
            - 再次失败 → 移入 _banned

        注意：调用方需传入同一个 Proxy 对象引用，
              我们通过 proxy.key 在 _suspicious 中查找。
        """
        async with self._lock:
            proxy.fail_count += 1

            if proxy.fail_count >= FAIL_THRESHOLD_BAN:
                self._remove_from_all(proxy)
                proxy.status = ProxyStatus.BANNED
                self._banned.add(proxy.key)
                logger.warning(f"代理已封禁: {proxy.key} (连续失败 {proxy.fail_count} 次)")

            elif proxy.fail_count == 1:
                if proxy in self._alive and len(self._alive) <= 1:
                    logger.debug(f"代理标记为可疑但仍在池中（最后一个代理，给 retry 机会）: {proxy.key}")
                    proxy.status = ProxyStatus.SUSPICIOUS
                else:
                    self._remove_from_all(proxy)
                    proxy.status = ProxyStatus.SUSPICIOUS
                    self._suspicious[proxy.key] = proxy
                    logger.debug(f"代理标记为可疑: {proxy.key}")

    def _remove_from_all(self, proxy: Proxy) -> None:
        """从 alive 和 suspicious 中移除代理（需在锁内调用）。"""
        self._alive = [p for p in self._alive if p.key != proxy.key]
        self._suspicious.pop(proxy.key, None)

    async def _report_ip_ok(self, proxy_key: str) -> None:
        """
        由 Cookie 验证后验：报告 IP 正常。

        通过 key (host:port) 查找代理 → report_success()。
        找不到则静默跳过。
        """
        proxy = self.get_by_key(proxy_key)
        if proxy:
            await self.report_success(proxy)

    async def _report_ip_fail(self, proxy_key: str) -> None:
        """
        由 Cookie 验证后验：报告 IP 不可用，同步状态机。

        通过 key (host:port) 查找代理 → report_failure()。
        找不到则静默跳过。
        """
        proxy = self.get_by_key(proxy_key)
        if proxy:
            await self.report_failure(proxy)

    # ==================== 校验 ====================

    @staticmethod
    async def verify_proxy(
        host: str, port: int,
        timeout: float = 5.0,
        username: str = "",
        password: str = "",
    ) -> bool:
        """
        轻量校验代理到豆瓣的可用性（aiohttp，适合批量 health_check）。

        通过代理请求 movie.douban.com，状态码 200/301/302 即视为可用。

        Args:
            host:    代理 IP
            port:    代理端口
            timeout: 超时秒数
            username: 认证用户名（可选）
            password: 认证密码（可选）

        Returns:
            True 可用，False 不可用
        """
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp 未安装，无法校验代理")
            return False

        if username and password:
            proxy_url = f"http://{username}:{password}@{host}:{port}"
        else:
            proxy_url = f"http://{host}:{port}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://movie.douban.com/",
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    headers={"User-Agent": "Mozilla/5.0"},
                    allow_redirects=False,
                    ssl=False,
                ) as resp:
                    return resp.status in (200, 301, 302)
        except Exception:
            return False

    @staticmethod
    async def verify_proxy_browser(
        host: str,
        port: int,
        browser,
        playwright=None,
        username: str = "",
        password: str = "",
        timeout: int = 15,
    ) -> tuple[bool, str]:
        """
        用真实浏览器校验代理到豆瓣的可用性（Playwright，适合单代理手动测试）。

        流程：
            1. Playwright → 代理 → movie.douban.com/chart
            2. domcontentloaded → 页面标题含"豆瓣" → 成功
            3. 等待 15s 检测验证按钮（#sub），有则自动点击
            4. 点击后指数退避轮询（5s→10s→20s），任一检查通过立即返回

        参考：scripts/test_paid_proxy.py 的验证逻辑

        Args:
            host:      代理 IP
            port:      代理端口
            browser:   Playwright Chromium 浏览器实例
            playwright: Playwright 入口对象（浏览器崩溃时自动重启）
            username:  认证用户名（可选）
            password:  认证密码（可选）
            timeout:   页面导航超时（秒）

        Returns:
            (True, "连接成功 (延迟 Xms)") 或 (False, "失败原因")
        """
        import time as _time
        proxy_config = {"server": f"http://{host}:{port}"}
        if username:
            proxy_config["username"] = username
        if password:
            proxy_config["password"] = password

        context = None
        try:
            context = await browser.new_context(proxy=proxy_config)
            page = await context.new_page()
            start = _time.time()
            await page.goto(
                "https://movie.douban.com/chart",
                wait_until="domcontentloaded",
                timeout=timeout * 1000,
            )
            elapsed = int((_time.time() - start) * 1000)
            title = await page.title()
            if "豆瓣" not in title:
                return False, f"页面标题异常: {title[:50]}"

            # 检测验证按钮 — 等待最多 15s 看 #sub 是否出现
            clicked_sub = False
            try:
                await asyncio.sleep(15)
                await page.locator("#sub").click(timeout=3000)
                clicked_sub = True
                logger.debug(f"代理测试 {host}:{port} — 检测到验证按钮，已自动点击，开始轮询")
            except Exception:
                logger.debug(f"代理测试 {host}:{port} — 未触发验证，跳过")

            if clicked_sub:
                verified = await _poll_verification_recovery(page, host, port)
                if not verified:
                    return False, "验证码点击后页面未恢复（可能被反爬拦截）"
                elapsed += 35000  # 轮询总耗时 ~35s

            return True, f"连接成功 (延迟 {elapsed}ms)"
        except Exception as e:
            msg = str(e)[:80]
            if "timeout" in msg.lower():
                return False, "连接超时（可能被豆瓣限流）"
            return False, f"代理不可用: {msg}"
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

    async def health_check(self, browser, concurrency: int = 2) -> Dict[str, int]:
        """
        批量验证 _alive 中所有代理（Playwright 真浏览器，逐个串行避免浏览器资源耗尽）。

        输入：browser (Playwright 实例), concurrency 并发数（建议 ≤2）
        输出：{"alive": N, "dead": M, "total": T}
        副作用：不可用的代理移入 banned

        注意：不再使用轻量 aiohttp 验证（多数代理会被豆瓣反爬拦截产生假阳性），
              统一走 Playwright 真浏览器，结果准确但耗时（每代理 15~50s）。
        """
        async with self._lock:
            proxies_to_check = list(self._alive)

        if not proxies_to_check:
            logger.info("health_check: 无代理需要验证")
            return {"alive": 0, "dead": 0, "total": 0}

        concurrency = max(1, min(concurrency, 3))
        semaphore = asyncio.Semaphore(concurrency)
        dead_count = 0
        alive_count = 0

        async def _check_one(p: Proxy):
            nonlocal dead_count, alive_count
            async with semaphore:
                ok, _ = await self.verify_proxy_browser(
                    p.host, p.port,
                    browser=browser,
                    username=p.username,
                    password=p.password,
                    timeout=15,
                )
                if ok:
                    alive_count += 1
                else:
                    dead_count += 1
                    await self.report_failure(p)

        await asyncio.gather(*[_check_one(p) for p in proxies_to_check])

        total = alive_count + dead_count
        logger.info(f"health_check: {alive_count} 存活, {dead_count} 死亡, {total} 总")
        return {"alive": alive_count, "dead": dead_count, "total": total}


# ==================== 模块级单例 ====================

_pool_instance: Optional[ProxyPool] = None


def init_proxy_pool() -> ProxyPool:
    """获取或创建 ProxyPool 单例。"""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = ProxyPool()
    return _pool_instance


def get_proxy_pool() -> ProxyPool:
    """获取已初始化的 ProxyPool 单例。未初始化则抛出异常。"""
    if _pool_instance is None:
        raise RuntimeError("ProxyPool 未初始化，请先调用 init_proxy_pool()")
    return _pool_instance
