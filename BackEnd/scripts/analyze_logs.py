"""
scripts/analyze_logs.py

日志分析工具 — 将结构化 JSON 日志翻译为直白的人类语言。

用法：
    python scripts/analyze_logs.py                          # 时间线模式（默认）
    python scripts/analyze_logs.py --summary                # 摘要统计
    python scripts/analyze_logs.py --since 2026-05-08T12:00 # 只看指定时间之后
    python scripts/analyze_logs.py --layer access           # 只看接入层
    python scripts/analyze_logs.py --layer infra --since 12:00  # 组合过滤
    python scripts/analyze_logs.py --verbose                # 展开 DEBUG / 后台噪声

输出：
    时间线模式：按时间排序，每行一条直白翻译
    摘要模式：按 URL/事件/状态码 聚合计数
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta

# 东八区时区常量
CST = timezone(timedelta(hours=8))
from pathlib import Path

# Windows 终端 UTF-8 兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── 日志目录 ──
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# ── 时间格式 ──
_TIME_FMT = "%H:%M:%S"
_FULL_TIME_FMT = "%Y-%m-%d %H:%M:%S"

# ── ANSI 颜色（终端高亮）──
_DIM = "\033[2m"
_RESET = "\033[0m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"


# ═══════════════════════════════════════════════════════
# 翻译规则
# ═══════════════════════════════════════════════════════

def _translate_access(entry: dict) -> str | None:
    """接入层翻译 — 路由日志 / hypercorn 启动。"""
    msg = entry["message"]

    if "Running on" in msg:
        return f"Server start -> {_GREEN}READY{_RESET}"

    # 路由: "POST /auth/login -> 200 | 172.0ms | IP=127.0.0.1"
    m = re.search(
        r"(GET|POST|PUT|DELETE|PATCH)\s+(\S+)\s+->\s+(\d+)\s*\|\s*([\d.]+)ms\s*\|\s*IP=(.*)",
        msg,
    )
    if not m:
        return msg

    method, path, status, elapsed, ip = m.groups()
    sc = _GREEN if status == "200" else _RED if status[0] in "45" else _YELLOW

    label = _route_label(method, path)
    icon = _status_icon(status)

    return (
        f"{label:<14} {icon} {sc}{status}{_RESET}"
        f" ({elapsed}ms) {_DIM}<-{ip}{_RESET}"
    )


def _translate_service(entry: dict) -> str | None:
    """业务层翻译 — 注册/登录/爬虫/评论/电影 等。"""
    msg = entry["message"]
    logger = entry.get("logger", "")

    # pymongo 内部 DEBUG -> 跳过
    if logger.startswith("pymongo"):
        return None

    # 注册
    if "用户已创建:" in msg:
        m = re.search(r"username='([^']+)'", msg)
        name = m.group(1) if m else "?"
        return f"[register]  new user '{_CYAN}{name}{_RESET}' {_GREEN}OK{_RESET}"

    # 豆瓣 Cookie
    if "登录态验证通过" in msg:
        return f"[crawler]  douban cookie verified {_GREEN}OK{_RESET}"
    if "已加载豆瓣登录态" in msg:
        m = re.search(r"保存于 (.+)\)", msg)
        saved = m.group(1)[:19] if m else "?"
        return f"[crawler]  loaded douban cookie (saved {saved})"

    # 爬虫引擎
    if "CrawlerEngine" in msg:
        return f"[crawler]  {msg}"
    if "爬取" in msg or "抓取" in msg:
        return f"[crawler]  {msg}"

    # 评论
    if "review" in logger.lower() or "评论" in msg or "长评" in msg or "短评" in msg:
        return f"[review]   {msg[:80]}"

    # 电影
    if "movie" in logger.lower() or "电影" in msg:
        return f"[movie]    {msg[:80]}"

    # 用户
    if "用户" in msg:
        return f"[user]    {msg[:80]}"

    # 权限
    if "权限" in msg:
        return f"[perm]    {msg[:80]}"

    # 其余
    return f"          {msg[:100]}"


def _translate_infra(entry: dict) -> str | None:
    """基础设施翻译 — DB / 后台任务 / Monitor。"""
    msg = entry["message"]

    # ── MySQL ──
    if "初始化 MySQL 连接池" in msg:
        return f"mysql     init pool {_DIM}({_extract_addr(msg)}){_RESET}"
    if "MySQL 连接池初始化成功" in msg:
        return f"mysql     ready {_GREEN}OK{_RESET}"

    # ── Redis ──
    if "初始化 Redis 连接池" in msg:
        return f"redis     init pool {_DIM}({_extract_addr(msg)}){_RESET}"
    if "Redis 连接池初始化成功" in msg:
        return f"redis     ready {_GREEN}OK{_RESET}"

    # ── MongoDB ──
    if "初始化 MongoDB 客户端" in msg:
        return f"mongo     init pool {_DIM}({_extract_addr(msg)}){_RESET}"
    if "MongoDB 客户端初始化成功" in msg:
        return f"mongo     ready {_GREEN}OK{_RESET}"

    # ── 数据库中间层 ──
    if "DatabaseLayerV2 初始化完成" in msg:
        return f"db        unified layer ready {_GREEN}OK{_RESET}"

    # ── 后台任务 ──
    if "Puller 单例已初始化" in msg:
        return "puller    init"
    if "Puller 启动" in msg:
        return f"puller    started {_GREEN}>-{_RESET}"
    if "BrowserPool 单例已初始化" in msg:
        return "worker    browser pool init"
    if "BrowserPool 启动" in msg:
        m = re.search(r"共 (\d+) 个", msg)
        n = m.group(1) if m else "?"
        return f"worker    started {_GREEN}{n} workers >-{_RESET}"
    if "Monitor 单例已初始化" in msg:
        return "monitor   init"
    if "Monitor 启动" in msg:
        m = re.search(r"轮询间隔 (\d+) 秒", msg)
        n = m.group(1) if m else "?"
        return f"monitor   started {_DIM}(every {n}s){_RESET}"

    # ── Monitor 报告 -> 压缩一行 ──
    if "Monitor 报告" in msg:
        return _summarize_monitor(msg)

    # ── Redis 任务弹出 ──
    if "弹出到期任务数:" in msg:
        m = re.search(r"弹出到期任务数: (\d+)", msg)
        n = m.group(1) if m else "0"
        if n != "0":
            return f"redis     popped {n} due tasks"
        return None

    # ── 关闭 ──
    if "优雅关闭" in msg or "停止" in msg:
        return f"          {_YELLOW}[DOWN] {msg}{_RESET}"

    return f"          {msg[:100]}"


def _route_label(method: str, path: str) -> str:
    if path.startswith("/auth/login"):
        return "[login]"
    if path.startswith("/auth/register"):
        return "[register]"
    if path.startswith("/auth/me"):
        return "[identity]"
    if path.startswith("/admin/"):
        return "[admin]"
    if path.startswith("/user/"):
        return "[user]"
    if path.startswith("/ws/"):
        return "[ws]"
    return f"[{method}]"


def _status_icon(status: str) -> str:
    s = int(status)
    if s == 200:
        return "OK  "
    if s == 201:
        return "NEW "
    if s == 401:
        return "AUTH"
    if s == 403:
        return "DENY"
    if s == 404:
        return "MISS"
    if s == 500:
        return "ERR "
    return "    "


def _extract_addr(msg: str) -> str:
    m = re.search(r"(\S+:\d+/\S+)", msg)
    return m.group(1) if m else ""


def _summarize_monitor(msg: str) -> str | None:
    cpu = re.search(r"cpu_percent=([\d.]+)", msg)
    mem = re.search(r"memory_percent=([\d.]+)", msg)
    qs = re.search(r"queue_size=(\d+)", msg)
    qm = re.search(r"queue_maxsize=(\d+)", msg)
    idle = re.search(r"worker_idle=(\d+)", msg)
    alive = re.search(r"worker_alive=(\d+)", msg)
    succ = re.search(r"events_success_total=(\d+)", msg)
    fail = re.search(r"events_failure_total=(\d+)", msg)

    parts = []
    if cpu and mem:
        cs = _cpu_color(float(cpu.group(1)))
        ms = _cpu_color(float(mem.group(1)))
        parts.append(f"CPU {cs}{cpu.group(1)}%{_RESET}  Mem {ms}{mem.group(1)}%{_RESET}")
    if qs and qm:
        parts.append(f"Queue {qs.group(1)}/{qm.group(1)}")
    if idle is not None and alive is not None:
        busy = int(alive.group(1)) - int(idle.group(1))
        bc = _YELLOW if busy else _GREEN
        parts.append(f"Worker {_GREEN}{idle.group(1)}idle{_RESET} {bc}{busy}busy{_RESET}")
    if succ and fail:
        fc = _RED if fail.group(1) != "0" else ""
        parts.append(f"Tasks OK:{succ.group(1)} {fc}FAIL:{fail.group(1)}{_RESET}")

    return f"[status]  {' | '.join(parts)}" if parts else None


def _cpu_color(val: float) -> str:
    if val > 80:
        return _RED
    if val > 50:
        return _YELLOW
    return _GREEN


# ═══════════════════════════════════════════════════════
# 调度
# ═══════════════════════════════════════════════════════

def _translate(entry: dict, verbose: bool) -> str | None:
    level = entry.get("level", "INFO")
    if not verbose and level == "DEBUG":
        return None

    category = entry.get("category", "service")

    if category == "access":
        result = _translate_access(entry)
    elif category == "infra":
        result = _translate_infra(entry)
    else:
        result = _translate_service(entry)

    if result is None:
        return None

    ts = _parse_time(entry.get("timestamp", ""))
    time_str = ts.strftime(_TIME_FMT) if ts else "??:??:??"
    level_tag = _level_tag(level)

    return f"{_DIM}{time_str}{_RESET} {level_tag} {result}"


def _parse_time(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _level_tag(level: str) -> str:
    if level == "ERROR":
        return f"{_RED}[E]{_RESET}"
    if level == "WARNING":
        return f"{_YELLOW}[W]{_RESET}"
    if level == "DEBUG":
        return f"{_DIM}[D]{_RESET}"
    return "   "


# ═══════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════

def _load_logs(since: datetime | None, layer: str | None) -> list[dict]:
    entries = []
    if not LOG_DIR.is_dir():
        print(f"log dir not found: {LOG_DIR}")
        return entries

    for f in sorted(LOG_DIR.iterdir()):
        if not f.is_file():
            continue
        if not (f.suffix == ".log" or _is_archive(f.name)):
            continue

        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if since is not None:
                    ts = _parse_time(entry.get("timestamp", ""))
                    if ts is None or ts < since:
                        continue

                if layer is not None:
                    allowed = set(layer.split(","))
                    cat = entry.get("category", "service")
                    if cat not in allowed:
                        continue

                entries.append(entry)

    entries.sort(key=lambda e: e.get("timestamp", ""))
    return entries


def _is_archive(name: str) -> bool:
    return bool(re.search(r"\.log\.\d{4}-\d{2}-\d{2}$", name))


# ═══════════════════════════════════════════════════════
# 输出模式
# ═══════════════════════════════════════════════════════

def _output_timeline(entries: list[dict], verbose: bool):
    count = 0
    skipped = 0
    for entry in entries:
        line = _translate(entry, verbose)
        if line is None:
            skipped += 1
            continue
        print(line)
        count += 1

    print()
    print(f"Total: {count} lines", end="")
    if skipped > 0:
        print(f"  (skipped {skipped} DEBUG/noise, use --verbose to expand)", end="")
    print()


def _output_summary(entries: list[dict], verbose: bool):
    if not verbose:
        entries = [e for e in entries if e.get("level") != "DEBUG"]

    route_counter = Counter()
    status_counter = Counter()
    event_counter = Counter()
    error_list = []

    for entry in entries:
        msg = entry.get("message", "")
        category = entry.get("category", "service")

        # 路由统计
        m = re.search(r"(GET|POST|PUT|DELETE|PATCH)\s+(\S+)\s+->\s+(\d+)", msg)
        if m:
            method, path, status = m.groups()
            route_counter[f"{method} {path}"] += 1
            status_counter[status] += 1

        # 业务事件
        if category == "service":
            label = _service_event_label(entry)
            if label:
                event_counter[label] += 1

        # 错误
        if entry.get("level") == "ERROR":
            error_list.append(entry)

    print("=" * 60)
    print("  ACCESS LAYER - Route Stats")
    print("=" * 60)
    if route_counter:
        print(f"\n  {'Route':<38} {'Count':>6}")
        print(f"  {'-'*38} {'-'*6}")
        for route, cnt in route_counter.most_common(20):
            print(f"  {route:<38} {cnt:>6}")
        print()

    if status_counter:
        print(f"  {'Status':<8} {'Count':>6}  Description")
        print(f"  {'-'*8} {'-'*6}  {'-'*12}")
        for code in sorted(status_counter):
            desc = _status_desc(code)
            cnt = status_counter[code]
            print(f"  {code:<8} {cnt:>6}  {desc}")
        print()

    print("=" * 60)
    print("  SERVICE LAYER - Event Stats")
    print("=" * 60)
    if event_counter:
        print()
        for event, cnt in event_counter.most_common(30):
            print(f"  {cnt:>4}  {event}")
        print()

    print("=" * 60)
    print(f"  ERRORS ({len(error_list)} total)")
    print("=" * 60)
    if error_list:
        print()
        for e in error_list[-10:]:
            ts = _parse_time(e.get("timestamp", ""))
            time_str = ts.strftime(_FULL_TIME_FMT) if ts else "?"
            msg = e.get("message", "")[:120]
            print(f"  {time_str}  {_RED}{msg}{_RESET}")
        print()

    print(f"Total log entries: {len(entries)}")


def _service_event_label(entry: dict) -> str | None:
    msg = entry.get("message", "")
    logger = entry.get("logger", "")

    if "用户已创建" in msg:
        return "user.register"
    if "登录态验证通过" in msg:
        return "crawler.cookie_verify"
    if "已加载豆瓣登录态" in msg:
        return "crawler.cookie_load"
    if "CrawlerEngine" in msg:
        return "crawler.engine"
    if "爬取" in msg:
        return "crawler.task"
    if "movie" in logger.lower() and "Service" in logger:
        return "movie.query"
    if "auth_service" in logger or "AuthService" in logger:
        return "auth.operation"
    if "review" in logger.lower() or "评论" in msg:
        return "review.operation"
    return None


def _status_desc(code: str) -> str:
    return {
        "200": "OK",
        "201": "Created",
        "400": "Bad Request",
        "401": "Unauthorized",
        "403": "Forbidden",
        "404": "Not Found",
        "500": "Server Error",
    }.get(code, "")


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

def _parse_since(raw: str) -> datetime | None:
    if not raw:
        return None

    # HH:MM shorthand -> today
    m = re.match(r"^(\d{1,2}):(\d{2})$", raw)
    if m:
        return datetime.now(CST).replace(
            hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0
        )

    # Full ISO
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        print(f"Error: cannot parse time '{raw}', use YYYY-MM-DDTHH:MM or HH:MM")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Log analyzer - translate structured JSON logs to plain language",
    )
    parser.add_argument("--since", help="Only show logs after this time (ISO or HH:MM)")
    parser.add_argument("--layer", help="Filter by layer: access, service, infra (comma-separated for multiple)")
    parser.add_argument("--summary", action="store_true", help="Summary mode (aggregate stats)")
    parser.add_argument("--verbose", action="store_true", help="Show DEBUG logs and noise")
    args = parser.parse_args()

    since = _parse_since(args.since)

    print(f"  Log dir: {LOG_DIR}")
    if since:
        print(f"  Since:   {since.strftime(_FULL_TIME_FMT)}")
    if args.layer:
        print(f"  Layer:   {args.layer}")
    print()

    entries = _load_logs(since, args.layer)
    if not entries:
        print("(no matching logs)")
        return

    if args.summary:
        _output_summary(entries, args.verbose)
    else:
        _output_timeline(entries, args.verbose)


if __name__ == "__main__":
    main()
