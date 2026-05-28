"""
config/puller_config.py

Puller 调优参数集中管理（pydantic-settings，环境变量前缀 PULLER_）。
包含背压控制、休眠策略、拉取控制等可配置参数，便于不同环境切换。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class PullerConfig(BaseSettings):
    """
    Puller 调优参数（可通过 .env 的 PULLER_* 覆盖）。

    背压控制（双阈值回滞）：
        backpressure_high: 进入背压水位线（默认 0.8）
        backpressure_low:  退出背压水位线（默认 0.6）
        high/long 回滞区避免边界抖动。

    休眠策略：
        base_sleep:         无任务初始休眠（默认 0.1s）
        max_sleep:          指数退避上限（默认 5.0s）
        backpressure_sleep: 背压态固定休眠（默认 0.5s）

    拉取控制：
        batch_size: 单次批量弹出数（默认 10）

    任务限速：
        task_cooldown_seconds: 相邻任务最小间隔（默认 2.0s）

    Worker 执行后休息（反爬核心）：
        worker_rest_min: 每任务执行完后最少休息（默认 150s）
        worker_rest_max: 每任务执行完后最多休息（默认 250s）
        5 Worker 各自独立休息，自然错峰——休息期间不持任务、不计 busy
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PULLER_",
        extra="ignore",
    )

    backpressure_high: float = 0.8
    backpressure_low: float = 0.6

    base_sleep: float = 0.1
    max_sleep: float = 5.0
    backpressure_sleep: float = 0.5

    batch_size: int = 10

    task_cooldown_seconds: float = 2.0
    worker_rest_min: float = 120.0
    worker_rest_max: float = 180.0


# 全局配置单例 — 自动读 .env 中 PULLER_* 变量
puller_config = PullerConfig()
