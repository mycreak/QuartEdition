"""
background/monitor.py

系统状态监视器（Monitor）。

职责（每轮轮询）：
    1. 采集 Puller 指标（状态、统计、队列饱和度）。
    2. 采集 BrowserPool 指标（空闲/繁忙）。
    3. 消费 Worker 事件队列（成功只计数，失败/取消写入 MySQL）。
    4. 采集系统资源（CPU、内存）。
    5. 检查三大数据库连接健康状态。
    6. 输出本轮报告日志。

设计原则：
    - 单协程周期运行，不产生额外后台任务。
    - 单轮内任何步骤失败不影响后续步骤和下一轮。
"""

import asyncio
import json
import logging
import time
from enum import Enum
from typing import Optional

from config import monitor_config as default_config
from config.monitor_config import MonitorConfig
from background.puller import get_puller
from background.worker import get_browser_pool
from utils.system_monitor import get_system_health
from crawler.failure_service import WorkerEvent, EventType

logger = logging.getLogger(__name__)


class MonitorState(Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"


class Monitor:
    """
    系统状态监视器。

    周期性采集系统各组件指标、消费 Worker 事件、决策伸缩。
    """

    def __init__(
        self,
        task_queue: asyncio.Queue,
        worker_event_queue: asyncio.Queue,
        db_layer,
        config: Optional[MonitorConfig] = None,
        ws_manager=None,
    ):
        """
        Args:
            task_queue: 任务队列（来自 app.py），用于监控队列饱和度。
            worker_event_queue: Worker 事件队列，Monitor 消费其中的执行结果。
            db_layer: DatabaseLayerV2 实例，用于数据库健康检查和写入失败事件。
            config: Monitor 调优参数。
            ws_manager: WebSocketManager 实例，用于推送失败通知。
        """
        self.task_queue = task_queue
        self.worker_event_queue = worker_event_queue
        self.db = db_layer
        self.config = config or default_config
        self.ws_manager = ws_manager

        self._state = MonitorState.INITIALIZED

        self.success_count = 0
        self.failure_count = 0
        self.cancelled_count = 0

    @property
    def state(self) -> str:
        return self._state.value

    async def stop(self):
        """停止 Monitor。"""
        self._state = MonitorState.STOPPED
        logger.info("Monitor 已停止")

    async def run(self):
        """Monitor 主循环：每 interval 秒执行一轮监控。"""
        self._state = MonitorState.RUNNING
        logger.info(
            f"Monitor 启动，轮询间隔 {self.config.interval} 秒"
        )

        try:
            while True:
                # ── 0. 停止信号检测（在轮询休眠之上，保证及时响应） ──
                if self._state == MonitorState.STOPPED:
                    logger.info("Monitor 检测到 STOPPED，退出主循环")
                    break

                cycle_start = time.time()
                try:
                    await self._run_cycle()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Monitor 本轮执行异常")

                elapsed = time.time() - cycle_start
                sleep_time = max(0, self.config.interval - elapsed)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            self._state = MonitorState.STOPPED
            logger.info("Monitor 已停止")
            raise

    async def _run_cycle(self):
        """执行单轮监控。"""
        report = {}

        # ── 1. 采集 Puller 指标 ──
        try:
            puller = await get_puller()
            report["puller_state"] = puller.state
            report["puller_fetched"] = puller.stats.total_fetched
            report["puller_empty_polls"] = puller.stats.total_empty_polls
            report["puller_backpressure_count"] = puller.stats.backpressure_enter_count
            report["puller_backpressure_duration"] = round(
                puller.stats.backpressure_duration, 2
            )
        except Exception as e:
            report["puller_error"] = str(e)

        # ── 2. 采集队列指标 ──
        try:
            qsize = self.task_queue.qsize()
            report["queue_size"] = qsize
            report["queue_maxsize"] = self.task_queue.maxsize
            report["queue_saturation"] = round(
                qsize / self.task_queue.maxsize, 2
            )
        except Exception as e:
            report["queue_error"] = str(e)

        # ── 3. 采集 BrowserPool 指标 + 健康检查 ──
        try:
            pool = get_browser_pool()
            report["worker_idle"] = pool.idle_count
            report["worker_busy"] = pool.busy_count

            health = pool.get_worker_health()
            report["worker_alive"] = health["alive"]
            report["worker_dead"] = len(health["dead"])
            report["worker_stuck"] = len(health["stuck"])
            report["worker_crashed_total"] = health["crashed_total"]

            if health["dead"]:
                await self._handle_dead_workers(health)
            if health["stuck"]:
                await self._handle_stuck_workers(health)

        except Exception as e:
            report["worker_error"] = str(e)

        # ── 4. 消费 Worker 事件队列 ──
        try:
            await self._drain_events()
            report["events_success_total"] = self.success_count
            report["events_failure_total"] = self.failure_count
            report["events_cancelled_total"] = self.cancelled_count
        except Exception as e:
            report["events_error"] = str(e)

        # ── 5. 采集系统资源 ──
        try:
            system = await get_system_health()
            report["cpu_percent"] = system["cpu_percent"]
            report["memory_percent"] = system["memory_percent"]
        except Exception as e:
            report["system_error"] = str(e)

        # ── 6. 数据库健康检查 ──
        try:
            db_health = await self.db.ping_all()
            report["db_mysql"] = db_health["mysql"]
            report["db_redis"] = db_health["redis"]
            report["db_mongodb"] = db_health["mongodb"]
        except Exception as e:
            report["db_error"] = str(e)

        # ── 7. 输出报告 + WS 广播 ──
        self._log_report(report)
        await self._broadcast_status(report)

    async def _drain_events(self):
        """消费 Worker 事件队列，通过 WorkerEvent 合同校验后写入数据库并累计计数。"""
        drained = 0
        while (
            drained < self.config.max_events_per_cycle
            and not self.worker_event_queue.empty()
        ):
            try:
                raw = self.worker_event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            # 强类型校验 — 不符合合同的事件直接丢弃并告警
            try:
                event = WorkerEvent.model_validate(raw)
            except Exception:
                logger.warning(f"Monitor 收到非法事件格式: {raw}")
                drained += 1
                continue

            drained += 1

            if event.event_type == EventType.STARTED:
                await self._push_task_started(event)
            elif event.event_type == EventType.STAGE_CHANGE:
                await self._push_task_stage_change(event)
            elif event.event_type == EventType.SUCCESS:
                self.success_count += 1
                await self._push_task_success(event)
            elif event.event_type == EventType.FAILURE:
                self.failure_count += 1
                await self._write_failure_event(event)
            elif event.event_type == EventType.CANCELLED:
                self.cancelled_count += 1
                await self._write_failure_event(event)

        if drained > 0:
            logger.debug(f"Monitor 消费了 {drained} 个事件")

    async def _write_failure_event(self, event: WorkerEvent):
        """
        将失败/取消事件写入 task_failures 表。

        通过 TaskFailureService.write_batch_failure() 统一入口，
        不再直接写裸 SQL，消除双重写入维护负担。

        同时通过 WebSocket 向提交任务的管理员推送通知。
        """
        admin_id, task_id = self._extract_task_meta(event.task)
        parent_failure_id = 0
        try:
            data = json.loads(event.task)
            parent_failure_id = data.get("parent_failure_id", 0)
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            from services.task_failure_service import _get_failure_service
            # 从 failure_service 导入 classify_failure_layer
            from crawler.failure_service import FailureKind, classify_failure_layer
            # 用事件中的 kind 字符串构造 FailureKind，推导 failure_layer
            try:
                kind_enum = FailureKind(event.kind.value)
                # 这里没有异常对象，降级用 kind 推导
                layer = "storage" if kind_enum == FailureKind.STORAGE else (
                    "system" if kind_enum == FailureKind.BROWSER else "crawler"
                )
            except ValueError:
                layer = "crawler"

            svc = _get_failure_service()
            await svc.write_batch_failure(
                task_id=task_id,
                worker_id=event.worker_id,
                task_json=event.task,
                event_type=event.event_type.value,
                kind=event.kind.value,
                reason=event.reason,
                admin_id=admin_id,
                parent_failure_id=parent_failure_id,
                failure_layer=layer,
                snapshot=event.snapshot,
            )
        except Exception:
            logger.exception("写入失败事件到 MySQL 失败")

        try:
            from services.task_history_service import _get_history_service
            task_type = ""
            try:
                tdata = json.loads(event.task)
                task_type = tdata.get("type", "")
            except (json.JSONDecodeError, TypeError):
                pass
            if task_type not in ("movie_detail_crawl", "review_full_crawl"):
                elapsed_ms = None
                if event.task:
                    try:
                        tdata = json.loads(event.task)
                        created = tdata.get("created_at", 0)
                        if created:
                            elapsed_ms = int((event.timestamp - created) * 1000)
                    except Exception:
                        pass
                await _get_history_service().update_status(
                    task_id=task_id,
                    status="failed",
                    message=event.reason,
                    elapsed_ms=elapsed_ms,
                )
        except Exception:
            pass

        if self.ws_manager and admin_id > 0:
            try:
                await self.ws_manager.push(admin_id, {
                    "type": "task_failure",
                    "event_type": event.event_type.value,
                    "task": event.task,
                    "reason": event.reason,
                    "timestamp": event.timestamp,
                })
            except Exception:
                logger.exception(f"WebSocket 推送失败: admin_id={admin_id}")

    def _log_report(self, report: dict):
        """输出本轮监控报告。"""
        parts = []
        for key, value in report.items():
            parts.append(f"{key}={value}")
        logger.debug(f"Monitor 报告 | {' | '.join(parts)}")

    @staticmethod
    def _extract_task_meta(task_str: str) -> tuple:
        """
        从 task JSON 中提取 admin_id 和 task_id。

        输入：task JSON 字符串
        输出：(admin_id, task_id) — 失败时返回 (0, 0)
        副作用：无
        """
        try:
            data = json.loads(task_str)
            return data.get("admin_id", 0), data.get("id", 0)
        except (json.JSONDecodeError, TypeError):
            return 0, 0

    async def _push_task_started(self, event: WorkerEvent) -> None:
        """
        任务开始执行 → 更新 task_history 为 running。
        """
        _, task_id = self._extract_task_meta(event.task)
        if not task_id:
            return
        try:
            from services.task_history_service import _get_history_service
            await _get_history_service().update_status(task_id=task_id, status="running")
        except Exception:
            pass

    async def _push_task_stage_change(self, event: WorkerEvent) -> None:
        """
        Crawler 阶段变更 → 更新 task_history.message + WS 推送 admin。
        """
        admin_id, task_id = self._extract_task_meta(event.task)
        if not task_id:
            return

        stage = event.stage or ""
        try:
            from services.task_history_service import _get_history_service
            await _get_history_service().update_status(task_id=task_id, status="running", message=stage)
        except Exception:
            pass

        if self.ws_manager and admin_id:
            try:
                await self.ws_manager.push(admin_id, {
                    "type": "task_progress",
                    "task_id": task_id,
                    "stage": stage,
                    "timestamp": event.timestamp,
                })
            except Exception:
                pass

    async def _push_task_success(self, event: WorkerEvent) -> None:
        """
        任务执行成功 → WS 推送给提交者 + 更新 task_history。

        注意：SUCCESS_UPDATE_EXCLUDED_TYPES 是硬编码排除列表，
        movie_detail_crawl / review_full_crawl 成功后不写 task_history=done。
        新增任务类型需手动添加到此处，否则行为不一致。

        输入：WorkerEvent（SUCCESS 类型）
        副作用：通过 WS push 到 admin_id + UPDATE task_history
        """
        admin_id, task_id = self._extract_task_meta(event.task)

        task_type = ""
        try:
            data = json.loads(event.task)
            task_type = data.get("type", "")
        except (json.JSONDecodeError, TypeError):
            pass

        if task_type not in ("movie_detail_crawl", "review_full_crawl"):
            try:
                from services.task_history_service import _get_history_service
                elapsed_ms = None
                if event.task:
                    try:
                        tdata = json.loads(event.task)
                        created = tdata.get("created_at", 0)
                        if created:
                            elapsed_ms = int((event.timestamp - created) * 1000)
                    except Exception:
                        pass
                await _get_history_service().update_status(
                    task_id=task_id,
                    status="done",
                    message=f"已完成: {task_type}" if task_type else "已完成",
                    elapsed_ms=elapsed_ms,
                )
            except Exception:
                pass

        if not self.ws_manager:
            return

        if admin_id <= 0:
            return

        try:
            await self.ws_manager.push(admin_id, {
                "type": "task_success",
                "task_id": task_id,
                "worker_id": event.worker_id,
                "task": event.task,
                "timestamp": event.timestamp,
            })
        except Exception:
            logger.exception(f"task_success WS 推送失败: admin_id={admin_id}")

    async def _broadcast_status(self, report: dict) -> None:
        """
        每轮Monitor报告广播给全体管理员 — 前端实况面板数据源。

        白名单过滤：仅推送前端安全字段，排除含密码/内部详情的错误消息。

        输入：report — _run_cycle 中构建的完整监控 dict
        副作用：WS broadcast 到所有在线管理员
        """
        if not self.ws_manager:
            return

        safe_keys = {
            "queue_size", "queue_maxsize", "queue_saturation",
            "worker_idle", "worker_busy",
            "worker_alive", "worker_dead", "worker_stuck", "worker_crashed_total",
            "events_success_total", "events_failure_total", "events_cancelled_total",
            "cpu_percent", "memory_percent",
            "db_mysql", "db_redis", "db_mongodb",
            "puller_state", "puller_fetched", "puller_empty_polls",
            "puller_backpressure_count", "puller_backpressure_duration",
            "puller_error", "queue_error", "worker_error", "events_error", "system_error",
        }
        safe_report = {k: v for k, v in report.items() if k in safe_keys}

        try:
            await self.ws_manager.broadcast({
                "type": "system_status",
                "timestamp": time.time(),
                **safe_report,
            })
        except Exception:
            pass

    async def _handle_dead_workers(self, health: dict) -> None:
        """
        处理已死亡的 Worker：日志告警 + WebSocket 推送 + 自动重启。

        输入：
            health: BrowserPool.get_worker_health() 返回的 dict
        副作用：
            重启死 Worker
            通过 WS 向所有连接管理员广播告警
        """
        pool = get_browser_pool()
        for dead in health["dead"]:
            wid = dead["worker_id"]
            err = dead["error"]
            logger.error(
                f"⚠️ Worker-{wid} 已崩溃！错误: {err} | "
                f"存活: {health['alive']}/{health['expected']} | "
                f"忙碌: {health['busy_count']} 卡死: {len(health['stuck'])}"
            )

            dead_task = pool.get_current_task(wid)
            if dead_task:
                try:
                    task_data = json.loads(dead_task)
                    from services.task_history_service import _get_history_service
                    await _get_history_service().update_status(
                        task_id=task_data.get("id", 0),
                        status="failed",
                        message=f"Worker #{wid} 在执行中崩溃",
                    )
                except Exception:
                    pass

        if self.ws_manager:
            try:
                await self.ws_manager.broadcast({
                    "type": "worker_crash",
                    "dead": health["dead"],
                    "alive": health["alive"],
                    "expected": health["expected"],
                    "crashed_total": health["crashed_total"],
                    "action": "正在自动重启...",
                })
            except Exception:
                logger.exception("Worker 崩溃告警 WS 推送失败")

        restarted = await pool.restart_dead_workers()
        if restarted > 0 and self.ws_manager:
            try:
                await self.ws_manager.broadcast({
                    "type": "worker_restarted",
                    "restarted": restarted,
                    "crashed_total": health["crashed_total"] + restarted,
                })
            except Exception:
                pass

    async def _handle_stuck_workers(self, health: dict) -> None:
        """
        处理疑似卡死的 Worker：日志告警 + WebSocket 推送。

        注意：卡死 Worker 不做自动重启（asyncio.Task 仍在运行，
        强行取消可能丢失正在执行的任务数据）。

        输入：
            health: BrowserPool.get_worker_health() 返回的 dict
        副作用：
            通过 WS 向所有连接管理员广播告警
        """
        pool = get_browser_pool()
        for stuck in health["stuck"]:
            wid = stuck["worker_id"]
            elapsed = stuck["busy_seconds"]
            logger.warning(
                f"⏳ Worker-{wid} 疑似卡死: "
                f"已执行 {elapsed:.0f}s（阈值 {self.config.worker_timeout_alert}s） | "
                f"存活: {health['alive']}/{health['expected']}"
            )

        if self.ws_manager:
            try:
                await self.ws_manager.broadcast({
                    "type": "worker_stuck",
                    "stuck": health["stuck"],
                    "threshold_seconds": self.config.worker_timeout_alert,
                    "alive": health["alive"],
                    "expected": health["expected"],
                    "action": "需要人工介入（重启应用）",
                })
            except Exception:
                pass


# ==================== 模块级单例管理 ====================

_monitor_instance: Optional[Monitor] = None


async def init_monitor(
    task_queue: asyncio.Queue,
    worker_event_queue: asyncio.Queue,
    db_layer,
    config: Optional[MonitorConfig] = None,
    ws_manager=None,
) -> Monitor:
    """
    初始化 Monitor 单例。

    Args:
        task_queue: 任务队列。
        worker_event_queue: Worker 事件队列。
        db_layer: DatabaseLayerV2 实例。
        config: Monitor 调优参数。
        ws_manager: WebSocketManager 实例。

    Returns:
        Monitor 实例。
    """
    global _monitor_instance
    _monitor_instance = Monitor(
        task_queue=task_queue,
        worker_event_queue=worker_event_queue,
        db_layer=db_layer,
        config=config,
        ws_manager=ws_manager,
    )
    logger.info("Monitor 单例已初始化")
    return _monitor_instance


def get_monitor() -> Monitor:
    """获取 Monitor 单例，未初始化时抛出 RuntimeError。"""
    if _monitor_instance is None:
        raise RuntimeError("Monitor 未初始化，请先调用 init_monitor()")
    return _monitor_instance


async def start_monitor():
    """启动 Monitor。"""
    monitor = get_monitor()
    await monitor.run()


async def stop_monitor():
    """停止 Monitor。"""
    monitor = get_monitor()
    await monitor.stop()
