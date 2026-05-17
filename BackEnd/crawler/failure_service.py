"""
crawler/failure_service.py

失败事件合同 — Worker → Monitor 事件通道的标准化定义。

职责：
    1. 定义事件类型枚举 (EventType) — 替换手写字符串 "success"/"failure"/"cancelled"
    2. 定义错误分类枚举 (FailureKind) — 异常自动化归类，7 种
    3. 定义事件合同 (WorkerEvent) — Pydantic 强类型，Worker/Monitor 共享同一份定义
    4. 提供 classify_exception() — 从异常对象推导 FailureKind

使用方式：
    Worker 侧（生产者）：
        from crawler.failure_service import WorkerEvent, EventType, FailureKind, classify_exception
        event = WorkerEvent(
            event_type=EventType.FAILURE,
            worker_id=worker_id,
            task=task,
            timestamp=time.time(),
            kind=classify_exception(e),
            reason=str(e),
        )
        await event_queue.put(event.model_dump())

    Monitor 侧（消费者）：
        from crawler.failure_service import WorkerEvent, EventType
        event = WorkerEvent.model_validate(raw_dict)
        if event.event_type == EventType.FAILURE:
            ...

统计能力（基于 FailureKind）：
    SELECT kind, COUNT(*) FROM task_failures GROUP BY kind;
    → network=120, parse=8, http=14, abuse=3, ...
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── 事件类型枚举 ──

class EventType(str, Enum):
    """Worker → event_queue 的事件类型。"""
    STARTED      = "started"
    STAGE_CHANGE = "stage_change"
    SUCCESS      = "success"
    FAILURE      = "failure"
    CANCELLED    = "cancelled"


# ── 错误分类枚举 ──

class FailureKind(str, Enum):
    """
    失败事件的错误分类（机器可读）。

    用途：
        - Monitor 写入 task_failures.kind 列
        - 统计错误分布，辅助优化代理/解析/容错策略
    """
    NETWORK     = "network"       # DNS/代理/连接被拒/直连失败
    TIMEOUT     = "timeout"       # Playwright 导航超时 / aiohttp 读取超时
    HTTP        = "http"          # 4xx 页面不存在 / 5xx 服务端异常
    PARSE       = "parse"         # HTML/JSON 结构变化，正则未匹配
    STORAGE     = "storage"       # MySQL/MongoDB 写入失败
    ABUSE       = "abuse"         # 豆瓣反爬 — "检测到有异常请求" / 验证码页
    VALIDATION  = "validation"    # 任务 JSON 非法、缺少必填字段
    BROWSER     = "browser"       # Chromium 进程崩溃（已自动重启）
    UNKNOWN     = "unknown"       # 兜底 — 无法归类的异常


# ── Worker 事件合同 ──

class WorkerEvent(BaseModel):
    """
    Worker → Monitor 事件通道的强类型合同。

    约束：
        - 所有字段必填（Pydantic 默认行为）
        - kind 和 reason 在 SUCCESS 时可为默认值
    """
    event_type:  EventType
    worker_id:   int
    task:        str                   # 原始任务 JSON 字符串
    timestamp:   float                 # time.time()

    # 仅在 FAILURE / CANCELLED 时有意义
    kind:    FailureKind = FailureKind.UNKNOWN
    reason:  str = ""

    # 仅在 STAGE_CHANGE 时有意义 — Crawler 内部阶段描述
    stage:   str = ""

    # 执行快照 — AI 失败时包含 {provider, model, input_preview, output_preview, ...}
    snapshot: Optional[dict] = None

    # 预留 — 当前全部为 0
    retry_count: int = 0
    max_retries: int = 0


# ── 异常分类器 ──

def classify_exception(exc: Exception) -> FailureKind:
    """
    从异常对象自动推导 FailureKind。

    输入：任意 Exception 或其子类
    输出：对应的 FailureKind 枚举值
    分类策略：
        1. 先按异常类型（isinstance）精确匹配
        2. 再按异常类名（type().__name__）匹配
        3. 最后按异常消息关键字兜底
    副作用：无

    维护提示：
        新增异常类型时在此函数中加一条规则即可，
        不需要改 EventType / FailureKind / WorkerEvent。
    """
    # ── 按完整类路径匹配（isinstance） ──
    from crawler.fetcher import FetcherError

    if isinstance(exc, FetcherError):
        msg = str(exc).lower()
        if "timeout" in msg:
            return FailureKind.TIMEOUT
        return FailureKind.NETWORK

    # ── 按类名匹配（避免跨模块 import 所有异常类型） ──
    exc_name = type(exc).__name__
    msg = str(exc).lower()

    if exc_name in ("ValueError", "ValidationError"):
        return FailureKind.VALIDATION

    if exc_name in (
        "PlaywrightTimeoutError", "TimeoutError", "asyncio.TimeoutError",
        "asyncio.exceptions.TimeoutError",
    ):
        return FailureKind.TIMEOUT

    if exc_name in ("ClientError", "ServerError", "HTTPError", "ClientResponseError"):
        return FailureKind.HTTP

    if exc_name in ("DuplicateKeyError", "IntegrityError", "DataError", "OperationalError"):
        return FailureKind.STORAGE

    # ── 按消息关键字兜底 ──
    if "abuse" in msg or "检测到有异常请求" in msg:
        return FailureKind.ABUSE

    if any(kw in msg for kw in ("browser crashed", "target closed", "browser closed")):
        return FailureKind.BROWSER

    if any(kw in msg for kw in ("timeout", "timed out", "超时")):
        return FailureKind.TIMEOUT

    if any(kw in msg for kw in ("connection", "resolve", "refused", "connect")):
        return FailureKind.NETWORK

    if "404" in msg or "not found" in msg:
        return FailureKind.HTTP

    if "parse" in msg or "解析" in msg:
        return FailureKind.PARSE

    return FailureKind.UNKNOWN


def classify_failure_layer(kind: FailureKind, exc: Exception) -> str:
    """
    根据 FailureKind + 异常信息推导 failure_layer（错误来源层）。

    输入：FailureKind 枚举 + 原始异常
    输出："crawler" | "storage" | "ai" | "system"

    分类策略：
        - STORAGE → "storage"（MySQL/MongoDB 写入失败）
        - ABUSE / NETWORK / PARSE / VALIDATION / HTTP → "crawler"
        - BROWSER → "system"（浏览器崩溃，已自带重启）
        - 异常类名含 "AI" 或 "DeepSeek" → "ai"
        - 其他 → "crawler"
    """
    if kind == FailureKind.STORAGE:
        return "storage"

    if kind == FailureKind.BROWSER:
        return "system"

    exc_name = type(exc).__name__
    msg = str(exc).lower()
    if any(kw in exc_name.lower() or kw in msg for kw in ("deepseek", "openai", "ai", "token")):
        return "ai"

    return "crawler"
