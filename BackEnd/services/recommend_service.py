"""
services/recommend_service.py

推荐引擎 — 基于用户标签画像 + 变异系数(CV)自适应内容推荐。

算法:
    ① 用户标签画像 → 计算各维度变异系数 CV
    ② CV 高的维度 → 精准匹配用户高分标签
    ③ CV 低的维度 → 探索模式，随机加权
    ④ 排序截断 top_n → 补全电影信息 → 返回

依赖:
    UserActionService    — 拿衰减版用户画像
    MovieContextService  — 拿单部电影标签（context）
    config_score_weight  — CV阈值 + 各维度权重

冷启动:
    新用户无 user_tag_score → 全部探索模式 → 返回热门电影兜底
"""

import logging
import random
import statistics
from typing import Any, Dict, List, Optional

from db.database_v2 import DatabaseLayerV2
from services.movie_context import decade_label
from services.movie_context import _DEFAULT_DIM_WEIGHTS as _DIM_WEIGHTS_DEFAULT
from services.user_action_service import get_user_action_service

logger = logging.getLogger(__name__)

# 参与推荐的所有维度
_ALL_DIMS = ("era", "region", "director", "actor", "genre", "overall", "plot", "visual", "narrative", "pacing")

# 豆瓣维度（无 confidence 概念）
_DOUBAN_DIMS = frozenset({"era", "region", "director", "actor", "genre"})

# 候选池上限（性能保护）
_MAX_CANDIDATES = 200

# CV 计算下限 — μ 太小时 CV 无意义，强制置 0
_MIN_MU_FOR_CV = 0.01

# 冷启动热门兜底数量
_COLD_START_LIMIT = 50


class RecommendService:
    """
    推荐引擎。

    输入: DatabaseLayerV2 实例（依赖注入）
    输出: recommend(user_id, top_n) → List[dict]
    """

    def __init__(self, db: DatabaseLayerV2):
        self.db = db
        self._cv_threshold: Optional[float] = None
        self._config_loaded = False

    async def _ensure_config(self) -> None:
        if self._config_loaded:
            return
        try:
            raw = self.db.raw_mysql()
            rows = await raw.execute_query(
                "SELECT config_key, config_value FROM config_score_weight "
                "WHERE config_key LIKE 'dim.%' OR config_key='recommend.cv_threshold'"
            )
            if rows:
                for r in rows:
                    key = r["config_key"]
                    if key == "recommend.cv_threshold":
                        self._cv_threshold = float(r["config_value"])
        except Exception:
            logger.warning("[Recommend] 配置加载失败，使用默认值", exc_info=True)
        if self._cv_threshold is None:
            self._cv_threshold = 0.5
        self._config_loaded = True

    def _dim_weight(self, dimension: str) -> float:
        return _DIM_WEIGHTS_DEFAULT.get(dimension, 0.5)

    # ═══════════════════════════════════════════════════════════
    # 公开方法
    # ═══════════════════════════════════════════════════════════

    async def recommend(self, user_id: int, top_n: int = 10) -> List[Dict[str, Any]]:
        """
        输入: user_id, top_n
        输出: [{
            movie_id, douban_id, title, poster_url, release_year,
            score, rating
        }, ...]
        """
        await self._ensure_config()

        # ── ① 拿用户画像（衰减版） ──
        profile_svc = get_user_action_service()
        profile = await profile_svc.get_user_tag_profile(user_id, decayed=True)

        # ── 冷启动 ──
        if not profile.tags:
            return await self._cold_start(top_n)

        # ── ② 计算各维度 CV ──
        cv_map = self._calc_cv(profile.tags)

        # ── ③ 构建用户-标签分值查找表 ──
        user_score_map: Dict[str, Dict[str, float]] = {d: {} for d in _ALL_DIMS}
        for t in profile.tags:
            user_score_map.setdefault(t.dimension, {})[t.label] = t.score

        # ── ④ 获取候选池 ──
        candidate_ids = await self._get_candidates(user_id, _MAX_CANDIDATES)
        if not candidate_ids:
            return []

        # ── ⑤ 批量加载候选电影的标签数据 ──
        contexts = await self._batch_build_contexts(candidate_ids)

        # ── ⑥ 打分 ──
        scored = []
        for ctx in contexts:
            movie_id = ctx["movie_id"]
            s = self._score_movie(ctx, cv_map, user_score_map)
            scored.append((s, ctx))

        # ── ⑦ 排序 → top_n ──
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_n]

        # ── ⑧ 补全评分 ──
        enriched = await self._enrich_with_ratings([item[1] for item in top])

        # ── ⑨ 组装响应 ──
        result = []
        for ctx in enriched:
            result.append({
                "movie_id": ctx["movie_id"],
                "douban_id": ctx["douban_id"],
                "title": ctx["title"],
                "poster_url": ctx.get("poster_url"),
                "release_year": ctx.get("release_year"),
                "score": round(ctx.get("_score", 0), 4),
                "rating": ctx.get("rating"),
            })
        return result

    # ═══════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════

    def _calc_cv(self, tag_items) -> Dict[str, float]:
        """
        输入: TagItem 列表
        输出: {dimension: cv}

        每个维度: 收集该维度所有标签的 score，计算 μ 和 σ
        0 或 1 个标签 → CV=0
        μ 太小（<0.01）→ CV=0
        """
        groups: Dict[str, List[float]] = {d: [] for d in _ALL_DIMS}
        for t in tag_items:
            groups.setdefault(t.dimension, []).append(float(t.score))

        cv_map: Dict[str, float] = {}
        for dim, scores in groups.items():
            n = len(scores)
            if n <= 1:
                cv_map[dim] = 0.0
                continue
            mu = sum(scores) / n
            if mu < _MIN_MU_FOR_CV:
                cv_map[dim] = 0.0
                continue
            sigma = statistics.stdev(scores)
            cv_map[dim] = sigma / mu

        logger.debug(
            "[Recommend] user CV: %s",
            {d: round(v, 3) for d, v in sorted(cv_map.items(), key=lambda x: -x[1])[:5]},
        )
        return cv_map

    def _score_movie(
        self,
        ctx: Dict[str, Any],
        cv_map: Dict[str, float],
        user_score_map: Dict[str, Dict[str, float]],
    ) -> float:
        """
        输入: 电影标签上下文, CV map, 用户分数查找表
        输出: 匹配分

        精准模式 (CV > threshold): 匹配分 = Σ user_tag_score[label] × confidence
        探索模式 (CV ≤ threshold): 匹配分 = random(0,1) × dim_weight
        """
        total = 0.0
        for tag in ctx.get("tags", []):
            dim = tag["dimension"]
            label = tag["label"]
            cv = cv_map.get(dim, 0.0)

            if cv > (self._cv_threshold or 0.5):
                # 精准模式
                user_s = user_score_map.get(dim, {}).get(label, 0.0)
                conf = tag.get("confidence", 1.0) or 1.0
                total += user_s * conf
            else:
                # 探索模式
                total += random.random() * self._dim_weight(dim)

        ctx["_score"] = total
        return total

    async def _get_candidates(self, user_id: int, limit: int) -> List[int]:
        """
        输入: user_id, limit
        输出: 候选电影 ID 列表（已排除该用户标记过 watched 的）
        """
        raw = self.db.raw_mysql()
        rows = await raw.execute_query(
            """SELECT DISTINCT m.id
               FROM movies m
               WHERE m.is_published = 1
                 AND m.id NOT IN (
                   SELECT DISTINCT movie_id
                   FROM user_action_log
                   WHERE user_id = %s AND action = 'watched' AND reverted_at IS NULL
                 )
               ORDER BY m.id DESC
               LIMIT %s""",
            (user_id, limit),
        )
        return [r["id"] for r in rows]

    async def _cold_start(self, top_n: int) -> List[Dict[str, Any]]:
        """冷启动: 按评分降序返回热门电影"""
        raw = self.db.raw_mysql()
        rows = await raw.execute_query(
            """SELECT m.id AS movie_id, m.douban_id, m.title, m.poster_url, m.release_year,
                      mr.average AS rating
               FROM movies m
               LEFT JOIN movie_ratings mr ON m.id = mr.movie_id
               WHERE m.is_published = 1
               ORDER BY mr.average DESC
               LIMIT %s""",
            (top_n,),
        )
        return [
            {
                "movie_id": r["movie_id"],
                "douban_id": r["douban_id"],
                "title": r["title"],
                "poster_url": r["poster_url"],
                "release_year": r["release_year"],
                "score": 0.0,
                "rating": float(r["rating"]) if r.get("rating") else None,
            }
            for r in rows
        ]

    async def _batch_build_contexts(self, movie_ids: List[int]) -> List[Dict[str, Any]]:
        """
        批量构建候选电影的标签上下文（替代逐部调 MovieContextService.build()）。

        批量查询 ~6 次，而非 200×6=1200 次。
        """
        if not movie_ids:
            return []

        raw = self.db.raw_mysql()
        placeholders = ",".join(["%s"] * len(movie_ids))
        params = tuple(movie_ids)

        # ── A. movies 基础信息 ──
        movie_rows = await raw.execute_query(
            f"SELECT id, douban_id, title, poster_url, release_year FROM movies WHERE id IN ({placeholders})",
            params,
        )
        movies = {r["id"]: r for r in movie_rows}

        # ── B. 地区 ──
        region_rows = await raw.execute_query(
            f"""SELECT mr.movie_id, r.id AS region_id, r.name AS region_name
                FROM movie_regions mr
                JOIN regions r ON mr.region_id = r.id
                WHERE mr.movie_id IN ({placeholders})""",
            params,
        )

        # ── C. 导演 ──
        dir_rows = await raw.execute_query(
            f"""SELECT mc.movie_id, p.id AS person_id, p.name AS person_name
                FROM movie_credits mc
                JOIN people p ON mc.person_id = p.id
                WHERE mc.movie_id IN ({placeholders}) AND mc.role_type = 'director'""",
            params,
        )

        # ── D. 演员 top-5（每个电影取前5） ──
        #    用 ROW_NUMBER 窗口函数按 movie_id 分组取前5
        actor_rows = await raw.execute_query(
            f"""SELECT movie_id, person_id, person_name FROM (
                    SELECT mc.movie_id, p.id AS person_id, p.name AS person_name,
                           ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY mc.movie_id) AS rn
                    FROM movie_credits mc
                    JOIN people p ON mc.person_id = p.id
                    WHERE mc.movie_id IN ({placeholders}) AND mc.role_type = 'actor'
                ) sub WHERE rn <= 5""",
            params,
        )

        # ── E. 豆瓣分类 ──
        genre_rows = await raw.execute_query(
            f"""SELECT mg.movie_id, mg.type_num, cp.type_name
                FROM movie_genres mg
                JOIN crawl_progress cp ON cp.type_num = mg.type_num
                WHERE mg.movie_id IN ({placeholders})
                GROUP BY mg.movie_id, mg.type_num, cp.type_name""",
            params,
        )

        # ── F. AI 风格标签 ──
        style_rows = await raw.execute_query(
            f"""SELECT ms.movie_id, mst.name, mst.dimension, ms.confidence
                FROM movie_style ms
                JOIN movie_style_tag mst ON ms.tag_id = mst.id
                WHERE ms.movie_id IN ({placeholders})
                ORDER BY ms.movie_id, mst.dimension""",
            params,
        )

        # ── 拼装 ──
        contexts = []
        _ALL_DIMS_SET = frozenset(_ALL_DIMS)
        _DCN = {"overall": "整体", "plot": "剧情", "visual": "画面", "narrative": "叙事", "pacing": "节奏"}

        for mid in movie_ids:
            m = movies.get(mid)
            if not m:
                continue

            tags: List[Dict[str, Any]] = []

            # era
            year = m.get("release_year") or 0
            if year > 0:
                label = decade_label(year)
                tags.append({
                    "dimension": "era",
                    "label": label,
                    "value": str(year),
                    "confidence": 1.0,
                    "weight": self._dim_weight("era"),
                    "source": "douban",
                })

            # regions
            for rr in region_rows:
                if rr["movie_id"] == mid:
                    tags.append({
                        "dimension": "region",
                        "label": rr["region_name"],
                        "value": str(rr["region_id"]),
                        "confidence": 1.0,
                        "weight": self._dim_weight("region"),
                        "source": "douban",
                    })

            # directors
            for dr in dir_rows:
                if dr["movie_id"] == mid:
                    tags.append({
                        "dimension": "director",
                        "label": dr["person_name"],
                        "value": str(dr["person_id"]),
                        "confidence": 1.0,
                        "weight": self._dim_weight("director"),
                        "source": "douban",
                    })

            # actors
            actor_idx = 0
            for ar in actor_rows:
                if ar["movie_id"] == mid:
                    actor_idx += 1
                    tags.append({
                        "dimension": "actor",
                        "label": ar["person_name"],
                        "value": str(ar["person_id"]),
                        "confidence": 1.0,
                        "weight": self._dim_weight("actor"),
                        "source": "douban",
                    })

            # genres
            for gr in genre_rows:
                if gr["movie_id"] == mid:
                    tags.append({
                        "dimension": "genre",
                        "label": gr["type_name"],
                        "value": str(gr["type_num"]),
                        "confidence": 1.0,
                        "weight": self._dim_weight("genre"),
                        "source": "douban",
                    })

            # AI styles
            for sr in style_rows:
                if sr["movie_id"] == mid:
                    dim = sr["dimension"]
                    conf = float(sr["confidence"])
                    tags.append({
                        "dimension": dim,
                        "label": sr["name"],
                        "value": None,
                        "confidence": conf,
                        "weight": round(self._dim_weight(dim) * conf, 2),
                        "source": "ai",
                    })

            contexts.append({
                "movie_id": mid,
                "douban_id": m["douban_id"],
                "title": m["title"],
                "poster_url": m.get("poster_url"),
                "release_year": m.get("release_year"),
                "tags": tags,
            })

        logger.debug("[Recommend] 批量构建 %d 部电影上下文", len(contexts))
        return contexts

    async def _enrich_with_ratings(self, contexts: List[Dict]) -> List[Dict]:
        """补全评分信息"""
        if not contexts:
            return contexts
        movie_ids = [c["movie_id"] for c in contexts]
        placeholders = ",".join(["%s"] * len(movie_ids))
        raw = self.db.raw_mysql()
        rows = await raw.execute_query(
            f"SELECT movie_id, average FROM movie_ratings WHERE movie_id IN ({placeholders})",
            tuple(movie_ids),
        )
        rating_map = {r["movie_id"]: float(r["average"]) for r in rows if r.get("average") is not None}
        for c in contexts:
            c["rating"] = rating_map.get(c["movie_id"])
        return contexts


# ═══════════════════════════════════════════════════════════════
# 模块级单例
# ═══════════════════════════════════════════════════════════════

_recommend_service: Optional[RecommendService] = None


def init_recommend_service(db: DatabaseLayerV2) -> RecommendService:
    global _recommend_service
    _recommend_service = RecommendService(db)
    logger.info("RecommendService 已初始化")
    return _recommend_service


def get_recommend_service() -> RecommendService:
    if _recommend_service is None:
        raise RuntimeError("RecommendService 未初始化，请先调用 init_recommend_service(db)")
    return _recommend_service
