"""
services/movie_context.py

电影标签上下文聚合服务 — 从多表拼装带权重/来源/置信度的标签集合。

输入: DatabaseLayerV2 实例（依赖注入）
输出: build(movie_id) → Dict 标签上下文对象

数据源:
    movies / movie_credits+people / movie_genres+crawl_progress / movie_regions+regions
    movie_style+movie_style_tag / review_summary
    config_score_weight (权重配置，热加载)

使用方式:
    from services.movie_context import init_movie_context, get_movie_context

    init_movie_context(db)                  ← app.py startup 中调用
    ctx = await get_movie_context().build(38)

设计:
    - 配置从 config_score_weight 表加载，缓存于内存
    - 维度权重按 config_key 分组读取 (dim.era / dim.region / ...)
    - 演员位置衰减按 config_key 分组读取 (actor.decay.1 ~ 5)
    - 配置表不存在时使用内置默认值兜底
"""

import logging
from typing import Any, Dict, List, Optional

from db.database_v2 import DatabaseLayerV2

logger = logging.getLogger(__name__)

# ── 维度权重默认值（config_score_weight 表不存在时兜底） ──
_DEFAULT_DIM_WEIGHTS: Dict[str, float] = {
    "era": 0.3,
    "region": 0.4,
    "director": 1.0,
    "actor": 0.8,
    "genre": 0.6,
    "overall": 0.7,
    "plot": 0.7,
    "visual": 0.7,
    "narrative": 0.7,
    "pacing": 0.7,
}

# ── 演员位置衰减默认值 ──
_DEFAULT_ACTOR_DECAY: Dict[int, float] = {
    1: 1.0,
    2: 0.85,
    3: 0.70,
    4: 0.55,
    5: 0.40,
}


# ═══════════════════════════════════════════════════════════════
# 纯函数 — 无副作用，不依赖 I/O
# ═══════════════════════════════════════════════════════════════

def decade(year: int) -> str:
    """输入: 年份, 输出: 年代区间字符串，如 1994 → '1990s'"""
    if year <= 0:
        return "未知"
    d = (year // 10) * 10
    return f"{d}s"


def decade_label(year: int) -> str:
    """输入: 年份, 输出: 人类可读年代标签，如 1994 → '1990s年代'"""
    d = decade(year)
    return f"{d}年代"


def _count_by_dimension(tags: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for t in tags:
        d = t["dimension"]
        counts[d] = counts.get(d, 0) + 1
    return counts


def _count_by_source(tags: List[Dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for t in tags:
        s = t["source"]
        counts[s] = counts.get(s, 0) + 1
    return counts


# ═══════════════════════════════════════════════════════════════
# MovieContextService — 核心服务类
# ═══════════════════════════════════════════════════════════════

class MovieContextService:
    """
    电影标签上下文聚合服务。

    输入: DatabaseLayerV2 实例（依赖注入）
    输出: build(movie_id) → 标签上下文 dict

    配置加载策略:
        - 首次调用 build() 时自动加载 config_score_weight 到内存
        - refresh_config() 可手动刷新（UPDATE 配置后调用）
        - 表不存在时使用内置默认值兜底
    """

    def __init__(self, db: DatabaseLayerV2):
        self.db = db
        self._config_loaded = False
        self._dim_weights: Dict[str, float] = {}
        self._actor_decay: Dict[int, float] = {}

    async def refresh_config(self) -> None:
        """
        从 config_score_weight 表重新加载权重配置到内存。

        输入: 无
        输出: 无
        副作用: 更新 self._dim_weights / self._actor_decay
        """
        self._dim_weights = {}
        self._actor_decay = {}
        self._config_loaded = False

        try:
            raw = self.db.raw_mysql()
            rows = await raw.execute_query(
                "SELECT config_key, config_value FROM config_score_weight "
                "WHERE config_key LIKE 'dim.%' OR config_key LIKE 'actor.decay.%'"
            )
            if rows:
                for r in rows:
                    key: str = r["config_key"]
                    val: float = float(r["config_value"])
                    if key.startswith("dim."):
                        dim_name = key[4:]  # "dim.era" -> "era"
                        self._dim_weights[dim_name] = val
                    elif key.startswith("actor.decay."):
                        pos_str = key[12:]  # "actor.decay.1" -> "1"
                        try:
                            self._actor_decay[int(pos_str)] = val
                        except ValueError:
                            pass

                logger.debug(
                    "[MovieContext] 配置加载完成: dim_weights=%d keys, actor_decay=%d positions",
                    len(self._dim_weights), len(self._actor_decay),
                )
            else:
                logger.info("[MovieContext] config_score_weight 表为空，使用默认权重")
        except Exception:
            logger.warning("[MovieContext] config_score_weight 表不可用，使用默认权重", exc_info=True)

        self._config_loaded = True

    async def _ensure_config(self) -> None:
        """保证配置已加载（懒加载，首次build时触发）"""
        if not self._config_loaded:
            await self.refresh_config()

    def _dim_weight(self, dimension: str) -> float:
        """
        输入: 维度名 (era/region/director/...)
        输出: 该维度的基础权重，优先读表，表不可用则用默认值
        """
        val = self._dim_weights.get(dimension)
        if val is not None:
            return val
        return _DEFAULT_DIM_WEIGHTS.get(dimension, 0.5)

    def _position_decay(self, position: int) -> float:
        """
        输入: 演员排名 (1~N)
        输出: 位置衰减系数，优先读表，表不可用则用默认值
        """
        if position in self._actor_decay:
            return self._actor_decay[position]
        return _DEFAULT_ACTOR_DECAY.get(position, 0.30)

    # ── 核心方法 ──

    async def build(self, movie_id: int) -> Dict[str, Any]:
        """
        输入: movie_id — 本地 movies.id
        输出: 标签上下文 dict {
            movie_id, douban_id, title,
            tags: [{
                dimension, label, value, confidence, weight, source
            }, ...],
            ai_summary: str|null,
            stats: { total_tags, by_dimension, by_source }
        }
        副作用: 只读，6 次查询
        """
        await self._ensure_config()

        raw = self.db.raw_mysql()
        tags: List[Dict[str, Any]] = []

        # ── 1. 基础信息 ──
        movie_rows = await raw.execute_query(
            "SELECT id, douban_id, title, release_year FROM movies WHERE id=%s",
            (movie_id,),
        )
        if not movie_rows:
            return {"error": f"movie_id={movie_id} 不存在"}

        movie = movie_rows[0]
        movie_title: str = movie["title"]
        movie_year: int = movie["release_year"] or 0
        movie_douban_id: str = movie["douban_id"]

        # ── 2. 年代 ──
        label = decade_label(movie_year)
        base_w = self._dim_weight("era")
        tags.append({
            "dimension": "era",
            "label": label,
            "value": str(movie_year),
            "confidence": 1.0,
            "weight": round(base_w * 1.0, 2),
            "source": "douban",
        })

        # ── 3. 地区 ──
        region_rows = await raw.execute_query(
            """SELECT r.id, r.name
               FROM movie_regions mr
               JOIN regions r ON mr.region_id = r.id
               WHERE mr.movie_id=%s""",
            (movie_id,),
        )
        base_w = self._dim_weight("region")
        for r in region_rows:
            tags.append({
                "dimension": "region",
                "label": r["name"],
                "value": str(r["id"]),
                "confidence": 1.0,
                "weight": round(base_w * 1.0, 2),
                "source": "douban",
            })

        # ── 4. 导演 ──
        dir_rows = await raw.execute_query(
            """SELECT p.id, p.name
               FROM movie_credits mc
               JOIN people p ON mc.person_id = p.id
               WHERE mc.movie_id=%s AND mc.role_type='director'""",
            (movie_id,),
        )
        base_w = self._dim_weight("director")
        for d in dir_rows:
            tags.append({
                "dimension": "director",
                "label": d["name"],
                "value": str(d["id"]),
                "confidence": 1.0,
                "weight": round(base_w * 1.0, 2),
                "source": "douban",
            })

        # ── 5. 演员 top-5（按 movie_credits 插入顺序，位置衰减） ──
        actor_rows = await raw.execute_query(
            """SELECT p.id, p.name
               FROM movie_credits mc
               JOIN people p ON mc.person_id = p.id
               WHERE mc.movie_id=%s AND mc.role_type='actor'
               LIMIT 5""",
            (movie_id,),
        )
        base_w = self._dim_weight("actor")
        for i, a in enumerate(actor_rows, 1):
            decay = self._position_decay(i)
            w = round(base_w * 1.0 * decay, 2)
            tags.append({
                "dimension": "actor",
                "label": a["name"],
                "value": str(a["id"]),
                "confidence": 1.0,
                "weight": w,
                "source": "douban",
            })

        # ── 6. 豆瓣分类 ──
        genre_rows = await raw.execute_query(
            """SELECT mg.type_num AS id, cp.type_name AS name
               FROM movie_genres mg
               JOIN crawl_progress cp ON cp.type_num = mg.type_num
               WHERE mg.movie_id=%s
               GROUP BY mg.type_num, cp.type_name""",
            (movie_id,),
        )
        base_w = self._dim_weight("genre")
        for g in genre_rows:
            tags.append({
                "dimension": "genre",
                "label": g["name"],
                "value": str(g["id"]),
                "confidence": 1.0,
                "weight": round(base_w * 1.0, 2),
                "source": "douban",
            })

        # ── 7. AI 风格标签（5 维度，有 confidence） ──
        style_rows = await raw.execute_query(
            """SELECT mst.name, mst.dimension, ms.confidence
               FROM movie_style ms
               JOIN movie_style_tag mst ON ms.tag_id = mst.id
               WHERE ms.movie_id=%s
               ORDER BY mst.dimension, ms.confidence DESC""",
            (movie_id,),
        )
        for sr in style_rows:
            dim = sr["dimension"]
            label_val = sr["name"]
            conf = float(sr["confidence"])
            base_w = self._dim_weight(dim)
            w = round(base_w * conf, 2)
            tags.append({
                "dimension": dim,
                "label": label_val,
                "value": None,
                "confidence": conf,
                "weight": w,
                "source": "ai",
            })

        # ── 8. AI 总结 ──
        summary_rows = await raw.execute_query(
            "SELECT full_summary FROM review_summary WHERE movie_id=%s AND status='done' LIMIT 1",
            (movie_id,),
        )
        ai_summary: Optional[str] = None
        if summary_rows and summary_rows[0].get("full_summary"):
            ai_summary = summary_rows[0]["full_summary"]

        # ── 组装 ──
        return {
            "movie_id": movie_id,
            "douban_id": movie_douban_id,
            "title": movie_title,
            "tags": tags,
            "ai_summary": ai_summary,
            "stats": {
                "total_tags": len(tags),
                "by_dimension": _count_by_dimension(tags),
                "by_source": _count_by_source(tags),
            },
        }


# ═══════════════════════════════════════════════════════════════
# 模块级单例
# ═══════════════════════════════════════════════════════════════

_movie_context: Optional[MovieContextService] = None


def init_movie_context(db: DatabaseLayerV2) -> MovieContextService:
    """
    初始化 MovieContextService 单例。

    输入: DatabaseLayerV2 实例
    输出: MovieContextService 实例
    副作用: 设置模块级 _movie_context 单例
    """
    global _movie_context
    _movie_context = MovieContextService(db)
    logger.info("MovieContextService 已初始化")
    return _movie_context


def get_movie_context() -> MovieContextService:
    """
    获取 MovieContextService 单例。
    若未初始化则抛出 RuntimeError。
    """
    if _movie_context is None:
        raise RuntimeError("MovieContextService 未初始化，请先调用 init_movie_context(db)")
    return _movie_context
