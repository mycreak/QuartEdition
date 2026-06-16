"""
AI 短评词云生成验证脚本

验证目标：读取 douban_id=21318488 的短评，调用 AI 生成词云总结。
对 AI 调用模块各环节错误有详尽报告输出。

用法：
    cd BackEnd
    python scripts/test_ai_comment_summary.py
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.mysql import init_mysql, close_mysql, execute_query
from db.mongodb import init_mongodb, close_mongodb, get_mongodb
from utils.ai_client import get_ai_client
from config.settings import settings

TEST_DOUBAN_ID = "21318488"
BORDER = "=" * 70


async def step1_lookup_movie() -> dict:
    """第一步：MySQL 查 douban_id → movie_id"""
    print(f"\n{BORDER}")
    print("STEP 1: MySQL 查找电影")
    print(BORDER)
    print(f"  douban_id = {TEST_DOUBAN_ID}")

    rows = await execute_query(
        "SELECT id, title, douban_id, poster_url FROM movies WHERE douban_id = %s LIMIT 1",
        (TEST_DOUBAN_ID,),
    )
    if not rows:
        raise RuntimeError(f"❌ 未找到 douban_id={TEST_DOUBAN_ID} 的电影，请先爬取")

    movie = rows[0]
    print(f"  ✅ 找到: movie_id={movie['id']}  title={movie['title']}")
    return movie


async def step2_read_comments(movie_id: int) -> list[str]:
    """第二步：MongoDB 读短评"""
    print(f"\n{BORDER}")
    print("STEP 2: MongoDB 读取短评")
    print(BORDER)
    print(f"  movie_id = {movie_id}")
    print(f"  集合: {settings.MONGO_DATABASE}.comments")

    db = get_mongodb()
    collection = db["comments"]

    total = await collection.count_documents({"movie_id": movie_id, "removed_by": None})
    print(f"  总短评数: {total}")

    cursor = collection.find(
        {"movie_id": movie_id, "removed_by": None},
        {"text": 1, "author": 1, "rating": 1, "useful_count": 1, "_id": 0},
    ).sort([("useful_count", -1)]).limit(100)

    comments = []
    async for doc in cursor:
        text = (doc.get("text") or "").strip()
        if text:
            comments.append(text)

    print(f"  有效短评数: {len(comments)} (过滤空文本后)")

    if len(comments) < 10:
        raise RuntimeError(
            f"❌ 短评不足 10 条 (仅 {len(comments)} 条)，AI 词云要求 ≥ 10"
        )

    print(f"  前 3 条预览:")
    for i, c in enumerate(comments[:3], 1):
        print(f"    [{i}] {c[:80]}...")

    return comments


async def step3_ai_wordcloud(comments: list[str]):
    """第三步：调用 AI 生成词云"""
    print(f"\n{BORDER}")
    print("STEP 3: AI 词云生成")
    print(BORDER)

    print(f"  输入短评数: {len(comments)}")
    print(f"  总字数: {sum(len(c) for c in comments)}")

    # ── 检查 AI 配置 ──
    provider = getattr(settings, 'AI_PROVIDER', 'deepseek') or 'deepseek'
    print(f"  AI 服务商: {provider}")

    if provider == "deepseek":
        key = settings.DEEPSEEK_API_KEY
        endpoint = settings.DEEPSEEK_ENDPOINT
    elif provider == "doubao":
        key = settings.DOUBAO_API_KEY
        endpoint = settings.DOUBAO_ENDPOINT
    else:
        key = ""
        endpoint = ""

    print(f"  API Endpoint: {endpoint}")
    print(f"  API Key 已配置: {'是' if key else '否'}")
    if not key:
        raise RuntimeError(
            f"❌ AI_PROVIDER={provider} 的 API Key 未配置，"
            f"请在 .env 中设置相应的 *_API_KEY"
        )

    # ── 调用 AI ──
    ai_client = get_ai_client()
    print(f"  AI 模型: {ai_client.model}")
    print(f"  超时: {ai_client.timeout}s / 最大重试: {ai_client.max_retries}")

    t_start = time.time()
    snapshot = None
    words = None
    error_detail = None

    try:
        words = await ai_client.generate_comment_wordcloud(comments)
        snapshot = getattr(ai_client, 'last_snapshot', None) or {}
    except Exception as e:
        error_detail = {
            "exception_type": type(e).__name__,
            "exception_msg": str(e),
            "snapshot": getattr(ai_client, 'last_snapshot', None) or {},
        }

    elapsed = time.time() - t_start

    # ── 结果输出 ──
    print(f"\n  耗时: {elapsed:.1f}s")

    if words:
        print(f"  ✅ 成功！生成 {len(words)} 个关键词")
        print(f"\n  📊 词云结果 (top 20):")
        print(f"  {'关键词':<20} {'权重':>6}")
        print(f"  {'-'*26}")
        for w in sorted(words, key=lambda x: x['weight'], reverse=True)[:20]:
            print(f"  {w['text']:<20} {w['weight']:>6}")
        print(f"\n  完整快照:")
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"  ❌ 失败")
        if snapshot:
            print(f"\n  📋 AI 调用快照:")
            print(json.dumps({
                "provider": snapshot.get("provider"),
                "model": snapshot.get("model"),
                "input_chars": snapshot.get("input_chars"),
                "attempts": snapshot.get("attempts"),
                "last_status": snapshot.get("last_status"),
                "last_error": snapshot.get("last_error"),
                "status": snapshot.get("status"),
            }, ensure_ascii=False, indent=2, default=str))

            if snapshot.get("output_preview"):
                preview = snapshot["output_preview"]
                print(f"\n  📄 最后一次响应预览 ({len(preview)} 字符):")
                print(f"  {preview[:800]}")
        if error_detail:
            print(f"\n  💥 额外错误信息:")
            print(json.dumps(error_detail, ensure_ascii=False, indent=2, default=str))


async def main():
    print(f"\n{'#'*70}")
    print(f"# AI 短评词云生成验证")
    print(f"# 目标: douban_id={TEST_DOUBAN_ID}")
    print(f"{'#'*70}")

    # ── 初始化 ──
    try:
        await init_mysql()
        print("\n✅ MySQL 已连接")
    except Exception as e:
        print(f"\n❌ MySQL 连接失败: {e}")
        return

    try:
        await init_mongodb()
        print("✅ MongoDB 已连接")
    except Exception as e:
        print(f"❌ MongoDB 连接失败: {e}")
        await close_mysql()
        return

    try:
        # Step 1 & 2
        movie = await step1_lookup_movie()
        comments = await step2_read_comments(movie["id"])

        # Step 3
        await step3_ai_wordcloud(comments)

    except RuntimeError as e:
        print(f"\n{BORDER}")
        print(f"❌ 验证失败")
        print(f"{BORDER}")
        print(f"  {e}")
        # Unwrap causes chain when available
        if e.__cause__:
            print(f"  caused by: {type(e.__cause__).__name__}: {e.__cause__}")
    except Exception as e:
        print(f"\n{BORDER}")
        print(f"💥 未预期的异常")
        print(f"{BORDER}")
        import traceback
        traceback.print_exc()
    finally:
        await close_mongodb()
        await close_mysql()
        print(f"\n✅ 资源已释放")


if __name__ == "__main__":
    asyncio.run(main())
