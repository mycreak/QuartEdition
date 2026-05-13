"""
services/movie_service.py

电影业务层（Service Layer）
封装 DatabaseLayer 的多表 CRUD 与复合查询，对外暴露业务方法。

职责：
    1. 隐藏裸表名和 SQL 细节
    2. 编排多表复合查询（get_movie_detail 等）
    3. 输入校验（Pydantic 模型）→ 数据转换（json.dumps 等）→ 调用 db 层
    4. 返回 Pydantic Read 模型，调用方不需要关心数据库字段
    5. 所有写操作同步写入 {table}_history 版本表

版本记录规则：
    - create → INSERT _history（变更后的完整快照 + change_type='create'）
    - update → INSERT _history（变更后的完整快照 + change_type='update'）
    - delete → INSERT _history（删除前的完整快照 + change_type='delete'）
    - ratings 不记录版本（统计数据，非"纠错"场景）

每一行注释标注："输入、输出、副作用"
"""

import json
import logging
from datetime import date as date_type, datetime
from typing import Optional, List, Tuple, Dict, Any

from db.database_v2 import DatabaseLayerV2, ConditionBuilder
from models.movie_models import (
    MovieCreate, MovieUpdate, MovieRead,
    PeopleRead, GenreRead, RegionRead,
    RatingRead, RatingCreate,
    CreditRead, MovieDetail, GenreStat,
)
from utils.serializers import to_iso
from utils.errors import ResourceNotFoundError

logger = logging.getLogger(__name__)


class MovieService:
    """
    电影业务层

    输入：DatabaseLayerV2 实例（依赖注入，解耦具体数据库）
    副作用：读写 MySQL movie_db + 版本历史表（事务内）

    V2 事务策略：
        - create_movie / update_movie / delete_movie / set_movie_published
          → transaction() 内执行：主表写入 + history 写入（原子）
        - add_credit / remove_credit / add_genre / remove_genre / add_region / remove_region
          → transaction() 内执行：关联写入 + history 写入（原子）
        - set_rating → 不用事务（ON DUPLICATE KEY UPDATE 本身幂等）
    """

    def __init__(self, db: DatabaseLayerV2):
        self.db = db

    # ==================== 版本历史写入 ====================

    async def _write_history(
        self,
        table: str,
        entity_pk: dict,
        snapshot: dict,
        change_type: str,
        changed_by: str = "",
        tx=None,
    ):
        """
        写入版本历史记录（内部方法）。

        输入：
            table:       原表名（"movies" / "movie_credits" / ...）
            entity_pk:   原表主键映射（如 {"movie_id": 5}）
            snapshot:    变更后的全量字段快照
            change_type: "create" / "update" / "delete"
            changed_by:  操作人标识（管理员ID 或 "system"）
            tx:          事务上下文（传入 TransactionContext 时走事务内，
                         不传时退化为独立连接写入）
        副作用：INSERT INTO {table}_history
        """
        clean = {}
        for k, v in snapshot.items():
            if k == "id":
                continue
            clean[k] = to_iso(v)

        doc = {**entity_pk, **clean, "change_type": change_type, "changed_by": changed_by}
        history_table = f"{table}_history"
        try:
            if tx is not None:
                await tx.insert(history_table, doc, return_id=False)
            else:
                await self.db.insert(history_table, doc)
        except Exception:
            logger.exception(f"写入 {history_table} 失败（不影响主操作）")

    # ==================== 字典表查询 ====================

    async def list_genres(self, published_only: bool = False) -> List[GenreRead]:
        """
        输入：published_only — True 时只返回上架类型
        输出：全部类型列表（来自 crawl_progress，DISTINCT type_num）
        副作用：只读
        """
        if published_only:
            rows = await self.db.execute_raw(
                "SELECT DISTINCT type_num AS id, type_name AS name, is_published "
                "FROM crawl_progress WHERE type_name != '' AND is_published = 1"
            )
        else:
            rows = await self.db.execute_raw(
                "SELECT DISTINCT type_num AS id, type_name AS name, is_published "
                "FROM crawl_progress WHERE type_name != ''"
            )
        return [GenreRead(**r) for r in rows]

    async def list_regions(self) -> List[RegionRead]:
        """
        输入：无
        输出：全部地区列表（数量少，无分页，直接用 raw SQL 避免 page_size=999 伪分页）
        副作用：只读
        """
        rows = await self.db.execute_raw("SELECT id, name FROM regions ORDER BY id")
        return [RegionRead(**r) for r in rows]

    # ==================== 电影 CRUD ====================

    async def create_movie(self, data: MovieCreate, changed_by: str = "") -> MovieRead:
        """
        输入：MovieCreate（不含 id）, changed_by（操作人）
        输出：MovieRead（含 id + 时间戳）
        副作用：INSERT INTO movies + movies_history（同一事务）
        """
        values = data.model_dump()
        if values.get("release_date"):
            values["release_date"] = str(values["release_date"])

        async with self.db.transaction() as tx:
            mid = await tx.insert("movies", values, return_id=True)
            row = await tx.find_one("movies", {"id": mid})
            if row:
                await self._write_history("movies", {"movie_id": mid}, row, "create", changed_by, tx=tx)
        return MovieRead(**row) if row else None

    async def get_movie(self, movie_id: int) -> Optional[MovieRead]:
        """
        输入：movie_id
        输出：MovieRead 或 None
        副作用：只读
        """
        row = await self.db.find_one("movies", {"id": movie_id})
        return MovieRead(**row) if row else None

    async def get_movie_by_douban_id(self, douban_id: str) -> Optional[MovieRead]:
        """
        输入：豆瓣电影ID
        输出：MovieRead 或 None
        副作用：只读

        用于去重 — 同一部电影从不同 (type, interval) 组合爬入时不会再创建。
        """
        if not douban_id:
            return None
        row = await self.db.find_one("movies", {"douban_id": douban_id})
        return MovieRead(**row) if row else None

    async def update_movie(self, movie_id: int, data: MovieUpdate, changed_by: str = "") -> Optional[MovieRead]:
        """
        输入：movie_id + MovieUpdate（只更新非 None 字段）, changed_by
        输出：更新后的 MovieRead 或 None（不存在）
        副作用：UPDATE movies SET ... + movies_history
        """
        values = data.model_dump(exclude_none=True)
        if not values:
            return await self.get_movie(movie_id)

        if values.get("release_date"):
            values["release_date"] = str(values["release_date"])

        async with self.db.transaction() as tx:
            affected = await tx.update("movies", {"id": movie_id}, values)
            if affected == 0:
                return None
            row = await tx.find_one("movies", {"id": movie_id})
            if row:
                await self._write_history("movies", {"movie_id": movie_id}, row, "update", changed_by, tx=tx)
            return MovieRead(**row) if row else None

    async def delete_movie(self, movie_id: int, changed_by: str = "") -> int:
        """
        输入：movie_id, changed_by
        输出：删除行数（0 或 1）
        副作用：DELETE FROM movies + movies_history（同一事务：先记历史再删）
        """
        async with self.db.transaction() as tx:
            row = await tx.find_one("movies", {"id": movie_id})
            if row:
                await self._write_history("movies", {"movie_id": movie_id}, row, "delete", changed_by, tx=tx)
            return await tx.delete("movies", {"id": movie_id})

    # ==================== 上下架管理 ====================

    async def set_movie_published(self, movie_id: int, published: bool, changed_by: str = "") -> bool:
        """
        输入：movie_id + published + changed_by
        输出：True
        异常：ResourceNotFoundError — 电影不存在
        副作用：UPDATE movies + movies_history（同一事务）

        幂等：已上架再上架、已下架再下架 → 返回 True（不报错）。
        """
        async with self.db.transaction() as tx:
            affected = await tx.update(
                "movies", {"id": movie_id},
                {"is_published": 1 if published else 0}
            )
            if not affected:
                # affected=0 有两种可能：
                #   ① 电影不存在 → 应报 404
                #   ② 已是目标状态（已上架再上架） → 幂等成功
                row = await tx.find_one("movies", {"id": movie_id})
                if not row:
                    raise ResourceNotFoundError(f"电影不存在: {movie_id}")
                # 已为目标状态，幂等放行，不写入 history
                return True

            row = await tx.find_one("movies", {"id": movie_id})
            if row:
                await self._write_history("movies", {"movie_id": movie_id}, row, "update", changed_by, tx=tx)
        action = "上架" if published else "下架"
        logger.info(f"电影 {movie_id} 已{action}")
        return True

    async def set_type_published(self, type_num: int, interval_id: str, published: bool) -> bool:
        """
        输入：type_num + interval_id + published
        输出：是否操作成功
        副作用：UPDATE crawl_progress SET is_published = ?
        """
        affected = await self.db.update(
            "crawl_progress",
            {"type_num": type_num, "interval_id": interval_id},
            {"is_published": 1 if published else 0}
        )
        action = "上架" if published else "下架"
        logger.info(f"类型 type_num={type_num} interval={interval_id} 已{action}")
        return affected > 0

    async def list_movies(
        self,
        published_only: bool = False,
        page: int = 1,
        page_size: int = 100,
    ) -> Tuple[List[MovieRead], int]:
        """
        输入：published_only — True 时只返回上架电影, page/page_size 分页
        输出：(电影列表, 总数)
        副作用：只读
        """
        conditions = None
        if published_only:
            conditions = {"is_published": 1}
        rows, total = await self.db.find("movies", conditions=conditions, page=page, page_size=page_size)
        return [MovieRead(**r) for r in rows], total

    async def batch_list_movies(
        self,
        keyword: str = "",
        type_num: int = None,
        published: int = None,
        interval_ids: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        批量查询电影列表（分页+搜索+类型过滤+上下架过滤+评分区间过滤），附带评分和类型摘要。

        输入：
            keyword:      按片名模糊搜索（空字符串=不搜索）
            type_num:     豆瓣类型编号过滤（None=不过滤）
            published:    1=仅上架 0=仅下架 None=全部
            interval_ids: 评分区间过滤，逗号分隔 "100:90,90:80"
                          格式 "{max*10}:{min*10}"，如 100:90 表示 9.0~10.0
                          空字符串=不过滤，无效格式自动跳过（容错）
            page/page_size: 分页参数
        输出：
            {"items": [{id, title, release_year, poster_url, rating, genres}, ...],
             "total": int, "page": int, "page_size": int}

        N+1 防护：评分和类型在列表查询后做 2 次批量 IN 查询，不逐条查。
        副作用：只读
        """
        where_clauses = []
        params = []

        if published is not None:
            where_clauses.append("m.is_published = %s")
            params.append(published)

        if keyword:
            where_clauses.append("m.title LIKE %s")
            params.append(f"%{keyword}%")

        if type_num:
            where_clauses.append(
                "m.id IN (SELECT mg.movie_id FROM movie_genres mg WHERE mg.type_num = %s)"
            )
            params.append(type_num)

        if interval_ids:
            or_parts = []
            for part in interval_ids.split(","):
                part = part.strip()
                if ":" not in part:
                    continue
                try:
                    hi_str, lo_str = part.split(":")
                    hi = float(hi_str) / 10
                    lo = float(lo_str) / 10
                    or_parts.append("(r.average >= %s AND r.average <= %s)")
                    params.extend([lo, hi])
                except (ValueError, AttributeError):
                    continue
            if or_parts:
                where_clauses.append(
                    "m.id IN (SELECT r.movie_id FROM movie_ratings r WHERE "
                    + " OR ".join(or_parts) + ")"
                )

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        count_sql = f"SELECT COUNT(*) AS total FROM movies m{where_sql}"
        count_rows = await self.db.execute_raw(count_sql, tuple(params))
        total = count_rows[0]["total"] if count_rows else 0

        offset = (page - 1) * page_size
        data_sql = (
            f"SELECT m.id, m.douban_id, m.title, m.release_year, m.poster_url, m.is_published "
            f"FROM movies m{where_sql} "
            f"ORDER BY m.id DESC LIMIT %s OFFSET %s"
        )
        data_params = list(params) + [page_size, offset]
        rows = await self.db.execute_raw(data_sql, tuple(data_params))

        if not rows:
            return {"items": [], "total": total, "page": page, "page_size": page_size}

        movie_ids = [r["id"] for r in rows]
        placeholders = ", ".join(["%s"] * len(movie_ids))
        id_params = tuple(movie_ids)

        rating_map = {}
        rating_rows = await self.db.execute_raw(
            f"SELECT movie_id, average, count FROM movie_ratings WHERE movie_id IN ({placeholders})",
            id_params,
        )
        for r in rating_rows:
            rating_map[r["movie_id"]] = {"average": float(r["average"]), "count": r["count"]}

        genre_map = {}
        genre_rows = await self.db.execute_raw(
            f"""SELECT mg.movie_id, cp.type_name
                FROM movie_genres mg
                JOIN crawl_progress cp ON cp.type_num = mg.type_num
                WHERE mg.movie_id IN ({placeholders})
                GROUP BY mg.movie_id, cp.type_name""",
            id_params,
        )
        for g in genre_rows:
            mid = g["movie_id"]
            genre_map.setdefault(mid, []).append(g["type_name"])

        items = []
        for r in rows:
            mid = r["id"]
            item = dict(r)
            item["rating"] = rating_map.get(mid)
            item["genres"] = genre_map.get(mid, [])
            items.append(item)

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    # ==================== 评分管理 ====================

    async def set_rating(self, movie_id: int, data: RatingCreate) -> bool:
        """
        输入：movie_id + RatingCreate
        输出：是否成功
        副作用：INSERT ... ON DUPLICATE KEY UPDATE（幂等）

        设计理由：movie_ratings 是 1:1 表，不存在则创建，存在则更新。
                 用 raw SQL 比两次请求更高效。
        """
        distribution_str = None
        if data.distribution:
            distribution_str = json.dumps(data.distribution)

        await self.db.execute_raw(
            f"""INSERT INTO `movie_ratings` (movie_id, average, `count`, distribution)
               VALUES (%s, %s, %s, %s) AS new
               ON DUPLICATE KEY UPDATE
               average = new.average, `count` = new.`count`,
               distribution = new.distribution""",
            (movie_id, data.average, data.count, distribution_str)
        )
        logger.info(f"评分已设置: movie_id={movie_id}, average={data.average}")
        return True

    async def get_rating(self, movie_id: int) -> Optional[RatingRead]:
        """
        输入：movie_id
        输出：RatingRead 或 None
        副作用：只读
        """
        row = await self.db.find_one("movie_ratings", {"movie_id": movie_id})
        return RatingRead(**row) if row else None

    # ==================== 角色关联管理 ====================

    async def add_credit(self, movie_id: int, person_id: int, role_type: str, changed_by: str = "") -> int:
        """
        输入：movie_id + person_id + role_type("director"/"actor"), changed_by
        输出：插入数量（1）
        副作用：INSERT INTO movie_credits + movie_credits_history（同一事务）
        """
        async with self.db.transaction() as tx:
            result = await tx.execute_raw(
                "INSERT IGNORE INTO `movie_credits` (movie_id, person_id, role_type) "
                "VALUES (%s, %s, %s)",
                (movie_id, person_id, role_type),
            )
            await self._write_history(
                "movie_credits",
                {"movie_id": movie_id, "person_id": person_id},
                {"role_type": role_type},
                "create", changed_by, tx=tx,
            )
        return result

    async def remove_credit(self, movie_id: int, person_id: int, role_type: str, changed_by: str = "") -> int:
        """
        输入：movie_id + person_id + role_type, changed_by
        输出：删除行数
        副作用：DELETE FROM movie_credits + movie_credits_history（同一事务）
        """
        async with self.db.transaction() as tx:
            await self._write_history(
                "movie_credits",
                {"movie_id": movie_id, "person_id": person_id},
                {"role_type": role_type},
                "delete", changed_by, tx=tx,
            )
            return await tx.delete("movie_credits", {
                "movie_id": movie_id, "person_id": person_id,
                "role_type": role_type,
            })

    # ==================== 类型关联管理（type_num → crawl_progress）====================

    async def add_genre_to_movie(self, movie_id: int, type_num: int, changed_by: str = "") -> int:
        """
        输入：movie_id + type_num（豆瓣类型编号）, changed_by
        输出：插入数量
        副作用：INSERT INTO movie_genres + movie_genres_history（同一事务）
        """
        async with self.db.transaction() as tx:
            result = await tx.insert("movie_genres", {
                "movie_id": movie_id,
                "type_num": type_num,
            }, return_id=False)
            await self._write_history(
                "movie_genres",
                {"movie_id": movie_id, "type_num": type_num},
                {}, "create", changed_by, tx=tx,
            )
        return result

    async def remove_genre_from_movie(self, movie_id: int, type_num: int, changed_by: str = "") -> int:
        """
        输入：movie_id + type_num, changed_by
        输出：删除行数
        副作用：DELETE FROM movie_genres + movie_genres_history（同一事务）
        """
        async with self.db.transaction() as tx:
            await self._write_history(
                "movie_genres",
                {"movie_id": movie_id, "type_num": type_num},
                {}, "delete", changed_by, tx=tx,
            )
            return await tx.delete("movie_genres", {
                "movie_id": movie_id, "type_num": type_num,
            })

    # ==================== 地区关联管理 ====================

    async def add_region_to_movie(self, movie_id: int, region_id: int, changed_by: str = "") -> int:
        """
        输入：movie_id + region_id, changed_by
        输出：插入数量
        副作用：INSERT INTO movie_regions + movie_regions_history（同一事务）
        """
        async with self.db.transaction() as tx:
            result = await tx.insert("movie_regions", {
                "movie_id": movie_id,
                "region_id": region_id,
            }, return_id=False)
            await self._write_history(
                "movie_regions",
                {"movie_id": movie_id, "region_id": region_id},
                {}, "create", changed_by, tx=tx,
            )
        return result

    async def remove_region_from_movie(self, movie_id: int, region_id: int, changed_by: str = "") -> int:
        """
        输入：movie_id + region_id, changed_by
        输出：删除行数
        副作用：DELETE FROM movie_regions + movie_regions_history（同一事务）
        """
        async with self.db.transaction() as tx:
            await self._write_history(
                "movie_regions",
                {"movie_id": movie_id, "region_id": region_id},
                {}, "delete", changed_by, tx=tx,
            )
            return await tx.delete("movie_regions", {
                "movie_id": movie_id, "region_id": region_id,
            })

    # ==================== 复合查询（核心价值）====================

    async def get_movie_detail(self, movie_id: int) -> MovieDetail:
        """
        输入：movie_id
        输出：MovieDetail 聚合视图（movie + rating + directors + actors + crew + genres）
        异常：ResourceNotFoundError — 电影不存在
        """
        movie = await self.get_movie(movie_id)
        if not movie:
            raise ResourceNotFoundError(f"电影不存在: {movie_id}")

        rating = await self.get_rating(movie_id)

        credits = await self.db.execute_raw(
            """SELECT mc.movie_id, mc.person_id, mc.role_type, p.name AS person_name
               FROM movie_credits mc
               JOIN people p ON mc.person_id = p.id
               WHERE mc.movie_id = %s""",
            (movie_id,)
        )
        directors = [
            PeopleRead(id=c["person_id"], name=c["person_name"], created_at=None)
            for c in credits if c["role_type"] == "director"
        ]
        actors = [
            PeopleRead(id=c["person_id"], name=c["person_name"], created_at=None)
            for c in credits if c["role_type"] == "actor"
        ]
        # 扩展角色类型：writer / producer / art_director / music / other
        crew: dict = {}
        EXTRA_ROLES = ("writer", "producer", "art_director", "music", "other")
        for role in EXTRA_ROLES:
            entries = [
                PeopleRead(id=c["person_id"], name=c["person_name"], created_at=None)
                for c in credits if c["role_type"] == role
            ]
            if entries:
                crew[role] = entries

        # 类型来自 crawl_progress（genres 表已合并到此处 — 用 GROUP BY 去重）
        genre_rows = await self.db.execute_raw(
            """SELECT mg.type_num AS id, cp.type_name AS name
               FROM movie_genres mg
               JOIN crawl_progress cp ON cp.type_num = mg.type_num
               WHERE mg.movie_id = %s
               GROUP BY mg.type_num, cp.type_name""",
            (movie_id,)
        )
        genres = [GenreRead(**g) for g in genre_rows]

        # 地区来自 movie_regions JOIN regions
        region_rows = await self.db.execute_raw(
            """SELECT r.id, r.name
               FROM movie_regions mr
               JOIN regions r ON mr.region_id = r.id
               WHERE mr.movie_id = %s""",
            (movie_id,)
        )
        regions = [RegionRead(**r) for r in region_rows]

        # 查询AI总结和标签
        ai_summary_row = await self.db.execute_raw(
            """SELECT full_summary, review_tags
               FROM review_summary
               WHERE movie_id = %s AND status = 'done'
               LIMIT 1""",
            (movie_id,)
        )
        
        ai_summary = None
        ai_tags = []
        if ai_summary_row:
            ai_summary = ai_summary_row[0]["full_summary"]
            review_tags = ai_summary_row[0]["review_tags"]
            if review_tags:
                try:
                    ai_tags = json.loads(review_tags)
                except:
                    ai_tags = []

        return MovieDetail(
            movie=movie,
            rating=rating,
            directors=directors,
            actors=actors,
            crew=crew,
            genres=genres,
            regions=regions,
            ai_summary=ai_summary,
            ai_tags=ai_tags
        )

    async def has_director(self, movie_id: int) -> bool:
        """
        检查电影是否已有导演记录。

        输入：movie_id
        输出：True=已有导演, False=尚未有导演
        副作用：只读
        """
        rows = await self.db.execute_raw(
            "SELECT 1 FROM movie_credits WHERE movie_id = %s AND role_type = 'director' LIMIT 1",
            (movie_id,)
        )
        return len(rows) > 0

    async def get_credits_by_person(self, person_id: int) -> List[CreditRead]:
        """
        输入：person_id
        输出：此人参与的所有影视作品及其角色类型
        副作用：只读
        """
        rows = await self.db.execute_raw(
            """SELECT mc.movie_id, mc.person_id, mc.role_type, p.name AS person_name
               FROM movie_credits mc
               JOIN people p ON mc.person_id = p.id
               WHERE mc.person_id = %s""",
            (person_id,)
        )
        return [CreditRead(**r) for r in rows]

    async def get_movies_by_director(self, person_id: int) -> List[MovieRead]:
        """
        输入：person_id（导演）
        输出：此人导演的全部电影
        副作用：只读
        """
        rows = await self.db.execute_raw(
            """SELECT m.*
               FROM movies m
               JOIN movie_credits mc ON m.id = mc.movie_id
               WHERE mc.person_id = %s AND mc.role_type = 'director'""",
            (person_id,)
        )
        return [MovieRead(**r) for r in rows]

    async def search_movies(
        self,
        title_keyword: str = None,
        type_num: int = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MovieRead], int]:
        """
        输入：title_keyword(可选), type_num(可选, 豆瓣类型编号), 分页参数
        输出：(电影列表, 总数)
        副作用：只读
        """
        where_clauses = []
        params = []

        if title_keyword:
            where_clauses.append("m.title LIKE %s")
            params.append(f"%{title_keyword}%")

        if type_num:
            where_clauses.append(
                "m.id IN (SELECT mg.movie_id FROM movie_genres mg WHERE mg.type_num = %s)"
            )
            params.append(type_num)

        where_sql = ""
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)

        # COUNT 查询
        count_sql = f"SELECT COUNT(*) AS total FROM movies m{where_sql}"
        count_result = await self.db.execute_raw(count_sql, tuple(params))
        total = count_result[0]["total"] if count_result else 0

        # 数据查询
        offset = (page - 1) * page_size
        data_sql = (
            f"SELECT m.* FROM movies m{where_sql} "
            f"ORDER BY m.id DESC LIMIT %s OFFSET %s"
        )
        params.extend([page_size, offset])
        rows = await self.db.execute_raw(data_sql, tuple(params))
        movies = [MovieRead(**r) for r in rows]

        return movies, total

    # ==================== 统计查询 ====================

    async def get_genre_stats(self, published_only: bool = False) -> List[GenreStat]:
        """
        输入：published_only — True 时只统计上架电影
        输出：每个类型的电影数 + 平均评分
        副作用：只读
        """
        movie_filter = "AND m.is_published = 1" if published_only else ""
        rows = await self.db.execute_raw(
            f"""SELECT cp.type_num, cp.type_name AS genre_name,
                      COUNT(DISTINCT m.id) AS movie_count,
                      ROUND(AVG(mr.average), 1) AS avg_rating
               FROM crawl_progress cp
               JOIN movie_genres mg ON cp.type_num = mg.type_num
               JOIN movies m ON mg.movie_id = m.id {movie_filter}
               LEFT JOIN movie_ratings mr ON m.id = mr.movie_id
               WHERE cp.is_published = 1 AND cp.type_name != ''
               GROUP BY cp.type_num, cp.type_name
               ORDER BY movie_count DESC"""
        )
        return [GenreStat(**r) for r in rows]

    _INTERVAL_BUCKETS = [
        ("100:90", "9.0~10.0"),
        ("90:80",  "8.0~9.0"),
        ("80:70",  "7.0~8.0"),
        ("70:60",  "6.0~7.0"),
        ("60:50",  "5.0~6.0"),
        ("50:40",  "4.0~5.0"),
        ("40:30",  "3.0~4.0"),
        ("30:20",  "2.0~3.0"),
        ("20:10",  "1.0~2.0"),
        ("10:0",   "0~1.0"),
    ]

    async def filter_packet(self, published_only: bool = False) -> Dict[str, Any]:
        """
        过滤器数据包 — 类型列表 + 评分区间（各含影片数）。

        输入：
            published_only: True=只统计已上架电影（用户端）
                           False=统计全部（管理端）
        输出：
            {"types": [{type_num, type_name, movie_count}, ...],
             "intervals": [{interval_id, label, movie_count}, ...]}
        副作用：只读
        """
        movie_join_condition = "AND m.is_published = 1" if published_only else ""
        type_filter = "AND cp.is_published = 1" if published_only else ""

        type_rows = await self.db.execute_raw(
            f"""SELECT cp.type_num, cp.type_name,
                      COUNT(DISTINCT m.id) AS movie_count
               FROM crawl_progress cp
               LEFT JOIN movie_genres mg ON cp.type_num = mg.type_num
               LEFT JOIN movies m ON mg.movie_id = m.id {movie_join_condition}
               WHERE cp.type_name != '' {type_filter}
               GROUP BY cp.type_num, cp.type_name
               ORDER BY cp.type_num""",
            (),
        )

        interval_rows = await self.db.execute_raw(
            f"""SELECT
                 CASE
                   WHEN mr.average >= 9.0 THEN '100:90'
                   WHEN mr.average >= 8.0 THEN '90:80'
                   WHEN mr.average >= 7.0 THEN '80:70'
                   WHEN mr.average >= 6.0 THEN '70:60'
                   WHEN mr.average >= 5.0 THEN '60:50'
                   WHEN mr.average >= 4.0 THEN '50:40'
                   WHEN mr.average >= 3.0 THEN '40:30'
                   WHEN mr.average >= 2.0 THEN '30:20'
                   WHEN mr.average >= 1.0 THEN '20:10'
                   ELSE '10:0'
                 END AS interval_id,
                 COUNT(*) AS movie_count
               FROM movie_ratings mr
               JOIN movies m ON mr.movie_id = m.id {movie_join_condition}
               GROUP BY interval_id
               ORDER BY interval_id DESC""",
            (),
        )

        interval_map = {r["interval_id"]: r["movie_count"] for r in interval_rows}

        intervals = []
        for iid, label in self._INTERVAL_BUCKETS:
            intervals.append({
                "interval_id": iid,
                "label": label,
                "movie_count": interval_map.get(iid, 0),
            })

        return {
            "types": type_rows,
            "intervals": intervals,
        }
