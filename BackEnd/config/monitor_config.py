"""
config/monitor_config.py

Monitor 调优参数集中管理（pydantic-settings，环境变量前缀 MONITOR_）。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class MonitorConfig(BaseSettings):
    """
    Monitor 调优参数（可通过 .env 的 MONITOR_* 覆盖）。

    轮询控制：
        interval:              轮询间隔秒数（默认 10s）
        max_events_per_cycle:  单次最多消费事件数（默认 500）
        worker_timeout_alert:  Worker 卡死告警阈值（默认 300s）

    数据库异常检测：
        storage_window_seconds:   storage 失败滑动窗口大小（默认 300 = 5 分钟）
        storage_alert_threshold:  窗口内触发告警的最小次数（默认 3）
        storage_alert_cooldown:   两次告警之间的冷却秒数（默认 120）
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MONITOR_",
        extra="ignore",
    )

    interval: int = 10
    max_events_per_cycle: int = 500
    worker_timeout_alert: int = 300

    storage_window_seconds: int = 300
    storage_alert_threshold: int = 3
    storage_alert_cooldown: int = 120


# 全局配置单例 — 自动读 .env 中 MONITOR_* 变量
monitor_config = MonitorConfig()
