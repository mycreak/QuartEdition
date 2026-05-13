#!/usr/bin/env python3
"""
统计项目代码行数（前端+后端）
排除依赖目录：.venv, .pytest_cache, node_modules, .git
"""

import os
from pathlib import Path
from typing import Dict, List, Tuple
from pygount import SourceAnalysis
from pygount.linecount import LineCounter


def count_directory(path: Path, exclude_dirs: List[str]) -> Dict[str, Dict[str, int]]:
    """统计指定目录下的代码行数"""
    result: Dict[str, Dict[str, int]] = {}
    
    for root, dirs, files in os.walk(path):
        # 排除目录
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for filename in files:
            file_path = Path(root) / filename
            try:
                analysis = SourceAnalysis.from_file(file_path, None)
                counter = LineCounter(analysis.language)
                counter.count(analysis.source_code)
                
                if analysis.language not in result:
                    result[analysis.language] = {
                        "files": 0,
                        "code": 0,
                        "comment": 0,
                        "empty": 0
                    }
                
                result[analysis.language]["files"] += 1
                result[analysis.language]["code"] += counter.code_count
                result[analysis.language]["comment"] += counter.comment_count
                result[analysis.language]["empty"] += counter.empty_count
                
            except Exception:
                continue  # 跳过无法解析的文件
    
    return result


def print_summary(title: str, stats: Dict[str, Dict[str, int]]):
    """打印统计结果"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    
    total_files = 0
    total_code = 0
    total_comment = 0
    total_empty = 0
    
    for lang, data in sorted(stats.items(), key=lambda x: x[1]["code"], reverse=True):
        print(f"\n{lang:20s}:")
        print(f"  文件数: {data['files']:6d}")
        print(f"  代码行: {data['code']:6d}")
        print(f"  注释行: {data['comment']:6d}")
        print(f"  空行  : {data['empty']:6d}")
        print(f"  总计  : {data['code'] + data['comment'] + data['empty']:6d}")
        
        total_files += data["files"]
        total_code += data["code"]
        total_comment += data["comment"]
        total_empty += data["empty"]
    
    print(f"\n{'-'*60}")
    print(f"  总计:")
    print(f"    文件数: {total_files:6d}")
    print(f"    代码行: {total_code:6d}")
    print(f"    注释行: {total_comment:6d}")
    print(f"    空行  : {total_empty:6d}")
    print(f"    总计  : {total_code + total_comment + total_empty:6d}")
    print(f"{'='*60}")


def main():
    project_root = Path(__file__).parent
    exclude_dirs = [".venv", ".pytest_cache", "node_modules", ".git", "__pycache__", ".idea", ".vscode"]
    
    # 后端统计
    backend_path = project_root / "BackEnd"
    if backend_path.exists():
        backend_stats = count_directory(backend_path, exclude_dirs)
        print_summary("后端 (BackEnd)", backend_stats)
    
    # 前端统计
    frontend_path = project_root / "FrontEnd"
    if frontend_path.exists():
        frontend_stats = count_directory(frontend_path, exclude_dirs)
        print_summary("前端 (FrontEnd)", frontend_stats)
    
    # 全项目统计
    all_stats = count_directory(project_root, exclude_dirs)
    print_summary("全项目 (总计)", all_stats)


if __name__ == "__main__":
    main()
