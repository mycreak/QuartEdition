"""
utils/serializers.py

统一的日期时间序列化工具。

所有 datetime 统一输出为带时区的 ISO 8601 字符串（东八区 CST=UTC+08:00）。
naive datetime（如 MySQL 返回的、旧代码中的 datetime.utcnow()）
自动附加东八区时区后再序列化。

解决了 ``datetime.isoformat()`` 散落在 3 个文件中的问题：
    - storage.py       → MongoDB 写入 crawled_at
    - movie_service.py → 版本历史快照
    - task_failure_service.py → 失败记录序列化

使用方式：
    from utils.serializers import to_iso, serialize_datetime_fields, CST

    "crawled_at": to_iso(datetime.now(CST))  # → '2024-05-06T20:00:00+08:00'
    clean[k] = to_iso(v)
    serialize_datetime_fields(row, ["created_at", "claimed_at"])
"""

from datetime import date as date_type, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# 东八区时区常量
CST = timezone(timedelta(hours=8))


def to_iso(value: Any) -> Any:
    """
    安全转换 datetime / date 对象为带东八区时区的 ISO 8601 字符串。

    - datetime → 自动附加东八区时区（naive 时）→ '2024-05-06T12:00:00+08:00'
    - date     → '2024-05-06'
    - None     → None
    - 其他类型 → 原样返回

    输入：datetime / date / str / int / None / 任意对象
    输出：ISO 字符串（datetime/date）或原始值
    副作用：无

    >>> to_iso(datetime(2024, 5, 6, 12, 0, 0))
    '2024-05-06T12:00:00+08:00'
    >>> to_iso(datetime(2024, 5, 6, 12, 0, 0, tzinfo=timezone.utc))
    '2024-05-06T12:00:00+00:00'
    >>> to_iso(None)
    None
    >>> to_iso("already_string")
    'already_string'
    >>> to_iso(42)
    42
    """
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=CST)
        return value.isoformat()
    return value


def serialize_datetime_fields(
    row: Dict[str, Any],
    fields: List[str],
) -> Dict[str, Any]:
    """
    批量转换一行数据中的 datetime 字段为 ISO 字符串。

    输入：
        row:    MySQL aiomysql DictCursor 返回的原始 dict
        fields: 需要转换的字段名列表
    输出：新 dict（不修改原 row）
    副作用：无
    """
    result = dict(row)
    for key in fields:
        result[key] = to_iso(result.get(key))
    return result
