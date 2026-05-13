"""
utils/snowflake.py

Snowflake 雪花ID生成器（基于 Twitter Snowflake 算法）。

ID 结构（64位）:
┌─┬──────────────────────────────────────┬───────────┬────────────────────┐
│0│             41 bit 时间戳             │ 10 bit    │    12 bit 序列号    │
│ │         (毫秒，epoch 2026-01-01)       │ 机器ID    │     (同毫秒内递增)   │
└─┴──────────────────────────────────────┴───────────┴────────────────────┘

特性:
    - 全局唯一、趋势递增（可做数据库主键）
    - 每毫秒 4096 个 ID，单机 QPS 远超实际需求
    - 不依赖外部服务，纯内存生成

使用方式:
    from utils.snowflake import init_snowflake, generate_id

    init_snowflake(machine_id=1)  # 每个部署实例唯一
    task_id = generate_id()       # → 1234567890123456789
"""

import threading
import time

# epoch: 2026-01-01 00:00:00 UTC 的毫秒时间戳
EPOCH = 1767225600000

# 位数分配
MACHINE_BITS = 10
SEQUENCE_BITS = 12

# 掩码
MAX_MACHINE_ID = (1 << MACHINE_BITS) - 1   # 1023
MAX_SEQUENCE  = (1 << SEQUENCE_BITS) - 1   # 4095

# 位移
TIMESTAMP_SHIFT = MACHINE_BITS + SEQUENCE_BITS
MACHINE_SHIFT   = SEQUENCE_BITS


class SnowflakeGenerator:
    """
    Snowflake ID 生成器（线程安全）。

    输入:
        machine_id: 机器编号（0~1023），每个部署实例唯一
    输出:
        64-bit 正整数，转为字符串使用
    副作用:
        更新内部计数器
    """

    def __init__(self, machine_id: int):
        if not (0 <= machine_id <= MAX_MACHINE_ID):
            raise ValueError(f"machine_id 必须在 0~{MAX_MACHINE_ID} 之间，实际: {machine_id}")

        self._machine_id = machine_id
        self._sequence = 0
        self._last_timestamp = -1
        self._lock = threading.Lock()  # asyncio 单线程安全；若引入多线程需改用 asyncio.Lock()

    def next_id(self) -> int:
        """
        生成下一个唯一 ID。

        异常:
            RuntimeError — 时钟回拨超过容忍范围
        """
        with self._lock:
            timestamp = self._current_millis()

            # 时钟回拨检测
            if timestamp < self._last_timestamp:
                drift = self._last_timestamp - timestamp
                if drift > 1000:
                    raise RuntimeError(
                        f"时钟回拨 {drift}ms，拒绝生成 ID（超过 1s 容忍范围）"
                    )
                # 小幅度回拨：等待追上
                timestamp = self._last_timestamp

            if timestamp == self._last_timestamp:
                # 同毫秒：序列号递增
                self._sequence = (self._sequence + 1) & MAX_SEQUENCE
                if self._sequence == 0:
                    # 序列号耗尽：等待下一毫秒
                    timestamp = self._wait_next_millis(self._last_timestamp)
            else:
                # 新毫秒：序列号归零
                self._sequence = 0

            self._last_timestamp = timestamp

            return (
                ((timestamp - EPOCH) << TIMESTAMP_SHIFT)
                | (self._machine_id << MACHINE_SHIFT)
                | self._sequence
            )

    @staticmethod
    def _current_millis() -> int:
        """当前 Unix 毫秒时间戳。"""
        return int(time.time() * 1000)

    @staticmethod
    def _wait_next_millis(last_timestamp: int) -> int:
        """
        自旋等待下一毫秒。

        ⚠️ 纯自旋忙等 — 若当前毫秒内 4096 个序列号耗尽（~400万 QPS），
        会阻塞事件循环 ~1ms。生产环境正常 QPS 下不会触发。
        """
        timestamp = int(time.time() * 1000)
        while timestamp <= last_timestamp:
            timestamp = int(time.time() * 1000)
        return timestamp


# 模块级单例
_generator: SnowflakeGenerator = None


def init_snowflake(machine_id: int = 1) -> SnowflakeGenerator:
    """
    初始化 Snowflake ID 生成器。

    输入:
        machine_id: 机器编号（0~1023），分布式部署时每台实例分配不同编号
    输出:
        SnowflakeGenerator 实例
    副作用:
        设置模块级 _generator
    """
    global _generator
    _generator = SnowflakeGenerator(machine_id)
    return _generator


def generate_id() -> int:
    """
    生成全局唯一 ID。

    输入: 无
    输出: 64-bit 正整数
    异常: RuntimeError — 未初始化
    """
    if _generator is None:
        raise RuntimeError("Snowflake 未初始化，请先调用 init_snowflake(machine_id=1)")
    return _generator.next_id()
