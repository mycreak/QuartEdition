"""
services/style_tag_service.py

电影风格标签相似度检测与合并管理。

职责：
    1. check_similarity — 新标签入库后，与同维度已有标签做 AI 相似度对比
    2. list_pending     — 管理员查看待审核标签列表（review_status=2）
    3. confirm_merge    — 管理员确认合并（事务：迁移关联 → 删除旧关联 → 改状态）
    4. reject_merge     — 管理员拒绝合并（改状态为 1）

状态机：
    0 = 刚生成，未检测
    1 = 已检测，相似度<82% 无需合并，或管理员已确认无需合并
    2 = 已检测，相似度≥82% 待管理员确认
    3 = 管理员确认已合并

依赖：
    DatabaseLayerV2 — 注入
    ai_client       — BaseAIClient 单例，做标签语义相似度判断
"""

import logging
from typing import Optional, List, Dict, Any

from db.database_v2 import DatabaseLayerV2
from utils.errors import ServiceError, NotFoundError

logger = logging.getLogger(__name__)

# 判定合并的相似度阈值
_SIMILARITY_THRESHOLD = 82.0


class TagAlreadyProcessedError(ServiceError):
    """标签已被处理过（非 status=0），不可重复检测。"""
    def __init__(self, tag_id: int):
        super().__init__(
            message=f"标签 id={tag_id} 已处理过，不可重复检测",
            code="TAG_ALREADY_PROCESSED",
            status_code=409,
        )


class TagNotPendingError(ServiceError):
    """标签不是待审核状态（非 status=2），不可审核。"""
    def __init__(self, tag_id: int):
        super().__init__(
            message=f"标签 id={tag_id} 不是待审核状态",
            code="TAG_NOT_PENDING",
            status_code=409,
        )


class StyleTagService:
    """
    风格标签相似度检测与合并管理。

    输入：DatabaseLayerV2 实例（依赖注入）
    副作用：读写 movie_style_tag / movie_style 表，调用 AI
    """

    def __init__(self, db: DatabaseLayerV2):
        self.db = db

    # ═══════════════════════════════════════
    # 相似度检测
    # ═══════════════════════════════════════

    async def check_similarity(self, tag_id: int, dimension: str) -> Dict[str, Any]:
        """
        对单个新标签做同维度相似度检测（异步触发，不阻塞调用方）。

        输入：
            tag_id:  movie_style_tag.id
            dimension: 标签维度（overall/plot/visual/narrative/pacing）
        输出：
            {"status": "skipped" | "done", "review_status": int, "merged_to": int|None, "similarity": float|None}
        异常：
            TagAlreadyProcessedError — 标签非 status=0
        """
        raw = self.db.raw_mysql()

        # ① 校验标签存在且为 status=0
        tag_rows = await raw.execute_query(
            "SELECT id, name, review_status FROM movie_style_tag WHERE id=%s AND dimension=%s",
            (tag_id, dimension),
        )
        if not tag_rows:
            raise NotFoundError("风格标签", tag_id)
        tag = tag_rows[0]
        if tag['review_status'] != 0:
            raise TagAlreadyProcessedError(tag_id)

        tag_name = tag['name']

        # ② 找新标签关联的一部电影名（给 AI 做上下文）
        sample_movie = await raw.execute_query(
            "SELECT m.title FROM movies m "
            "JOIN movie_style ms ON m.id=ms.movie_id "
            "WHERE ms.tag_id=%s LIMIT 1",
            (tag_id,),
        )
        movie_a = sample_movie[0]['title'] if sample_movie else ""

        # ③ 查同维度已有标签（只和已确认/未检测的比）
        existing_rows = await raw.execute_query(
            "SELECT id, name FROM movie_style_tag "
            "WHERE dimension=%s AND id!=%s AND review_status IN (0, 1)",
            (dimension, tag_id),
        )

        if not existing_rows:
            # 同维度无其他标签 → 直接标记已确认
            await raw.execute_update(
                "UPDATE movie_style_tag SET review_status=1 WHERE id=%s",
                (tag_id,),
            )
            logger.info(
                f"[风格标签] tag_id={tag_id} dimension={dimension} "
                f"同维度无已有标签，自动标记 status=1"
            )
            return {"status": "done", "review_status": 1, "merged_to": None, "similarity": None}

        # ④ 遍历已有标签，AI 对比相似度
        from utils.ai_client import get_ai_client
        ai_client = get_ai_client()

        best_match_id = None
        best_score = 0.0

        for existing in existing_rows:
            # 找已有标签关联的电影名
            existing_movie = await raw.execute_query(
                "SELECT m.title FROM movies m "
                "JOIN movie_style ms ON m.id=ms.movie_id "
                "WHERE ms.tag_id=%s LIMIT 1",
                (existing['id'],),
            )
            movie_b = existing_movie[0]['title'] if existing_movie else ""

            score = await ai_client.compare_style_tags(
                tag_a=tag_name,
                tag_b=existing['name'],
                dimension=dimension,
                movie_a=movie_a,
                movie_b=movie_b,
            )
            if score is None:
                logger.warning(
                    f"[风格标签] AI 相似度检测失败: "
                    f"tag_a='{tag_name}' tag_b='{existing['name']}' dimension={dimension}"
                )
                continue

            if score > best_score:
                best_score = score
                best_match_id = existing['id']

        # ⑤ 根据最高分更新状态
        if best_score >= _SIMILARITY_THRESHOLD and best_match_id:
            await raw.execute_update(
                "UPDATE movie_style_tag "
                "SET review_status=2, merged_to_tag_id=%s "
                "WHERE id=%s",
                (best_match_id, tag_id),
            )
            logger.info(
                f"[风格标签] tag_id={tag_id} '{tag_name}' → status=2 "
                f"(相似 {best_score:.1f}% → 已有标签 id={best_match_id})"
            )
            return {
                "status": "done",
                "review_status": 2,
                "merged_to": best_match_id,
                "similarity": round(best_score, 1),
            }
        else:
            await raw.execute_update(
                "UPDATE movie_style_tag SET review_status=1 WHERE id=%s",
                (tag_id,),
            )
            logger.info(
                f"[风格标签] tag_id={tag_id} '{tag_name}' → status=1 "
                f"(最高相似度 {best_score:.1f}% < {_SIMILARITY_THRESHOLD}%，无需合并)"
            )
            return {
                "status": "done",
                "review_status": 1,
                "merged_to": None,
                "similarity": round(best_score, 1) if best_score > 0 else None,
            }

    # ═══════════════════════════════════════
    # 待审核列表
    # ═══════════════════════════════════════

    async def list_pending(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        查询待审核标签列表（review_status=2），带合并目标标签名和示例电影。

        输入：page, page_size
        输出：(items, total)
        """
        raw = self.db.raw_mysql()

        count_rows = await raw.execute_query(
            "SELECT COUNT(*) AS cnt FROM movie_style_tag WHERE review_status=2"
        )
        total = count_rows[0]['cnt'] if count_rows else 0

        offset = (page - 1) * page_size
        rows = await raw.execute_query(
            "SELECT t.*, mt.name AS merged_to_name "
            "FROM movie_style_tag t "
            "LEFT JOIN movie_style_tag mt ON t.merged_to_tag_id = mt.id "
            "WHERE t.review_status=2 "
            "ORDER BY t.id DESC "
            "LIMIT %s OFFSET %s",
            (page_size, offset),
        )

        items = []
        for r in rows:
            # 找新标签关联的电影名
            sample_movies = await raw.execute_query(
                "SELECT m.title FROM movies m "
                "JOIN movie_style ms ON m.id=ms.movie_id "
                "WHERE ms.tag_id=%s LIMIT 1",
                (r['id'],),
            )
            sample_movie = sample_movies[0]['title'] if sample_movies else ""

            # 找合并目标标签关联的电影名
            merged_movie = ""
            if r.get('merged_to_tag_id'):
                merged_movies = await raw.execute_query(
                    "SELECT m.title FROM movies m "
                    "JOIN movie_style ms ON m.id=ms.movie_id "
                    "WHERE ms.tag_id=%s LIMIT 1",
                    (r['merged_to_tag_id'],),
                )
                merged_movie = merged_movies[0]['title'] if merged_movies else ""

            items.append({
                "id": r['id'],
                "name": r['name'],
                "dimension": r['dimension'],
                "review_status": r['review_status'],
                "merged_to_tag_id": r.get('merged_to_tag_id', 0),
                "merged_to_tag_name": r.get('merged_to_name', ''),
                "sample_movie": sample_movie,
                "merged_sample_movie": merged_movie,
            })

        return items, total

    # ═══════════════════════════════════════
    # 管理员审核
    # ═══════════════════════════════════════

    async def confirm_merge(self, tag_id: int, admin_id: int) -> Dict[str, Any]:
        """
        管理员确认合并 — 事务执行三步操作。

        事务步骤：
            ① 迁移 movie_style 关联到目标标签（ON DUPLICATE KEY 保留最高置信度）
            ② 删除被合并标签的旧关联
            ③ 更新标签状态 status=3

        输入：tag_id（待合并的标签）, admin_id（操作的管理员）
        输出：{"success": True, "merged_count": int}
        异常：TagNotPendingError — 标签不是 status=2
        """
        raw = self.db.raw_mysql()

        # 校验状态
        tag_rows = await raw.execute_query(
            "SELECT id, name, dimension, merged_to_tag_id, review_status "
            "FROM movie_style_tag WHERE id=%s",
            (tag_id,),
        )
        if not tag_rows:
            raise NotFoundError("风格标签", tag_id)
        tag = tag_rows[0]
        if tag['review_status'] != 2:
            raise TagNotPendingError(tag_id)

        target_tag_id = tag['merged_to_tag_id']
        if not target_tag_id:
            raise ServiceError(
                message=f"标签 id={tag_id} 没有合并目标",
                code="NO_MERGE_TARGET",
                status_code=400,
            )

        # 事务执行
        async with self.db.transaction() as tx:
            # ① 迁移关联（ON DUPLICATE KEY 保留最高置信度）
            await tx.raw_mysql().execute_update(
                "INSERT INTO movie_style (movie_id, tag_id, confidence) "
                "SELECT ms.movie_id, %s, ms.confidence "
                "FROM movie_style ms "
                "WHERE ms.tag_id=%s "
                "ON DUPLICATE KEY UPDATE "
                "confidence = GREATEST(movie_style.confidence, VALUES(confidence))",
                (target_tag_id, tag_id),
            )

            # ② 删除被合并标签的旧关联
            await tx.raw_mysql().execute_update(
                "DELETE FROM movie_style WHERE tag_id=%s",
                (tag_id,),
            )

            # ③ 更新标签状态
            await tx.raw_mysql().execute_update(
                "UPDATE movie_style_tag SET review_status=3 WHERE id=%s",
                (tag_id,),
            )

        # 查迁移数量
        count_rows = await raw.execute_query(
            "SELECT COUNT(*) AS cnt FROM movie_style WHERE tag_id=%s",
            (target_tag_id,),
        )
        merged_count = count_rows[0]['cnt'] if count_rows else 0

        logger.info(
            f"[风格标签] 管理员确认合并: tag_id={tag_id} '{tag['name']}' "
            f"→ target_tag_id={target_tag_id} admin_id={admin_id} "
            f"migrated={merged_count}"
        )
        return {"success": True, "merged_count": merged_count}

    async def reject_merge(self, tag_id: int, admin_id: int) -> Dict[str, Any]:
        """
        管理员拒绝合并 — 将标签标记为已确认无需合并（status=1）。

        输入：tag_id, admin_id
        输出：{"success": True}
        异常：TagNotPendingError — 标签不是 status=2
        """
        raw = self.db.raw_mysql()

        tag_rows = await raw.execute_query(
            "SELECT id, name, review_status FROM movie_style_tag WHERE id=%s",
            (tag_id,),
        )
        if not tag_rows:
            raise NotFoundError("风格标签", tag_id)
        tag = tag_rows[0]
        if tag['review_status'] != 2:
            raise TagNotPendingError(tag_id)

        await raw.execute_update(
            "UPDATE movie_style_tag SET review_status=1, merged_to_tag_id=0 WHERE id=%s",
            (tag_id,),
        )

        logger.info(
            f"[风格标签] 管理员拒绝合并: tag_id={tag_id} '{tag['name']}' "
            f"→ status=1 admin_id={admin_id}"
        )
        return {"success": True}


# ═══════════════════════════════════════
# 模块级单例
# ═══════════════════════════════════════

_style_tag_service: Optional[StyleTagService] = None


def init_style_tag_service(db: DatabaseLayerV2) -> StyleTagService:
    """初始化 StyleTagService 单例。"""
    global _style_tag_service
    _style_tag_service = StyleTagService(db)
    logger.info("StyleTagService 已初始化")
    return _style_tag_service


def _get_style_tag_service() -> StyleTagService:
    """获取 StyleTagService 单例，未初始化时抛 RuntimeError。"""
    if _style_tag_service is None:
        raise RuntimeError("StyleTagService 未初始化，请先调用 init_style_tag_service()")
    return _style_tag_service
