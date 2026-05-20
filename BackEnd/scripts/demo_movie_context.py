"""
demo_movie_context.py — 电影标签上下文聚合 Demo

用法:
    cd BackEnd
    python scripts/demo_movie_context.py [movie_id]

默认 movie_id=38。

已迁移为核心模块 services/movie_context.py，本脚本委托调用。
"""

import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import init_mysql, close_mysql
from services.movie_context import init_movie_context, get_movie_context


async def build_movie_context(movie_id: int):
    """
    委托调用 MovieContextService.build()，保持旧接口兼容。

    输入: movie_id
    输出: 标签上下文 dict（含 print 输出）
    """
    from db.database_v2 import DatabaseLayerV2

    db = DatabaseLayerV2()
    await db.initialize("mysql")
    init_movie_context(db)

    ctx = await get_movie_context().build(movie_id)

    if "error" in ctx:
        print(f"  ❌ {ctx['error']}")
        return ctx

    print(f"\n{'='*70}")
    print(f"  🎬 电影标签上下文聚合 — movie_id={ctx['movie_id']}")
    print(f"  📌 片名: {ctx['title']}")
    print(f"  🆔 豆瓣ID: {ctx['douban_id']}")
    print(f"{'='*70}")

    _DIM_CN = {"overall": "整体", "plot": "剧情", "visual": "画面", "narrative": "叙事", "pacing": "节奏"}

    for t in ctx["tags"]:
        dim = t["dimension"]
        if dim == "era":
            print(f"\n  📅 年代 | label={t['label']} | year={t['value']} | weight={t['weight']}")
        elif dim == "region":
            print(f"  🌍 地区 | {t['label']} | weight={t['weight']}")
        elif dim == "director":
            print(f"  🎬 导演 | {t['label']} | weight={t['weight']}")
        elif dim == "actor":
            print(f"  🎭 演员 | {t['label']} | weight={t['weight']}")
        elif dim == "genre":
            print(f"  🏷️  豆瓣分类 | {t['label']} | weight={t['weight']}")
        elif dim in _DIM_CN:
            cn = _DIM_CN[dim]
            print(f"  🎨 {cn:6s} | {t['label']:12s} | confidence={t['confidence']:.1f} | weight={t['weight']}")

    if ctx["ai_summary"]:
        print(f"\n  📄 AI 总结 (前150字):")
        print(f"     {ctx['ai_summary'][:150]}...")
    else:
        print(f"\n  📄 AI 总结: (无)")

    stats = ctx["stats"]
    print(f"\n{'='*70}")
    print(f"  📊 聚合统计")
    print(f"     total  tags: {stats['total_tags']}")
    print(f"     by dimension: {json.dumps(stats['by_dimension'], ensure_ascii=False)}")
    print(f"     by source:    {json.dumps(stats['by_source'], ensure_ascii=False)}")
    print(f"{'='*70}")

    print(f"\n  📦 完整 JSON:")
    print(json.dumps(ctx, ensure_ascii=False, indent=2))
    print()

    return ctx


async def main():
    movie_id = int(sys.argv[1]) if len(sys.argv) > 1 else 38

    await init_mysql()
    try:
        await build_movie_context(movie_id)
    finally:
        await close_mysql()


if __name__ == "__main__":
    asyncio.run(main())
