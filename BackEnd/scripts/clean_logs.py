"""
scripts/clean_logs.py

日志清理工具 — 手动运行，按保留天数清理过期的日志归档文件。

用法：
    python scripts/clean_logs.py                   # 保留 7 天
    python scripts/clean_logs.py --days 30         # 保留 30 天
    python scripts/clean_logs.py --dry-run         # 只看不删
    python scripts/clean_logs.py --all             # 全删
    python scripts/clean_logs.py --all --dry-run   # 只看不删

行为：
    - 保留 logs/ 目录下各分类的最新 .log 文件（当前活跃日志）
    - 删除超过保留天数的轮转归档 .log.YYYY-MM-DD 文件
    - 可选清空当前 .log（追加 Truncate 选项），默认不清
"""

import argparse
import os
import sys
import re
from datetime import datetime, timezone, timedelta

# 东八区时区常量
CST = timezone(timedelta(hours=8))
from pathlib import Path


# 日志目录（相对 BackEnd/）
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# 轮转归档模式：access.log.2026-05-08
_LOG_ARCHIVE_PATTERN = re.compile(r"\.(\d{4}-\d{2}-\d{2})$")


def _parse_date_from_name(name: str) -> datetime | None:
    """从文件名末尾提取日期，如 access.log.2026-05-08 → datetime(2026,5,8)。"""
    m = _LOG_ARCHIVE_PATTERN.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=CST)
    except ValueError:
        return None


def clean(days: int, dry_run: bool, delete_all: bool = False):
    """执行清理。"""
    if not LOG_DIR.is_dir():
        print(f"[SKIP] 日志目录不存在: {LOG_DIR}")
        return

    if delete_all:
        return _clean_all(dry_run)

    now = datetime.now(CST)
    cutoff = now - timedelta(days=days)

    # 收集所有日志文件信息
    archives = []       # 待删除的归档
    active_files = []   # 当前活跃 .log（保留）

    for f in sorted(LOG_DIR.iterdir()):
        if not f.is_file():
            continue
        if f.suffix == ".log":
            active_files.append(f)
        else:
            # 形如 access.log.2026-05-08
            file_date = _parse_date_from_name(f.name)
            if file_date is not None:
                archives.append((file_date, f))

    # 统计
    total_archives = len(archives)
    to_delete = []
    safe = []
    for file_date, f in archives:
        if file_date < cutoff:
            to_delete.append(f)
        else:
            safe.append(f)

    # 打印报告
    print(f"日志目录: {LOG_DIR}")
    print(f"保留天数: {days} 天")
    print(f"截止日期: {cutoff.strftime('%Y-%m-%d')}")
    print(f"当前活跃: {len(active_files)} 个")
    print(f"归档总计: {total_archives} 个")
    print(f"  → 待删除: {len(to_delete)} 个（超过 {days} 天）")
    print(f"  → 保留:   {len(safe)} 个（{days} 天内）")
    print()

    if to_delete:
        print("待删除文件:")
        for f in sorted(to_delete):
            size_kb = f.stat().st_size / 1024
            print(f"  [{size_kb:>8.1f} KB] {f.name}")
        print()

    if dry_run:
        print("[DRY-RUN] 预览模式，未执行任何删除。去掉 --dry-run 可实际删除。")
        return

    # 实际删除
    deleted_count = 0
    deleted_bytes = 0
    for f in to_delete:
        size = f.stat().st_size
        f.unlink()
        deleted_count += 1
        deleted_bytes += size
        print(f"  [DEL] {f.name} ({size / 1024:.1f} KB)")

    if deleted_count > 0:
        print(f"\n已删除 {deleted_count} 个归档文件，释放 {deleted_bytes / 1024:.1f} KB")
    else:
        print("无需清理，所有归档均在保留期内。")

    # 可选：显示当前活跃文件大小
    print()
    print("当前活跃日志文件:")
    for f in sorted(active_files):
        size_kb = f.stat().st_size / 1024
        print(f"  [{size_kb:>8.1f} KB] {f.name}")


def _clean_all(dry_run: bool = False):
    """删除 logs/ 目录下所有文件（包括当前活跃日志）。"""
    files = [f for f in LOG_DIR.iterdir() if f.is_file()]
    total_size = sum(f.stat().st_size for f in files)

    print(f"日志目录: {LOG_DIR}")
    print(f"文件总数: {len(files)} 个")
    print(f"总大小:   {total_size / 1024:.1f} KB")
    print()

    if not files:
        print("目录已空，无需清理。")
        return

    print("将删除以下文件:")
    for f in sorted(files):
        size_kb = f.stat().st_size / 1024
        print(f"  [{size_kb:>8.1f} KB] {f.name}")
    print()

    if dry_run:
        print("[DRY-RUN] 预览模式，未执行任何删除。去掉 --all 可实际删除。")
        return

    deleted = 0
    for f in files:
        f.unlink()
        deleted += 1
    print(f"已删除 {deleted} 个文件，释放 {total_size / 1024:.1f} KB")


def main():
    parser = argparse.ArgumentParser(
        description="清理 logs/ 目录下过期的日志归档文件",
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="保留天数，默认 7 天",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="预览模式，不实际删除",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="删除全部日志（包括当前活跃文件），默认只删过期归档",
    )
    args = parser.parse_args()

    if args.all:
        clean(days=0, dry_run=args.dry_run, delete_all=True)
    else:
        if args.days < 1:
            print("错误: --days 必须 >= 1")
            sys.exit(1)
        clean(days=args.days, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
