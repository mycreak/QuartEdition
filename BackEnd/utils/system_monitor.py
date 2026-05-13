"""
utils/system_monitor.py

系统资源监控工具。
封装 psutil 的同步调用为异步接口，避免阻塞事件循环。
"""

import asyncio

import psutil


async def get_system_health() -> dict:
    """
    异步采集系统资源状态。

    psutil 的 cpu_percent 和 virtual_memory 是同步调用，
    通过 asyncio.to_thread 丢到线程池执行，不阻塞事件循环。

    Returns:
        {
            "cpu_percent": float,       # CPU 使用率（0~100）
            "memory_percent": float,    # 内存使用率（0~100）
            "memory_used_mb": float,    # 已用内存（MB）
            "memory_total_mb": float,   # 总内存（MB）
        }
    """
    cpu, mem = await asyncio.gather(
        asyncio.to_thread(psutil.cpu_percent, 1),
        asyncio.to_thread(psutil.virtual_memory),
    )

    return {
        "cpu_percent": cpu,
        "memory_percent": mem.percent,
        "memory_used_mb": round(mem.used / 1024 / 1024, 1),
        "memory_total_mb": round(mem.total / 1024 / 1024, 1),
    }
