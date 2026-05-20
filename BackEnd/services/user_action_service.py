"""
services/user_action_service.py

用户行为评分服务 — 接收用户操作，编排状态校验 + 分数计算 + 多表写入。

输入: DatabaseLayerV2 实例（依赖注入）
输出: ActionResult / TagProfileResponse / MovieStatusResponse

核心方法:
    execute_action(user_id, movie_id, action) → ActionResult
    rollback_action(user_id, movie_id, action) → ActionResult
    get_user_tag_profile(user_id, dimension?, decayed?) → TagProfileResponse
    get_movie_status(user_id, movie_id) → MovieStatusResponse

依赖:
    services/movie_context.py  — MovieContextService.build() 获取归一化标签
    models/user_action.py      — Pydantic 请求/响应模型

使用方式:
    from services.user_action_service import init_user_action_service, get_user_action_service

    init_user_action_service(db)
    svc = get_user_action_service()
    result = await svc.execute_action(user_id=1, movie_id=38, action='watched')
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.database_v2 import DatabaseLayerV2
from utils.snowflake import generate_id
from services.movie_context import get_movie_context
from models.user_action import ActionResult, MovieStatusResponse, TagItem, TagProfileResponse

logger = logging.getLogger(__name__)


def _mask_author(author: str) -> str:
    """昵称去敏 — 保留前2字符 + **"""
    if not author:
        return ""
    if len(author) <= 2:
        return author[0] + "*"
    return author[:2] + "**"


# ── 操作权重默认值（config_score_weight 表不可用时兜底） ──
_DEFAULT_ACTION_WEIGHTS: Dict[str, float] = {
    "want_watch": 1.0,
    "watching": 1.2,
    "watched": 2.0,
    "favorite": 1.5,
    "comment": 3.0,
}

# 观看状态机 — 递进顺序
_WATCH_ACTIONS = ("want_watch", "watching", "watched")


class UserActionService:
    """
    用户行为评分服务。

    输入: DatabaseLayerV2 实例（依赖注入）
    输出: 操作结果 / 画像 / 状态查询
    """

    def __init__(self, db: DatabaseLayerV2):
        self.db = db
        self._action_weights: Dict[str, float] = {}
        self._config_loaded = False

    async def _ensure_config(self) -> None:
        """懒加载 action 权重配置"""
        if self._config_loaded:
            return
        try:
            raw = self.db.raw_mysql()
            rows = await raw.execute_query(
                "SELECT config_key, config_value FROM config_score_weight "
                "WHERE config_key LIKE 'action.%'"
            )
            if rows:
                for r in rows:
                    key = r["config_key"]
                    if key.startswith("action."):
                        action_name = key[7:]  # "action.watched" -> "watched"
                        self._action_weights[action_name] = float(r["config_value"])
        except Exception:
            logger.warning("[UserAction] 配置加载失败，使用默认权重", exc_info=True)
        self._config_loaded = True

    def _action_weight(self, action: str) -> float:
        val = self._action_weights.get(action)
        if val is not None:
            return val
        return _DEFAULT_ACTION_WEIGHTS.get(action, 1.0)

    # ═══════════════════════════════════════════════════════════
    # 公开方法
    # ═══════════════════════════════════════════════════════════

    async def execute_action(
        self,
        user_id: int,
        movie_id: int,
        action: str,
        review_text: Optional[str] = None,
        rating: Optional[float] = None,
    ) -> ActionResult:
        """
        输入: user_id, movie_id, action
        输出: ActionResult { action, movie_id, score_total, tag_count }
        异常: ValueError — 业务规则校验失败
        副作用:
            - MySQL: user_movie_status / user_action_log / user_tag_score
            - MongoDB: comments（仅 review 操作）
        """
        await self._ensure_config()

        if action not in ("want_watch", "watching", "watched", "favorite", "comment"):
            raise ValueError(f"不支持的操作类型: {action}")

        # ── ① 加载当前状态 ──
        current = await self._load_status(user_id, movie_id)

        # ── ② 幂等校验 ──
        self._check_idempotent(current, action)

        # ── ③ 状态机递进检查 ──
        need_revert, prev_action = self._check_transition(current, action)

        # ── ④ comment 特殊校验 ──
        if action == "comment":
            if not current or not current.get("watched"):
                raise ValueError("请先标记看过，才能评论")
            # 评论幂等（user_action_log 中查）
            existing = await self._find_active_action(user_id, movie_id, "comment")
            if existing:
                raise ValueError("已评论过该电影")

        # ── ⑤ 计算分数 ──
        aw = self._action_weight(action)
        deltas, total_score = await self._calc_score_deltas(movie_id, aw)

        # ── ⑥ comment: 先写 MongoDB ──
        review_mongo_id: Optional[str] = None
        if action == "comment":
            review_mongo_id = await self._write_review_to_mongo(
                user_id, movie_id, review_text, rating
            )

        # ── ⑦ MySQL 事务 ──
        action_log_id = generate_id()
        original_deltas_json = json.dumps(deltas, ensure_ascii=False)

        async with self.db.transaction() as tx:
            # 7a. 更新 user_movie_status
            await self._apply_status(tx, user_id, movie_id, action)

            # 7b. 插入 user_action_log
            await tx.execute_raw(
                "INSERT INTO user_action_log (id, user_id, movie_id, action, score_delta, tag_deltas_json) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (action_log_id, user_id, movie_id, action, total_score, original_deltas_json),
            )

            # 7c. UPSERT user_tag_score × N
            for d in deltas:
                await tx.execute_raw(
                    "INSERT INTO user_tag_score (user_id, dimension, label, score, last_action) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE score = score + VALUES(score), last_action = VALUES(last_action)",
                    (user_id, d["dimension"], d["label"], d["delta"], action),
                )

            # 7d. 递进覆盖：回滚前一级
            if need_revert and prev_action:
                prev_log = await self._find_active_action(user_id, movie_id, prev_action)
                if prev_log:
                    prev_delta = float(prev_log.get("score_delta", 0))
                    prev_deltas_json = prev_log.get("tag_deltas_json")
                    # 标记原始记录为已回滚
                    await tx.execute_raw(
                        "UPDATE user_action_log SET reverted_at=NOW() WHERE id=%s",
                        (prev_log["id"],),
                    )
                    # 插入回滚记录（负分）
                    await tx.execute_raw(
                        "INSERT INTO user_action_log (id, user_id, movie_id, action, score_delta, reverted_at) "
                        "VALUES (%s, %s, %s, %s, %s, NOW())",
                        (generate_id(), user_id, movie_id, prev_action, -prev_delta),
                    )
                    # 抵扣分数
                    if prev_deltas_json:
                        try:
                            prev_deltas = json.loads(prev_deltas_json) if isinstance(prev_deltas_json, str) else prev_deltas_json
                            for pd in prev_deltas:
                                await tx.execute_raw(
                                    "INSERT INTO user_tag_score (user_id, dimension, label, score, last_action) "
                                    "VALUES (%s, %s, %s, %s, %s) "
                                    "ON DUPLICATE KEY UPDATE score = score + VALUES(score)",
                                    (user_id, pd["dimension"], pd["label"], -pd["delta"], prev_action),
                                )
                        except Exception:
                            logger.warning(
                                "[UserAction] 回滚 delta 解析失败 user=%s movie=%s prev=%s",
                                user_id, movie_id, prev_action, exc_info=True,
                            )

        logger.info(
            "[UserAction] action=%s user=%s movie=%s total=%.2f tags=%d revert=%s",
            action, user_id, movie_id, total_score, len(deltas), prev_action if need_revert else "无",
        )
        return ActionResult(action=action, movie_id=movie_id, score_total=round(total_score, 2), tag_count=len(deltas))

    async def rollback_action(
        self, user_id: int, movie_id: int, action: str
    ) -> ActionResult:
        """
        输入: user_id, movie_id, action
        输出: ActionResult（score_total 为负值）
        异常: ValueError — 当前未标记该状态
        """
        await self._ensure_config()

        # ── ① 校验当前状态 ──
        if action != "comment":
            current = await self._load_status(user_id, movie_id)
            if not current or not current.get(action):
                raise ValueError(f"未标记 {action}，无法取消")

        # ── ② 查原始操作记录 ──
        orig = await self._find_active_action(user_id, movie_id, action)
        if not orig:
            raise ValueError(f"未找到 {action} 的有效操作记录")

        orig_delta = float(orig.get("score_delta", 0))
        orig_deltas_json = orig.get("tag_deltas_json")

        # ── ③ MySQL 事务 ──
        async with self.db.transaction() as tx:
            # 3a. 更新状态
            if action == "watched":
                # 看过 → 清空观看标记，保留 favorite
                await tx.execute_raw(
                    "UPDATE user_movie_status SET want_watch=0, watching=0, watched=0 "
                    "WHERE user_id=%s AND movie_id=%s",
                    (user_id, movie_id),
                )
            elif action == "comment":
                # 评论回滚：MongoDB 在事务外处理
                pass
            else:
                # action 已入口校验，只可能是 want_watch/watching/favorite 之一
                await tx.execute_raw(
                    f"UPDATE user_movie_status SET {action}=0 WHERE user_id=%s AND movie_id=%s",
                    (user_id, movie_id),
                )

            # 3b. 标记原始记录为已回滚
            await tx.execute_raw(
                "UPDATE user_action_log SET reverted_at=NOW() WHERE id=%s",
                (orig["id"],),
            )

            # 3c. 插入回滚记录
            await tx.execute_raw(
                "INSERT INTO user_action_log (id, user_id, movie_id, action, score_delta, reverted_at) "
                "VALUES (%s, %s, %s, %s, %s, NOW())",
                (generate_id(), user_id, movie_id, action, -orig_delta),
            )

            # 3d. 抵扣分数
            tag_count = 0
            if orig_deltas_json:
                try:
                    deltas = json.loads(orig_deltas_json) if isinstance(orig_deltas_json, str) else orig_deltas_json
                    tag_count = len(deltas)
                    for d in deltas:
                        await tx.execute_raw(
                            "INSERT INTO user_tag_score (user_id, dimension, label, score, last_action) "
                            "VALUES (%s, %s, %s, %s, %s) "
                            "ON DUPLICATE KEY UPDATE score = score + VALUES(score)",
                            (user_id, d["dimension"], d["label"], -d["delta"], action),
                        )
                except Exception:
                    logger.warning("[UserAction] 回滚 delta 解析失败", exc_info=True)

        # ── ④ comment 回滚: 更新 MongoDB ──
        if action == "comment":
            await self._unpublish_user_review(user_id, movie_id)

        logger.info(
            "[UserAction] rollback action=%s user=%s movie=%s delta=-%.2f",
            action, user_id, movie_id, orig_delta,
        )
        return ActionResult(action=action, movie_id=movie_id, score_total=round(-orig_delta, 2), tag_count=tag_count)

    async def get_user_tag_profile(
        self, user_id: int, dimension: Optional[str] = None, decayed: bool = False
    ) -> TagProfileResponse:
        """
        输入: user_id, dimension(可选), decayed(是否时间衰减)
        输出: TagProfileResponse { user_id, tags, total_tags }
        """
        raw = self.db.raw_mysql()

        if decayed:
            # 衰减版：查 user_action_log → Python 侧展开 JSON + 时间窗口打折
            sql = """SELECT tag_deltas_json, score_delta, created_at
                     FROM user_action_log
                     WHERE user_id=%s AND reverted_at IS NULL AND tag_deltas_json IS NOT NULL"""
            params: tuple = (user_id,)
            rows = await raw.execute_query(sql, params)

            # 时间衰减系数
            from datetime import timedelta
            from datetime import datetime as dt
            now = dt.now()
            windows = [
                (timedelta(days=30), 1.0),
                (timedelta(days=90), 0.8),
                (timedelta(days=180), 0.5),
                (timedelta.max, 0.2),
            ]

            def _decay_factor(created_at_val):
                created_at = created_at_val if isinstance(created_at_val, dt) else dt.fromisoformat(str(created_at_val))
                age = now - created_at
                for window, factor in windows:
                    if age <= window:
                        return factor
                return 0.2

            from collections import defaultdict
            acc: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

            for r in rows:
                raw_json = r["tag_deltas_json"]
                if not raw_json:
                    continue
                try:
                    deltas = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                except (json.JSONDecodeError, TypeError):
                    continue
                factor = _decay_factor(r["created_at"])

                for d in deltas:
                    dim = d.get("dimension", "")
                    lbl = d.get("label", "")
                    delta = float(d.get("delta", 0))
                    if dimension and dim != dimension:
                        continue
                    acc[dim][lbl] += delta * factor

            # 转成排序列表
            items = []
            for dim, labels in acc.items():
                for lbl, score in labels.items():
                    items.append((dim, lbl, score))
            items.sort(key=lambda x: -x[2])

            tags = [
                TagItem(
                    dimension=dim,
                    label=lbl,
                    score=round(score, 4),
                    source="douban" if dim in ("era", "region", "director", "actor", "genre") else "ai",
                )
                for dim, lbl, score in items
            ]
            return TagProfileResponse(user_id=user_id, tags=tags, total_tags=len(tags))

        # 实时版：直接查 user_tag_score
        sql = "SELECT dimension, label, score FROM user_tag_score WHERE user_id=%s"
        params_t: tuple = (user_id,)
        if dimension:
            sql += " AND dimension=%s"
            params_t = (user_id, dimension)
        sql += " ORDER BY score DESC"

        rows = await raw.execute_query(sql, params_t)

        tags = [
            TagItem(
                dimension=r["dimension"],
                label=r["label"],
                score=round(float(r["score"]), 4),
                source="douban" if r["dimension"] in ("era", "region", "director", "actor", "genre") else "ai",
            )
            for r in rows
        ]
        return TagProfileResponse(user_id=user_id, tags=tags, total_tags=len(tags))

    async def get_movie_status(self, user_id: int, movie_id: int) -> MovieStatusResponse:
        """
        输入: user_id, movie_id
        输出: MovieStatusResponse { movie_id, want_watch, watching, watched, favorite, reviewed }
        """
        current = await self._load_status(user_id, movie_id)
        reviewed = await self._find_active_action(user_id, movie_id, "comment")

        return MovieStatusResponse(
            movie_id=movie_id,
            want_watch=bool(current.get("want_watch")) if current else False,
            watching=bool(current.get("watching")) if current else False,
            watched=bool(current.get("watched")) if current else False,
            favorite=bool(current.get("favorite")) if current else False,
            reviewed=reviewed is not None,
        )

    # ═══════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════

    async def _load_status(self, user_id: int, movie_id: int) -> Optional[Dict[str, Any]]:
        """查询 user_movie_status"""
        raw = self.db.raw_mysql()
        rows = await raw.execute_query(
            "SELECT want_watch, watching, watched, favorite FROM user_movie_status WHERE user_id=%s AND movie_id=%s",
            (user_id, movie_id),
        )
        return rows[0] if rows else None

    async def _find_active_action(self, user_id: int, movie_id: int, action: str) -> Optional[Dict[str, Any]]:
        """查找未回滚的操作记录"""
        raw = self.db.raw_mysql()
        rows = await raw.execute_query(
            "SELECT id, score_delta, tag_deltas_json FROM user_action_log "
            "WHERE user_id=%s AND movie_id=%s AND action=%s AND reverted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, movie_id, action),
        )
        return rows[0] if rows else None

    def _check_idempotent(self, current: Optional[Dict], action: str) -> None:
        """幂等校验：同一操作不可重复"""
        if action == "comment":
            return  # comment 在 execute_action 中单独校验
        if current and current.get(action):
            raise ValueError(f"已标记 {action}")

    def _check_transition(
        self, current: Optional[Dict], action: str
    ) -> tuple[bool, Optional[str]]:
        """
        状态机递进检查。

        输入: current 状态, action
        输出: (need_revert, prev_action)
        need_revert=True → 需要回滚前一级分数
        """
        if action not in _WATCH_ACTIONS:
            return False, None

        # 想看/在看/看过 的递进检查
        if action == "watching" and current and current.get("want_watch"):
            return True, "want_watch"
        if action == "watched" and current and current.get("watching"):
            return True, "watching"
        if action == "watched" and current and current.get("want_watch"):
            return True, "want_watch"
        return False, None

    async def _apply_status(
        self, tx, user_id: int, movie_id: int, action: str
    ) -> None:
        """在事务中更新 user_movie_status"""
        if action in _WATCH_ACTIONS:
            # 观看标记：先把前几个归零，再设当前为 1
            await tx.execute_raw(
                "INSERT INTO user_movie_status (user_id, movie_id, want_watch, watching, watched, favorite) "
                "VALUES (%s, %s, 0, 0, 0, 0) "
                "ON DUPLICATE KEY UPDATE want_watch=0, watching=0, watched=0",
                (user_id, movie_id),
            )
            # action 已通过 execute_action 入口严格控制，只可能是 want_watch/watching/watched
            await tx.execute_raw(
                f"UPDATE user_movie_status SET {action}=1 WHERE user_id=%s AND movie_id=%s",
                (user_id, movie_id),
            )
        elif action == "favorite":
            await tx.execute_raw(
                "INSERT INTO user_movie_status (user_id, movie_id, want_watch, watching, watched, favorite) "
                "VALUES (%s, %s, 0, 0, 0, 1) "
                "ON DUPLICATE KEY UPDATE favorite=1",
                (user_id, movie_id),
            )
        # comment 不改变 user_movie_status

    async def _calc_score_deltas(
        self, movie_id: int, action_weight: float
    ) -> tuple:
        """
        输入: movie_id, action_weight
        输出: (deltas_list, total_score)
        deltas_list = [{"dimension":"director", "label":"吕克·贝松", "delta":2.0}, ...]

        公式: delta = action_weight × tag.weight
              (tag.weight 已包含 dim_weight × confidence × actor_decay)
        """
        ctx_svc = get_movie_context()
        ctx = await ctx_svc.build(movie_id)
        if "error" in ctx:
            raise ValueError(ctx["error"])

        deltas: List[Dict[str, Any]] = []
        total = 0.0
        for tag in ctx["tags"]:
            d = round(action_weight * tag["weight"], 4)
            deltas.append({
                "dimension": tag["dimension"],
                "label": tag["label"],
                "delta": d,
            })
            total += d

        return deltas, total

    async def _write_review_to_mongo(
        self, user_id: int, movie_id: int, text: Optional[str], rating: Optional[float]
    ) -> str:
        """
        写入用户评论到 MongoDB comments 集合。

        输入: user_id, movie_id, text, rating
        输出: MongoDB _id（"user_{uid}_movie_{mid}" 格式）
        副作用: INSERT 到 MongoDB comments
        """
        from datetime import datetime

        mongo_id = f"user_{user_id}_movie_{movie_id}"

        # 查 movie 元数据补 douban_id 和 author
        raw = self.db.raw_mysql()
        movie_rows = await raw.execute_query(
            "SELECT douban_id, title FROM movies WHERE id=%s LIMIT 1",
            (movie_id,),
        )
        movie_douban_id = movie_rows[0]["douban_id"] if movie_rows else str(movie_id)

        # 查用户显示名
        user_rows = await raw.execute_query(
            "SELECT display_name, username FROM users WHERE id=%s LIMIT 1",
            (user_id,),
        )
        author = user_rows[0]["display_name"] or user_rows[0]["username"] if user_rows else f"用户{user_id}"

        set_doc = {
            "movie_douban_id": movie_douban_id,
            "movie_id": movie_id,
            "user_id": user_id,
            "author": _mask_author(author),
            "rating": rating or 0.0,
            "text": text or "",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "useful_count": 0,
            "is_published": True,
            "removed_by": None,
        }
        set_on_insert = {
            "crawled_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        }

        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        _set_key = "$set"
        _set_on_insert_key = "$setOnInsert"
        try:
            await self.db.update(
                "comments", {"_id": mongo_id},
                {_set_key: set_doc, _set_on_insert_key: set_on_insert},
                upsert=True,
            )
            logger.info("[UserAction] 评论写入 MongoDB: id=%s movie=%s", mongo_id, movie_id)
        except Exception:
            raise
        finally:
            self.db._set_type(original_type)

        return mongo_id

    async def _unpublish_user_review(self, user_id: int, movie_id: int) -> None:
        """
        用户自删评论 — MongoDB 标记 is_published=false, removed_by='user'

        输入: user_id, movie_id
        副作用: MongoDB update
        """
        mongo_id = f"user_{user_id}_movie_{movie_id}"
        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            _set_key = "$set"
            await self.db.update(
                "comments", {"_id": mongo_id},
                {_set_key: {"is_published": False, "removed_by": "user"}},
            )
            logger.info("[UserAction] 评论下架: id=%s", mongo_id)
        except Exception:
            raise
        finally:
            self.db._set_type(original_type)


# ═══════════════════════════════════════════════════════════════
# 模块级单例
# ═══════════════════════════════════════════════════════════════

_user_action_service: Optional[UserActionService] = None


def init_user_action_service(db: DatabaseLayerV2) -> UserActionService:
    global _user_action_service
    _user_action_service = UserActionService(db)
    logger.info("UserActionService 已初始化")
    return _user_action_service


def get_user_action_service() -> UserActionService:
    if _user_action_service is None:
        raise RuntimeError("UserActionService 未初始化，请先调用 init_user_action_service(db)")
    return _user_action_service
