"""
background/worker.py

任务执行池（BrowserPool）。

架构变更（Playwright 迁移）：
    - Worker + WorkerPool 合并为 BrowserPool 单一类
    - 固定 worker_count 个并发槽位（默认 5），不再支持动态伸缩
    - WorkerState 枚举删除，busy/idle 通过计数器追踪
    - 浏览器资源由 BrowserFetcher 内部管理，BrowserPool 是纯调度器

设计原则：
    - Worker 只负责"从 Queue 取任务 → 执行 → 上报事件"，不关心业务逻辑。
    - 业务逻辑通过 execute_func 回调注入，便于测试和替换。
    - 执行结果（成功/失败/取消）通过 event_queue 上报，与 Monitor 解耦。
    - 浏览器实例由外部（app.py）创建并注入给 crawler，BrowserPool 不持有。
"""

import asyncio
import json
import logging
import random
import time
from typing import Callable, Coroutine, Optional

from crawler.failure_service import WorkerEvent, EventType, classify_exception

logger = logging.getLogger(__name__)


class BrowserPool:
    """
    固定容量的任务执行池。

    管理 N 个 Worker 协程，每个 Worker 从 task_queue 取任务，
    调用 execute_func 执行业务逻辑，将结果上报 event_queue。

    与旧 WorkerPool 的关键区别：
        - 不维护 Worker 对象列表，不维护独立的状态枚举
        - busy_count 通过计数器追踪（原子性由 asyncio 单线程模型保证）
        - 不支持 add_worker / remove_worker（固定容量）
        - 不持有浏览器资源（页面生命周期由 BrowserFetcher 内部管理）

    使用方式：
        pool = BrowserPool(
            task_queue=app.task_queue,
            execute_func=crawler.execute,
            event_queue=app.worker_event_queue,
            worker_count=5,
        )
        await pool.start()
        # ... 运行中 ...
        await pool.stop()
    """

    def __init__(
        self,
        task_queue: asyncio.Queue,
        execute_func: Callable[[str], Coroutine],
        event_queue: asyncio.Queue,
        worker_count: int = 5,
    ):
        """
        Args:
            task_queue:    任务队列，Puller 写入，Worker 读取
            execute_func:  业务执行函数，签名 async (task: str) -> None
            event_queue:   事件上报队列，Monitor 消费
            worker_count:  固定 Worker 数量（默认 5，与浏览器内存预算匹配）
        """
        self.task_queue = task_queue
        self.execute = execute_func
        self.event_queue = event_queue
        self._worker_count = worker_count

        self._tasks: list[asyncio.Task] = []
        self._busy_counter = 0
        self._busy_since: dict[int, float] = {}
        self._cooldown_since: dict[int, float] = {}  # worker 开始冷却的时间戳
        self._cooldown_until: dict[int, float] = {}  # worker 冷却结束的时间戳
        self._worker_crashed_count = 0
        self._worker_current_task: dict[int, str] = {}
        self._shutting_down = False  # shutdown 标志：防止 restart_dead_workers 误复活

    @property
    def busy_count(self) -> int:
        """
        当前正在执行任务的 Worker 数量。

        asyncio 单线程模型保证了读写原子性，无需加锁。
        """
        return self._busy_counter

    def get_current_task(self, worker_id: int) -> Optional[str]:
        """获取指定 Worker 当前执行的任务 JSON（用于 Monitor 崩溃诊断）。"""
        return self._worker_current_task.get(worker_id)

    @property
    def idle_count(self) -> int:
        """当前空闲的 Worker 数量（不含冷却中）。"""
        return self._worker_count - self._busy_counter - self.cooldown_count

    @property
    def cooldown_count(self) -> int:
        """当前冷却中的 Worker 数量。"""
        now = time.time()
        count = 0
        for wid, until in self._cooldown_until.items():
            if now < until:
                count += 1
        return count

    def get_worker_health(self) -> dict:
        """
        检测所有 Worker 任务的存活状态和卡死情况。

        两种故障形态：
            1. 死亡：asyncio.Task.done() == True → _worker_loop 异常退出
            2. 卡死：busy 时长 > 阈值 → execute() 永不返回（僵尸 Worker）

        输出：
            {
                "alive": int,              # 还活着的 Worker 数
                "expected": int,           # 应有 Worker 数
                "dead": [dict],            # 已死亡的 Worker 详情
                "stuck": [dict],           # 疑似卡死的 Worker 详情
                "crashed_total": int,      # 累计崩溃次数
                "busy_count": int,         # 当前忙碌数
                "idle_count": int,         # 当前空闲数（不含冷却）
                "cooldown_count": int,     # 当前冷却数
                "busy_since": dict,        # 各 Worker 开始忙碌的时间戳
                "cooldown_info": list[dict], # 各冷却中 Worker 的详情
            }
        副作用：只读，不修改状态
        """
        alive = 0
        dead = []
        for i, task in enumerate(self._tasks):
            if task.done():
                exc = task.exception()
                dead.append({
                    "worker_id": i,
                    "error": str(exc) if exc else "正常结束",
                })
            else:
                alive += 1

        stuck = []
        now = time.time()
        for wid, since in list(self._busy_since.items()):
            elapsed = now - since
            if elapsed > 330:  # 5.5 分钟未返回 → 疑似卡死（jitter 最大 300s + 30s 余量）
                stuck.append({
                    "worker_id": wid,
                    "busy_seconds": round(elapsed, 1),
                })

        cooldown_info = []
        for wid, until in self._cooldown_until.items():
            if now < until:
                cooldown_info.append({
                    "worker_id": wid,
                    "cooldown_remaining": round(until - now, 1),
                })

        return {
            "alive": alive,
            "expected": self._worker_count,
            "dead": dead,
            "stuck": stuck,
            "crashed_total": self._worker_crashed_count,
            "busy_count": self._busy_counter,
            "idle_count": self._worker_count - self._busy_counter - self.cooldown_count,
            "cooldown_count": self.cooldown_count,
            "busy_since": dict(self._busy_since),
            "cooldown_info": cooldown_info,
        }

    async def restart_dead_workers(self) -> int:
        """
        重启已死亡的 Worker 任务。

        只处理 done()==True 的任务（_worker_loop 异常退出）。
        卡死（stuck）的 Worker 不能自动重启——它的 asyncio.Task 仍在运行，
        强行取消可能丢任务。

        shutdown 期间不重启：_shutting_down=True 时直接返回 0。
        """
        if self._shutting_down:
            return 0

        restarted = 0
        for i, task in enumerate(self._tasks):
            if not task.done():
                continue

            exc = task.exception()
            logger.warning(
                f"Worker-{i} 已死亡（{str(exc) if exc else '正常结束'}），"
                f"正在重启..."
            )
            try:
                new_task = asyncio.create_task(
                    self._worker_loop(i),
                    name=f"browser-worker-{i}",
                )
                self._tasks[i] = new_task
                self._worker_crashed_count += 1
                restarted += 1
            except Exception as e:
                logger.error(f"Worker-{i} 重启失败: {e}")

        if restarted > 0:
            logger.info(f"已重启 {restarted} 个 Worker（累计崩溃 {self._worker_crashed_count} 次）")
        return restarted

    async def start(self):
        """
        启动固定数量的 Worker 协程。

        每个 Worker 是一个 asyncio.Task，独立运行 _worker_loop。
        start() 本身会阻塞等待所有 Task 完成（通过 gather），
        因此它必须作为后台任务启动（app.add_background_task）。
        """
        self._tasks = [
            asyncio.create_task(
                self._worker_loop(i),
                name=f"browser-worker-{i}",
            )
            for i in range(self._worker_count)
        ]
        logger.info(f"BrowserPool 启动，共 {self._worker_count} 个 Worker")
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        """停止所有 Worker 协程并等待完成（超时 30s 防止无限等待）。"""
        self._shutting_down = True
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks, return_exceptions=True),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"BrowserPool.stop() 超时 30s：{sum(1 for t in self._tasks if not t.done())} "
                    f"个 Worker 未能在超时内完成，强制继续关闭"
                )
        logger.info("BrowserPool 已停止")

    async def _worker_loop(self, worker_id: int):
        """
        单个 Worker 的主循环 — 纯调度，不持有浏览器资源。

        职责：
            task_queue.get() → execute(task) → 休息 cooldown → event_queue.put()

        反爬设计（关键变更）：
            每个 Worker 执行完任务后随机休息 120~300s，再取下一个任务。
            休息期间不持任务、不计 busy → Puller 可继续拉新任务到队列。
            5 Worker 各自独立休息，自然形成 120~300s 的请求间隔错峰。

        退出机制（双重防线）：
            ① asyncio.CancelledError — stop() 调用 task.cancel()
            ② _shutting_down 标志 — 防止 stop() 异常未走到 cancel() 时永久阻塞

        输入：
            worker_id: Worker 编号（0 ~ worker_count-1），仅用于日志和事件标识
        副作用：
            - 读写 self.task_queue（取任务、标记完成）
            - 读写 self.event_queue（上报事件）
            - 修改 self._busy_counter
        """
        while True:
            # 第二道退出防线：stop() 未能执行 cancel() 时，检查标志位主动退出
            if self._shutting_down:
                break

            task = None
            try:
                task = await self.task_queue.get()
            except asyncio.CancelledError:
                break

            self._worker_current_task[worker_id] = task
            self._busy_counter += 1
            self._busy_since[worker_id] = time.time()

            # 通知 Monitor 任务已开始执行
            await self.event_queue.put(
                WorkerEvent(
                    event_type=EventType.STARTED,
                    worker_id=worker_id,
                    task=task,
                    timestamp=time.time(),
                ).model_dump()
            )

            try:
                await self.execute(task)

                await self.event_queue.put(
                    WorkerEvent(
                        event_type=EventType.SUCCESS,
                        worker_id=worker_id,
                        task=task,
                        timestamp=time.time(),
                    ).model_dump()
                )

            except asyncio.CancelledError:
                await self.event_queue.put(
                    WorkerEvent(
                        event_type=EventType.CANCELLED,
                        worker_id=worker_id,
                        task=task if task is not None else "",
                        timestamp=time.time(),
                        reason="worker 被取消",
                    ).model_dump()
                )
                raise

            except Exception as e:
                # AI 失败时尝试从 ai_client 提取快照
                snapshot = None
                try:
                    tdata = json.loads(task) if task else {}
                    if tdata.get("type") in ("ai_review_summary", "ai_wordcloud"):
                        from utils.ai_client import get_ai_client
                        ai_client = get_ai_client()
                        snapshot = getattr(ai_client, 'last_snapshot', None)
                except Exception:
                    pass

                await self.event_queue.put(
                    WorkerEvent(
                        event_type=EventType.FAILURE,
                        worker_id=worker_id,
                        task=task if task is not None else "",
                        timestamp=time.time(),
                        kind=classify_exception(e),
                        reason=str(e),
                        snapshot=snapshot,
                    ).model_dump()
                )

            finally:
                self._busy_counter -= 1
                self._busy_since.pop(worker_id, None)
                self._worker_current_task.pop(worker_id, None)
                self.task_queue.task_done()

            # Worker 执行后随机休息 — 5 Worker 自然错峰
            from config.puller_config import puller_config
            cooldown = random.uniform(
                puller_config.worker_rest_min,
                puller_config.worker_rest_max,
            )
            now = time.time()
            self._cooldown_since[worker_id] = now
            self._cooldown_until[worker_id] = now + cooldown
            logger.debug(
                f"Worker-{worker_id} 任务完成，cooldown={cooldown:.0f}s 后取下一个任务"
            )
            try:
                await asyncio.sleep(cooldown)
            finally:
                self._cooldown_since.pop(worker_id, None)
                self._cooldown_until.pop(worker_id, None)


# ==================== 虚拟执行器 ====================


async def dummy_execute(
    task: str,
    *,
    force_result: Optional[bool] = None,
) -> None:
    """
    虚拟任务执行器。

    用于开发和测试阶段，模拟真实任务执行。

    Args:
        task: 任务 JSON 字符串。
        force_result:
            - True: 必定成功
            - False: 必定失败（抛 RuntimeError）
            - None: 50% 概率成功/失败

    Raises:
        RuntimeError: 任务执行失败时抛出。
    """
    data = json.loads(task)
    await asyncio.sleep(0.05)

    if force_result is False:
        raise RuntimeError(f"模拟失败：任务 {data['id']}")

    if force_result is True:
        return

    if random.random() < 0.5:
        raise RuntimeError(f"随机失败：任务 {data['id']}")


# ==================== 模块级单例管理 ====================

_pool_instance: Optional[BrowserPool] = None


async def init_browser_pool(
    task_queue: asyncio.Queue,
    execute_func: Callable[[str], Coroutine],
    event_queue: asyncio.Queue,
    worker_count: int = 5,
) -> BrowserPool:
    """
    初始化 BrowserPool 单例。

    Args:
        task_queue:    任务队列
        execute_func:  业务执行函数
        event_queue:   事件队列
        worker_count:  固定 Worker 数量（默认 5）

    Returns:
        BrowserPool 实例
    """
    global _pool_instance
    _pool_instance = BrowserPool(
        task_queue=task_queue,
        execute_func=execute_func,
        event_queue=event_queue,
        worker_count=worker_count,
    )
    logger.info("BrowserPool 单例已初始化")
    return _pool_instance


def get_browser_pool() -> BrowserPool:
    """获取 BrowserPool 单例，未初始化时抛出 RuntimeError。"""
    if _pool_instance is None:
        raise RuntimeError("BrowserPool 未初始化，请先调用 init_browser_pool()")
    return _pool_instance


async def start_browser_pool():
    """启动 BrowserPool。"""
    pool = get_browser_pool()
    await pool.start()


async def stop_browser_pool():
    """停止 BrowserPool。"""
    pool = get_browser_pool()
    await pool.stop()
