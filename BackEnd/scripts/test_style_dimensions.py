"""
新 Prompt 测试脚本 — 5 维度风格分析（只读不写，单次调用）

用法：
    1. 确认 .env 中 DEEPSEEK_API_KEY 已配置
    2. 确认 MongoDB 中有 movie_id 对应的长评数据
    3. python scripts/test_style_dimensions.py [movie_id]

输出：
    - AI 返回的 full_summary
    - 5 个维度的 label + confidence
    - 过滤后应入库 movie_style_tag 的标签列表
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from pymongo import MongoClient
from utils.ai_client import get_ai_client
from config.settings import settings

DIM_LABELS = {
    "overall": "整体风格",
    "plot": "剧情风格",
    "visual": "画面风格",
    "narrative": "叙事风格",
    "pacing": "节奏风格",
}


async def main(movie_id: int = 38):
    print("=" * 72)
    print("🧪 5 维度风格分析 Prompt 测试")
    print(f"   movie_id={movie_id}（只读，不写库，单次 API 调用）")
    print("=" * 72)

    # ── 1. 读取数据 ──
    print("\n📥 1. 从 MongoDB 读取长评...")
    if settings.MONGO_USER:
        client = MongoClient(
            f"mongodb://{settings.MONGO_USER}:{settings.MONGO_PASSWORD}@"
            f"{settings.MONGO_HOST}:{settings.MONGO_PORT}/",
            authSource="admin",
        )
    else:
        client = MongoClient(
            f"mongodb://{settings.MONGO_HOST}:{settings.MONGO_PORT}/"
        )
    db = client[settings.MONGO_DATABASE]
    collection = db["reviews"]

    reviews = list(
        collection.find(
            {"movie_id": movie_id, "is_published": True},
            {"text": 1, "useful_count": 1, "_id": 0},
        )
        .sort([("useful_count", -1)])
        .limit(20)
    )

    if not reviews:
        print(f"❌ movie_id={movie_id} 无长评数据")
        client.close()
        return

    for r in reviews:
        r["content"] = r.pop("text", "")
    print(f"✅ 读取 {len(reviews)} 条长评")

    # ── 2. 调用 AI ──
    print("\n🤖 2. 调用 AI 生成 5 维度分析（请等待 5-15 秒）...")
    ai_client = get_ai_client()
    result = await ai_client.generate_review_summary(reviews, max_chars_per_review=800)
    client.close()

    if not result:
        print("❌ AI 返回失败，请查看控制台错误日志")
        return

    # ── 3. 输出结果 ──
    print("\n" + "=" * 72)
    print("📄 综合总结")
    print("=" * 72)
    print(result.get("full_summary", "(无)"))

    print("\n" + "=" * 72)
    print("🏷️ Tags（兼容前端）")
    print("=" * 72)
    for i, t in enumerate(result.get("tags", []), 1):
        print(f"  {i}. {t}")

    dims = result.get("style_dimensions", {})
    if dims:
        print("\n" + "=" * 72)
        print("🎨 5 维度风格分析")
        print("=" * 72)
        filtered = []
        for key in ("overall", "plot", "visual", "narrative", "pacing"):
            d = dims.get(key, {})
            label = d.get("label", "?")
            conf = d.get("confidence", 0)
            cn = DIM_LABELS.get(key, key)
            status = (
                "❌ 过滤(无显著特征)" if label == "无显著特征"
                else "⚠️ 过滤(可信度<0.5)" if conf < 0.5
                else "✅ 入库"
            )
            print(f"  {cn:6s} | {label:14s} | confidence={conf:.1f} | {status}")
            if label != "无显著特征" and conf >= 0.5:
                filtered.append({"dimension": key, "label": label, "confidence": conf})

        print(f"\n📊 应入库 movie_style_tag: {len(filtered)} 条")
        for f in filtered:
            print(f"  dimension={f['dimension']:10s} name={f['label']} confidence={f['confidence']}")

    # ── 4. 格式校验 ──
    print("\n" + "=" * 72)
    print("🔍 格式校验")
    print("=" * 72)
    errors = []
    if not result.get("full_summary"):
        errors.append("缺少 full_summary")
    if not result.get("tags"):
        errors.append("缺少 tags")
    if not isinstance(dims, dict):
        errors.append("缺少 style_dimensions 或格式错误")
    else:
        for key in ("overall", "plot", "visual", "narrative", "pacing"):
            d = dims.get(key)
            if not isinstance(d, dict) or "label" not in d or "confidence" not in d:
                errors.append(f"style_dimensions.{key} 格式错误")

    if errors:
        print("❌ 错误：")
        for e in errors:
            print(f"  - {e}")
    else:
        print("✅ 格式完全正确")
        print(f"\n⚠️ 注意：本次测试仅验证 Prompt 效果，未写入任何数据库。")
        print(f"   确认结果满意后，执行完整的 AI 总结任务即可入库。")

    print()


if __name__ == "__main__":
    mid = int(sys.argv[1]) if len(sys.argv) > 1 else 38
    asyncio.run(main(mid))
