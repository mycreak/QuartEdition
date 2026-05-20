"""
services/playlist_service.py

片单业务层 — 管理端 CRUD + 定时上下架 + 用户端查询。

通过 DatabaseLayerV2.raw_mysql() 操作 MySQL，
movie_ids JSON 列在应用层序列化/反序列化。

职责：
    管理端: create / update / delete / publish / unpublish / list_all（含筛选）
    用户端: list_published（轮播，时间窗口过滤） / detail（含电影摘要）

定时上下架方案（系统本地时间 — 2026-05-21 统一）：
    不依赖 cron。publish_at / unpublish_at 在查询时用 WHERE 条件过滤
    → publish_at <= NOW() 才可见，unpublish_at IS NULL OR > NOW() 仍可见
    → 管理员手动 "发布" 时设 publish_at = datetime.now()，立即生效

时区约定：
    - 所有 datetime 统一以系统本地时间 (UTC+8) 存储到 MySQL DATETIME 列
    - MySQL 连接池默认 SET time_zone='+08:00'，NOW() 返回本地时间
    - 前端传入 ISO 字符串：无时区视为本地时间，有时区转为本地时间
    - 输出给前端：保持本地时间原始值，前端 JavaScript new Date() 自动按本地时间解析

每一行注释标注："输入、输出、副作用"
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from db.database_v2 import DatabaseLayerV2

_CST = timezone(timedelta(hours=8))

logger = logging.getLogger(__name__)

_playlist_service: Optional["PlaylistService"] = None

# 全字段列表，避免多处重复
_ALL_COLS = "id, title, description, cover_url, movie_ids, sort_order, is_published, publish_at, unpublish_at, created_by, created_at, updated_at"


class PlaylistService:
    """
    片单服务。

    输入: DatabaseLayerV2 实例（依赖注入）
    输出: CRUD → dict；用户端 → 含电影完整信息的 dict
    """

    def __init__(self, db: DatabaseLayerV2):
        self.db = db

    # ═══════════════════════════════════════════════════════════
    # 管理端 CRUD
    # ═══════════════════════════════════════════════════════════

    async def create(
        self,
        title: str,
        movie_ids: List[int],
        description: str = "",
        cover_url: str = "",
        sort_order: int = 0,
        created_by: int = 1,
        publish_at: Optional[str] = None,
        unpublish_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        输入: title, movie_ids（必填）, description, cover_url, sort_order, created_by,
              publish_at / unpublish_at（可选 ISO 字符串，如 "2025-07-03T12:00:00"）
        输出: 完整片单 dict
        副作用: INSERT 一行
        """
        if not isinstance(movie_ids, list) or len(movie_ids) == 0:
            raise ValueError("movie_ids 必须为包含至少一个电影ID的非空数组")

        raw = self.db.raw_mysql()
        movie_ids_json = json.dumps(movie_ids, ensure_ascii=False)

        pub_dt = self._parse_datetime(publish_at)
        unpub_dt = self._parse_datetime(unpublish_at)

        await raw.execute_update(
            """INSERT INTO playlists (title, description, cover_url, movie_ids, sort_order, is_published, publish_at, unpublish_at, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (title.strip(), description.strip(), cover_url.strip(), movie_ids_json, sort_order, 0, pub_dt, unpub_dt, created_by),
        )

        rows = await raw.execute_query("SELECT LAST_INSERT_ID() AS id", ())
        new_id = rows[0]["id"] if rows else 0

        logger.info("[Playlist] 创建 id=%s title=%s movie_count=%d publish_at=%s unpublish_at=%s",
                     new_id, title, len(movie_ids), publish_at, unpublish_at)
        return await self._get_by_id(new_id)

    async def update(
        self,
        playlist_id: int,
        title: Optional[str] = None,
        movie_ids: Optional[List[int]] = None,
        description: Optional[str] = None,
        cover_url: Optional[str] = None,
        sort_order: Optional[int] = None,
        publish_at: Optional[str] = None,
        unpublish_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        输入: playlist_id + 可选的新值（None = 不更新该字段，"" = 清空该字段）
        输出: 更新后的片单 dict
        异常: ValueError
        副作用: UPDATE
        """
        existing = await self._get_by_id(playlist_id)
        if not existing:
            raise ValueError(f"片单 #{playlist_id} 不存在")

        raw = self.db.raw_mysql()
        sets: List[str] = []
        params: List[Any] = []

        if title is not None:
            sets.append("title = %s")
            params.append(title.strip())
        if description is not None:
            sets.append("description = %s")
            params.append(description.strip())
        if cover_url is not None:
            sets.append("cover_url = %s")
            params.append(cover_url.strip())
        if sort_order is not None:
            sets.append("sort_order = %s")
            params.append(sort_order)
        if movie_ids is not None:
            if not isinstance(movie_ids, list) or len(movie_ids) == 0:
                raise ValueError("movie_ids 必须为非空数组")
            sets.append("movie_ids = %s")
            params.append(json.dumps(movie_ids, ensure_ascii=False))
        if publish_at is not None:
            sets.append("publish_at = %s")
            params.append(self._parse_datetime(publish_at) if publish_at else None)
        if unpublish_at is not None:
            sets.append("unpublish_at = %s")
            params.append(self._parse_datetime(unpublish_at) if unpublish_at else None)

        if not sets:
            return existing

        params.append(playlist_id)
        sql = f"UPDATE playlists SET {', '.join(sets)} WHERE id = %s"
        await raw.execute_update(sql, tuple(params))

        logger.info("[Playlist] 更新 id=%s", playlist_id)
        return await self._get_by_id(playlist_id)

    async def delete(self, playlist_id: int) -> None:
        existing = await self._get_by_id(playlist_id)
        if not existing:
            raise ValueError(f"片单 #{playlist_id} 不存在")
        raw = self.db.raw_mysql()
        await raw.execute_update("DELETE FROM playlists WHERE id = %s", (playlist_id,))
        logger.info("[Playlist] 删除 id=%s title=%s", playlist_id, existing.get("title", ""))

    async def publish(self, playlist_id: int) -> Dict[str, Any]:
        """
        手动发布 — 设 is_published=1, publish_at=NOW()（如果未设）
        """
        return await self._set_published(playlist_id, True)

    async def unpublish(self, playlist_id: int) -> Dict[str, Any]:
        """手动下架 — 设 is_published=0, unpublish_at=NOW()（如果未设）"""
        return await self._set_published(playlist_id, False)

    async def list_all(
        self,
        keyword: Optional[str] = None,
        created_by: Optional[int] = None,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        publish_after: Optional[str] = None,
        publish_before: Optional[str] = None,
        is_published: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        管理端列表（含筛选）。

        输入:
            keyword:       按标题模糊搜索
            created_by:    按创建者过滤（None=所有人）
            created_after:  ISO 字符串 "2025-07-01T00:00:00"
            created_before: ISO 字符串
            publish_after:  上架时间起始
            publish_before: 上架时间结束
            is_published:   1=已发布 0=未发布 None=全部
        输出: 片单列表，按 sort_order ASC
        副作用: 只读
        """
        raw = self.db.raw_mysql()
        where: List[str] = []
        params: List[Any] = []

        if keyword:
            where.append("title LIKE %s")
            params.append(f"%{keyword.strip()}%")
        if created_by is not None:
            where.append("created_by = %s")
            params.append(created_by)
        if created_after is not None:
            where.append("created_at >= %s")
            params.append(self._parse_datetime(created_after))
        if created_before is not None:
            where.append("created_at <= %s")
            params.append(self._parse_datetime(created_before))
        if publish_after is not None:
            where.append("publish_at >= %s")
            params.append(self._parse_datetime(publish_after))
        if publish_before is not None:
            where.append("publish_at <= %s")
            params.append(self._parse_datetime(publish_before))
        if is_published is not None:
            where.append("is_published = %s")
            params.append(is_published)

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        sql = f"SELECT {_ALL_COLS} FROM playlists {where_clause} ORDER BY sort_order ASC, id ASC"

        rows = await raw.execute_query(sql, tuple(params) if params else ())
        return [self._row_to_dict(r) for r in rows]

    # ═══════════════════════════════════════════════════════════
    # 用户端
    # ═══════════════════════════════════════════════════════════

    async def list_published(self) -> List[Dict[str, Any]]:
        """
        轮播用 — 已发布 + 时间窗口内的片单列表。

        规则: is_published=1 且 publish_at <= NOW() 且 unpublish_at IS NULL OR > NOW()
        输出: [{ id, title, description, cover_url, sort_order }, ...]
        副作用: 只读
        """
        raw = self.db.raw_mysql()
        rows = await raw.execute_query(
            """SELECT id, title, description, cover_url, sort_order
               FROM playlists
               WHERE is_published = 1
                 AND (publish_at IS NULL OR publish_at <= NOW())
                 AND (unpublish_at IS NULL OR unpublish_at > NOW())
               ORDER BY sort_order ASC, id ASC"""
        )
        return [dict(r) for r in rows]

    async def detail(self, playlist_id: int) -> Dict[str, Any]:
        """
        片单详情 — 含电影摘要列表。

        输入: playlist_id
        输出: { id, title, description, cover_url, sort_order, movies: [...] }
        异常: ValueError
        副作用: 2 次查询
        """
        pl = await self._get_by_id(playlist_id)
        if not pl:
            raise ValueError(f"片单 #{playlist_id} 不存在")

        movie_ids = pl.get("movie_ids", [])
        if isinstance(movie_ids, str):
            try:
                movie_ids = json.loads(movie_ids)
            except json.JSONDecodeError:
                movie_ids = []

        movies = await self._batch_get_movie_summaries(movie_ids)

        return {
            "id": pl["id"],
            "title": pl["title"],
            "description": pl.get("description", ""),
            "cover_url": pl.get("cover_url", ""),
            "sort_order": pl.get("sort_order", 0),
            "movies": movies,
        }

    # ═══════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════

    async def _get_by_id(self, playlist_id: int) -> Optional[Dict[str, Any]]:
        raw = self.db.raw_mysql()
        rows = await raw.execute_query(
            f"SELECT {_ALL_COLS} FROM playlists WHERE id = %s",
            (playlist_id,),
        )
        if not rows:
            return None
        return self._row_to_dict(rows[0])

    def _row_to_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """数据库行 → 业务 dict，movie_ids JSON → list, datetime → ISO 字符串"""
        result = dict(row)

        # movie_ids: JSON 字符串 → list
        raw_ids = result.get("movie_ids")
        if isinstance(raw_ids, str):
            try:
                result["movie_ids"] = json.loads(raw_ids)
            except json.JSONDecodeError:
                result["movie_ids"] = []
        elif not isinstance(raw_ids, list):
            result["movie_ids"] = []

        # datetime → ISO 字符串
        for dt_key in ("publish_at", "unpublish_at", "created_at", "updated_at"):
            val = result.get(dt_key)
            if isinstance(val, datetime):
                result[dt_key] = val.strftime("%Y-%m-%dT%H:%M:%S")

        return result

    async def _set_published(self, playlist_id: int, publish: bool) -> Dict[str, Any]:
        existing = await self._get_by_id(playlist_id)
        if not existing:
            raise ValueError(f"片单 #{playlist_id} 不存在")

        raw = self.db.raw_mysql()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        val = 1 if publish else 0

        if publish:
            # 发布时自动设 publish_at（如果还没设）
            await raw.execute_update(
                "UPDATE playlists SET is_published = %s, publish_at = COALESCE(publish_at, %s) WHERE id = %s",
                (val, now, playlist_id),
            )
        else:
            # 下架时自动设 unpublish_at（如果还没设）
            await raw.execute_update(
                "UPDATE playlists SET is_published = %s, unpublish_at = COALESCE(unpublish_at, %s) WHERE id = %s",
                (val, now, playlist_id),
            )

        logger.info("[Playlist] %s id=%s", "发布" if publish else "下架", playlist_id)
        return await self._get_by_id(playlist_id)

    async def _batch_get_movie_summaries(self, movie_ids: List[int]) -> List[Dict[str, Any]]:
        """
        批量补全电影摘要（含 AI 总结）。

        输出: [{ id, title, poster_url, release_year, rating, ai_summary }, ...]
        副作用: 2 次查询（movies + review_summary）
        """
        if not movie_ids:
            return []

        placeholders = ",".join(["%s"] * len(movie_ids))
        params = tuple(movie_ids)
        raw = self.db.raw_mysql()

        # A. 电影基础信息 + 评分
        rows = await raw.execute_query(
            f"""SELECT m.id, m.title, m.poster_url, m.release_year,
                       mr.average AS rating
                FROM movies m
                LEFT JOIN movie_ratings mr ON m.id = mr.movie_id
                WHERE m.id IN ({placeholders})""",
            params,
        )

        # B. AI 总结（批量子查询，防 N+1）
        ai_rows = await raw.execute_query(
            f"""SELECT movie_id, full_summary
                FROM review_summary
                WHERE movie_id IN ({placeholders}) AND status = 'done'""",
            params,
        )
        ai_map = {r["movie_id"]: r["full_summary"] for r in ai_rows}

        movie_map = {
            r["id"]: {
                "id": r["id"],
                "title": r["title"],
                "poster_url": r.get("poster_url"),
                "release_year": r.get("release_year"),
                "rating": float(r["rating"]) if r.get("rating") is not None else None,
                "ai_summary": ai_map.get(r["id"]),
            }
            for r in rows
        }
        return [movie_map[mid] for mid in movie_ids if mid in movie_map]

    @staticmethod
    def _parse_datetime(val: Optional[str]) -> Optional[str]:
        """
        将前端传入的 ISO 字符串转为本地时间的 MySQL datetime 格式。

        输入：ISO 字符串（如 "2026-05-20T21:00:00" 或 "2026-05-20T21:00:00+08:00"）
        输出：本地时间 (UTC+8) 的 MySQL datetime 字符串（如 "2026-05-20 21:00:00"）
        规则：
            - 含时区 → 转为本地时间 (UTC+8) 后格式化
            - 无时区 → 视为本地时间，直接格式化
            - 非法值 → 返回 None（静默，由上层校验）
        """
        if not val:
            return None
        try:
            dt = datetime.fromisoformat(val)
            if dt.tzinfo is not None:
                dt = dt.astimezone(_CST).replace(tzinfo=None)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None


# ═══════════════════════════════════════════════════════════════
# 模块级单例
# ═══════════════════════════════════════════════════════════════


def init_playlist_service(db: DatabaseLayerV2) -> PlaylistService:
    global _playlist_service
    _playlist_service = PlaylistService(db)
    logger.info("PlaylistService 已初始化")
    return _playlist_service


def get_playlist_service() -> PlaylistService:
    if _playlist_service is None:
        raise RuntimeError("PlaylistService 未初始化，请先调用 init_playlist_service(db)")
    return _playlist_service
