"""
utils/logging_config.py

结构化 JSON 日志配置 + 分类持久化。

用途：
    按三层架构自动分类日志，便于前后端联调时按层次查看。

分类规则（三层架构）：
    access      接入层    → access.log     谁在敲门：API 路由 / WebSocket / 服务器
    service     业务层    → service.log    干了什么：注册、爬取、搜索等业务逻辑
    infra       基础设施   → infra.log      底座是否正常：数据库 / 任务调度 / 工具
    所有 ERROR+ 汇总      → error.log     跨三层的错误快速定位

使用方式（app.py）：
    from utils.logging_config import setup_logging
    setup_logging()

环境变量（.env）：
    LOG_DIR=logs          — 日志目录（相对 BackEnd/）
    LOG_LEVEL=INFO        — 控制台最低级别
    LOG_FORMAT=json       — json（生产）| txt（开发）
    LOG_TO_FILE=true      — 是否写文件
    LOG_BACKUP_DAYS=30    — 文件保留天数
"""

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

# 东八区时区常量
CST = timezone(timedelta(hours=8))


class LogCategory(str, Enum):
    """三层架构分类，同时也是文件名（不含后缀）。"""
    ACCESS = "access"
    SERVICE = "service"
    INFRA = "infra"
    ERROR = "error"


_CATEGORY_MAP: dict[str, LogCategory] = {
    "routes.": LogCategory.ACCESS,
    "hypercorn": LogCategory.ACCESS,
    "services.": LogCategory.SERVICE,
    # crawler.* 与 services.* 同归 SERVICE → 混在 service.log
    # 若爬虫高频生产，建议新增 CRAWLER 分类独立 crawler.log
    "crawler.": LogCategory.SERVICE,
    "db.": LogCategory.INFRA,
    "background.": LogCategory.INFRA,
    "utils.": LogCategory.INFRA,
}


def _get_category(logger_name: str) -> LogCategory:
    """根据 logger 名称返回所属分层，未匹配默认归入 SERVICE（业务层）。"""
    for prefix, category in _CATEGORY_MAP.items():
        if logger_name.startswith(prefix):
            return category
    return LogCategory.SERVICE


class CategoryFilter(logging.Filter):
    """Handler 级别的过滤器：只允许指定分层的日志通过。"""
    def __init__(self, category: LogCategory):
        super().__init__()
        self.category = category

    def filter(self, record: logging.LogRecord) -> bool:
        return _get_category(record.name) == self.category


class JsonFormatter(logging.Formatter):
    """将日志记录格式化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(CST).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "category": _get_category(record.name).value,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            import traceback
            entry["exc_info"] = traceback.format_exception(*record.exc_info)
        entry["module"] = record.module
        entry["function"] = record.funcName
        entry["line"] = record.lineno
        return json.dumps(entry, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """可读的文本格式（本地开发用）。"""
    def __init__(self):
        super().__init__(
            "[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def _setup_handlers(
    log_dir: Path,
    log_level: int,
    use_json: bool,
    backup_days: int,
) -> list[logging.Handler]:
    """创建并返回所有 handler（控制台 + 三层架构文件 + 错误汇总）。

    输入：
        log_dir     — 日志文件输出目录
        log_level   — 控制台最低日志级别
        use_json    — True=JSON 格式，False=文本格式
        backup_days — 日志文件保留天数

    返回：
        handler 列表，由调用方挂到 root logger 上
    """
    handlers: list[logging.Handler] = []

    formatter: logging.Formatter = JsonFormatter() if use_json else TextFormatter()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(log_level)
    handlers.append(console)

    if os.getenv("LOG_TO_FILE", "true").lower() == "true":
        log_dir.mkdir(parents=True, exist_ok=True)

        for category in (
            LogCategory.ACCESS,
            LogCategory.SERVICE,
            LogCategory.INFRA,
        ):
            filepath = log_dir / f"{category.value}.log"
            handler = logging.handlers.TimedRotatingFileHandler(
                filename=str(filepath),
                when="midnight",
                interval=1,
                backupCount=backup_days,
                encoding="utf-8",
                delay=True,
            )
            handler.setFormatter(formatter)
            handler.setLevel(logging.DEBUG)
            handler.addFilter(CategoryFilter(category))
            handlers.append(handler)

        error_path = log_dir / f"{LogCategory.ERROR.value}.log"
        error_handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(error_path),
            when="midnight",
            interval=1,
            backupCount=backup_days,
            encoding="utf-8",
            delay=True,
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        handlers.append(error_handler)

    return handlers


def setup_logging(log_level: Optional[int] = None):
    """
    配置根 logger：控制台 + 分层文件 + 错误汇总。

    输入：
        log_level — 控制台最低级别，默认从 .env 读取 LOG_LEVEL

    副作用：
        1. 创建 log_dir 目录（如 logs/）
        2. 替换 root logger 的所有 handler
        3. 静默第三方库的 DEBUG 日志
    """
    if log_level is None:
        level_name = os.getenv("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, level_name, logging.INFO)

    use_json = os.getenv("LOG_FORMAT", "json").lower() != "txt"
    backup_days = int(os.getenv("LOG_BACKUP_DAYS", "30"))

    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    if not log_dir.is_absolute():
        log_dir = Path(__file__).resolve().parent.parent / log_dir

    handlers = _setup_handlers(log_dir, log_level, use_json, backup_days)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    for handler in handlers:
        root.addHandler(handler)

    for noisy in ("asyncio", "urllib3", "aiomysql", "motor", "playwright", "hypercorn", "pymongo"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


setup_json_logging = setup_logging
