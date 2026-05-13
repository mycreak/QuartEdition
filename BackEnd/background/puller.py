"""
background/puller.py

延迟任务拉取器。
负责从 Redis 延迟队列（ZSet）中拉取到期的任务，放入 asyncio.Queue 供 Worker 消费。

设计原则：
    - Redis 连接由基础设施层（db/redis.py）统一管理，Puller 不负责重连。
    - 数据库操作通过 DatabaseLayer 统一接口执行，不直接操作 Redis 客户端。
    - 背压控制采用双阈值回滞机制，避免边界抖动。
    - 无任务时采用指数退避休眠，减少空转。
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from db.database_v2 import DatabaseLayerV2

from config import puller_config as default_config
from config.puller_config import PullerConfig

logger = logging.getLogger(__name__)


class PullerState(Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    BACKPRESSURE = "backpressure"
    STOPPED = "stopped"


@dataclass
class PullerStats:
    total_fetched: int = 0
    total_empty_polls: int = 0
    backpressure_enter_count: int = 0
    backpressure_exit_count: int = 0
    backpressure_duration: float = 0.0
    last_fetch_time: float = 0.0
    last_backpressure_time: float = 0.0
    started_at: float = 0.0


class Puller:
    """
    延迟任务拉取器。

    使用示例：
        puller = Puller(task_queue=app.task_queue, db_layer=app.db)
        await puller.run()
    """

    def __init__(
        self,
        task_queue: asyncio.Queue,
        db_layer: DatabaseLayerV2,
        config: Optional[PullerConfig] = None,
    ):
        """
        Args:
            task_queue: 来自 app.py 的异步任务队列，Puller 将任务放入，Worker 从中取走。
            db_layer: DatabaseLayerV2 实例，通过其统一接口操作 Redis 延迟队列。
            config: Puller 调优参数，未传入时使用全局默认配置。
        """
        self.task_queue = task_queue
        self.db = db_layer
        self.config = config or default_config

        self._state = PullerState.INITIALIZED
        self._empty_wait = self.config.base_sleep

        self.stats = PullerStats()

    @property
    def state(self) -> str:
        return self._state.value

    async def stop(self):
        """
        停止 Puller。

        设置 STOPPED 状态 → run() 主循环下次迭代检测到后 break 退出，
        实现优雅关闭（不强行 cancel，不丢中间状态）。
        """
        self._state = PullerState.STOPPED
        logger.info("Puller 收到停止信号")

    async def run(self):
        """
        Puller 主循环。

        每次迭代：
            1. 检查停止信号（STOPPED → 退出）
            2. 检查队列饱和度，通过双阈值回滞控制背压状态。
            3. 从 Redis 拉取到期任务，空结果触发指数退避。
            4. 将任务放入 asyncio.Queue。
        """
        self._state = PullerState.RUNNING
        self.stats.started_at = time.time()
        logger.info("Puller 启动")

        try:
            while True:
                # ── 0. 停止信号检测（时机：每次迭代起始，含 backpressure continue 后） ──
                if self._state == PullerState.STOPPED:
                    logger.info("Puller 检测到 STOPPED，退出主循环")
                    break

                # ── 1. 队列饱和检查（双阈值回滞） ──
                queue_max = self.task_queue.maxsize
                qsize = self.task_queue.qsize()
                high_watermark = queue_max * self.config.backpressure_high
                low_watermark = queue_max * self.config.backpressure_low

                if self._state != PullerState.BACKPRESSURE and qsize >= high_watermark:
                    self._state = PullerState.BACKPRESSURE
                    self.stats.backpressure_enter_count += 1
                    self.stats.last_backpressure_time = time.time()
                    logger.info(
                        f"队列饱和 ({qsize}/{queue_max})，进入背压状态"
                    )

                if self._state == PullerState.BACKPRESSURE:
                    if qsize <= low_watermark:
                        self._state = PullerState.RUNNING
                        self.stats.backpressure_exit_count += 1
                        self.stats.backpressure_duration += (
                            time.time() - self.stats.last_backpressure_time
                        )
                        logger.info(
                            f"队列恢复 ({qsize}/{queue_max})，退出背压状态"
                        )
                    else:
                        await asyncio.sleep(self.config.backpressure_sleep)
                        continue

                # ── 2. 拉取到期任务 ──
                tasks = await self.db.batch_pop_due_tasks(
                    now=time.time(),
                    limit=self.config.batch_size,
                )

                if not tasks:
                    self.stats.total_empty_polls += 1
                    await asyncio.sleep(self._empty_wait)
                    self._empty_wait = min(
                        self._empty_wait * 1.5,
                        self.config.max_sleep,
                    )
                    continue

                # ── 3. 放入任务队列 ──
                self._empty_wait = self.config.base_sleep
                self.stats.last_fetch_time = time.time()
                for task in tasks:
                    await self.task_queue.put(task)
                    self.stats.total_fetched += 1

                logger.debug(
                    f"拉取并放入 {len(tasks)} 个任务, "
                    f"队列: {self.task_queue.qsize()}/{queue_max}"
                )

        except asyncio.CancelledError:
            self._state = PullerState.STOPPED
            logger.info("Puller 已停止")
            raise

        except Exception:
            self._state = PullerState.STOPPED
            logger.exception("Puller 因异常退出")
            raise


# ==================== 模块级单例管理 ====================

_puller_instance: Optional[Puller] = None


async def init_puller(task_queue: asyncio.Queue, db_layer: DatabaseLayerV2) -> Puller:
    """
    初始化 Puller 单例。

    Args:
        task_queue: asyncio.Queue 实例。
        db_layer: DatabaseLayerV2 实例（已初始化）。

    Returns:
        Puller 实例。
    """
    global _puller_instance
    _puller_instance = Puller(task_queue=task_queue, db_layer=db_layer)
    logger.info("Puller 单例已初始化")
    return _puller_instance


async def get_puller() -> Puller:
    """获取 Puller 单例，未初始化时抛出 RuntimeError。"""
    if _puller_instance is None:
        raise RuntimeError("Puller 未初始化，请先调用 init_puller()")
    return _puller_instance


async def start_puller():
    """
    启动 Puller 后台任务。
    由 app.add_background_task() 调用，以协程形式运行 Puller.run()。
    """
    puller = await get_puller()
    await puller.run()


async def stop_puller():
    """
    停止 Puller。
    由 app.after_serving 钩子调用，触发 Puller 的优雅关闭逻辑。
    """
    puller = await get_puller()
    await puller.stop()
