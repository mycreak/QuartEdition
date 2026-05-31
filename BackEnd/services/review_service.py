"""
services/review_service.py

评论管理业务层 — MongoDB reviews / comments 集合的唯一操作入口。

v2 — 通过 DatabaseLayerV2 统一中间层操作 MongoDB，不再直接调用 get_mongodb()。
     构造函数注入 DatabaseLayerV2，读写操作走 self.db.find/update。

职责：
    读: list_reviews / list_comments  → comment_status 参数控制上架/下架/用户删除过滤
    改: publish_*/unpublish_*         → 上下架（内部复用 _set_published）
    写: upsert_review / upsert_comment → 爬虫 upsert

输入：MongoDB _id（豆瓣评论 ID 字符串）
副作用：读/写 MongoDB 文档（经 DatabaseLayerV2）

⚠️ 字段语义速查：
    movie_id          int   MySQL movies.id（自增主键，用于跨表关联补中文片名）
    movie_douban_id   str   豆瓣平台电影 ID（如 "1292052"，用于构造豆瓣链接）
    _id | review_id | comment_id   str   豆瓣评论的 ID（MongoDB 文档主键）
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from db.database_v2 import DatabaseLayerV2
from utils.serializers import to_iso, CST

logger = logging.getLogger(__name__)

# MongoDB 文档投影字段说明：
#   movie_id          int   MySQL movies 表自增主键（用于跨表关联查中文片名）
#   movie_douban_id   str   豆瓣平台的电影 ID（如 "1292052"，用于构造豆瓣链接）
#   两者语义不同且类型不同，调用方需明确区分，禁止混传
_MONGO_PROJECTION_REVIEWS = {
    "_id": 1, "review_id": 1,
    "movie_id": 1,             "movie_douban_id": 1,
    "title": 1, "author": 1, "date": 1, "useful_count": 1,
    "text": 1, "crawled_at": 1, "removed_by": 1,
}
_MONGO_PROJECTION_COMMENTS = {
    "_id": 1, "comment_id": 1,
    "movie_id": 1,             "movie_douban_id": 1,
    "author": 1, "rating": 1, "text": 1, "date": 1,
    "useful_count": 1, "crawled_at": 1, "removed_by": 1,
}


class ReviewService:
    """
    评论管理业务层。

    输入：DatabaseLayerV2 实例（依赖注入）
    副作用：读写 MongoDB reviews / comments 集合
    """

    def __init__(self, db: DatabaseLayerV2):
        self.db = db

    # ═══════════════════════════════════════
    # 读
    # ═══════════════════════════════════════

    async def list_reviews(
        self,
        movie_ids: Optional[List[int]] = None,
        comment_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        长评列表。

        输入：
            movie_ids:     可选，按本地电影ID列表过滤（None=不过滤，空列表=无结果）
            comment_status: None=全部, "published"=已上架, "unpublished"=已下架(管理员), "removed"=用户删除
            page/page_size: 分页
        输出：(items, total)
        """
        query: Dict[str, Any] = {}
        if comment_status == "published":
            query["removed_by"] = {"$exists": False}
        elif comment_status == "unpublished":
            query["removed_by"] = "admin"
        elif comment_status == "removed":
            query["removed_by"] = "user"
        if movie_ids is not None:
            if len(movie_ids) == 1:
                query["movie_id"] = movie_ids[0]
            else:
                query["movie_id"] = {"$in": movie_ids}

        projection = dict(_MONGO_PROJECTION_REVIEWS)
        if comment_status == "published":
            projection.pop("removed_by", None)

        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            items, total = await self.db.find(
                table="reviews",
                conditions=query,
                projection=projection,
                sort=[("crawled_at", -1)],
                page=page,
                page_size=page_size,
            )
        finally:
            self.db._set_type(original_type)

        # 映射ID字段，兼容前端：长评把_id映射为review_id
        for item in items:
            if "review_id" not in item or not item["review_id"]:
                item["review_id"] = item.get("_id", "")
        await self._attach_movie_titles(items)
        return items, total

    async def get_comments_by_user_id(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        查询某用户发表的全部评论（用于个人中心）。

        输入: user_id, page, page_size
        输出: (items, total)，items 含 comment_id, movie_id, text, rating, date
        """
        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            items, total = await self.db.find(
                table="comments",
                conditions={"user_id": user_id, "removed_by": {"$exists": False}},
                projection={
                    "_id": 1, "movie_id": 1, "text": 1, "rating": 1, "date": 1,
                },
                sort=[("crawled_at", -1)],
                page=page,
                page_size=page_size,
            )
        finally:
            self.db._set_type(original_type)

        for item in items:
            if "comment_id" not in item or not item["comment_id"]:
                item["comment_id"] = item.get("_id", "")

        return items, total

    async def list_comments(
        self,
        movie_ids: Optional[List[int]] = None,
        rating: Optional[float] = None,
        comment_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        短评列表。

        输入：
            movie_ids:     可选，按本地电影ID列表过滤（None=不过滤，空列表=无结果）
            rating:        可选，按评分过滤
            comment_status: None=全部, "published"=已上架, "unpublished"=已下架(管理员), "removed"=用户删除
            page/page_size: 分页
        输出：(items, total)
        """
        query: Dict[str, Any] = {}
        if comment_status == "published":
            query["removed_by"] = {"$exists": False}
        elif comment_status == "unpublished":
            query["removed_by"] = "admin"
        elif comment_status == "removed":
            query["removed_by"] = "user"
        if movie_ids is not None:
            if len(movie_ids) == 1:
                query["movie_id"] = movie_ids[0]
            else:
                query["movie_id"] = {"$in": movie_ids}
        if rating:
            query["rating"] = rating

        projection = dict(_MONGO_PROJECTION_COMMENTS)
        if comment_status == "published":
            projection.pop("removed_by", None)

        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            items, total = await self.db.find(
                table="comments",
                conditions=query,
                projection=projection,
                sort=[("crawled_at", -1)],
                page=page,
                page_size=page_size,
            )
        finally:
            self.db._set_type(original_type)

        # 映射ID字段，兼容前端：短评把_id映射为comment_id
        for item in items:
            if "comment_id" not in item or not item["comment_id"]:
                item["comment_id"] = item.get("_id", "")
        await self._attach_movie_titles(items)
        return items, total

    async def get_top_reviews_by_movie_id(
        self,
        movie_id: int,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        获取指定电影的长评列表，按爬取顺序（即豆瓣默认的受欢迎排序）返回，用于AI总结。
        返回字段：content(长评正文), useful_count(点赞数)
        """
        if not movie_id:
            return []
        
        query = {"movie_id": movie_id, "removed_by": {"$exists": False}}
        projection = {
            "text": 1, "useful_count": 1, "_id": 0
        }

        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            items, _ = await self.db.find(
                table="reviews",
                conditions=query,
                projection=projection,
                sort=[("crawled_at", -1)],  # 按爬取顺序返回，和豆瓣默认展示顺序一致
                page=1,
                page_size=limit,
            )
            # 字段重命名，适配AI客户端期望的content字段
            for item in items:
                item["content"] = item.pop("text", "")
            return items
        finally:
            self.db._set_type(original_type)

    async def get_review_by_id(self, review_id: str) -> Optional[Dict[str, Any]]:
        """
        根据review_id获取单条长评，用于幂等判断。
        
        输入：review_id: 豆瓣长评ID
        输出：长评文档或None
        """
        if not review_id:
            return None
        
        query = {"_id": review_id}
        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            items, _ = await self.db.find(
                table="reviews",
                conditions=query,
                projection={},
                page=1,
                page_size=1,
            )
            return items[0] if items else None
        finally:
            self.db._set_type(original_type)

    async def get_comments_text_by_movie_id(
        self,
        movie_id: int,
        limit: int = 100,
    ) -> List[str]:
        """
        获取指定电影已上架短评的纯文本列表，供 AI 词云分析使用。

        输入：movie_id: 本地电影ID, limit: 最多取多少条（≤100，受 MongoDB 分页校验限制）
        输出：短评纯文本字符串列表
        副作用：无异常抛出 — 集合不存在/无数据/连接失败均返回空列表
        """
        if not movie_id:
            return []

        query = {"movie_id": movie_id, "removed_by": {"$exists": False}}
        projection = {"text": 1, "_id": 0}

        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            items, _ = await self.db.find(
                table="comments",
                conditions=query,
                projection=projection,
                sort=[("crawled_at", -1)],
                page=1,
                page_size=limit,
            )
            return [item.get("text", "") for item in items if item.get("text")]
        except Exception as e:
            logger.warning(
                "获取短评文本异常 movie_id=%s: %s，返回空列表降级处理",
                movie_id, e,
            )
            return []
        finally:
            self.db._set_type(original_type)

    async def get_distinct_movie_ids(self) -> List[int]:
        """
        获取所有有评论（长评或短评）的电影 ID 列表。

        输入：无
        输出：去重的 movie_id 列表
        副作用：MongoDB distinct 查询（reviews + comments 两集合）
        """
        ids = set()
        try:
            from db.mongodb import get_mongodb
            mongodb = get_mongodb()
            review_ids = await mongodb["reviews"].distinct("movie_id")
            ids.update(int(i) for i in review_ids if i is not None)
            comment_ids = await mongodb["comments"].distinct("movie_id")
            ids.update(int(i) for i in comment_ids if i is not None)
        except Exception as e:
            logger.warning("获取 distinct movie_id 失败: %s，返回空列表", e)
            return []
        return sorted(ids)

    async def count_comments_by_movie_id(self, movie_id: int) -> int:
        """
        获取指定电影的已上架短评总数，供 comment_crawl 顺延偏移计算。

        输入：movie_id: 本地电影ID
        输出：已上架短评数量（连接失败等异常返回 0）
        """
        if not movie_id:
            return 0

        query = {"movie_id": movie_id, "removed_by": {"$exists": False}}
        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            items, total = await self.db.find(
                table="comments",
                conditions=query,
                page=1,
                page_size=1,
            )
            logger.info(
                "[短评爬取 MongoDB计数] movie_id=%s is_published=True → total=%s",
                movie_id, total,
            )
            return total
        except Exception as e:
            logger.warning(
                "[短评爬取 MongoDB计数] 统计异常 movie_id=%s: %s，返回 0 降级处理",
                movie_id, e,
            )
            return 0
        finally:
            self.db._set_type(original_type)

    async def get_comment_movie_id(self, comment_id: str) -> Optional[int]:
        """
        根据短评ID查询 movie_id（供管理端删除词云缓存用）。

        输入：comment_id: 豆瓣短评ID (MongoDB _id)
        输出：movie_id 或 None
        """
        if not comment_id:
            return None
        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            doc = await self.db.find_one("comments", {"_id": comment_id})
            if doc and doc.get("movie_id"):
                return doc["movie_id"]
            return None
        finally:
            self.db._set_type(original_type)

    # ═══════════════════════════════════════
    # 改（上下架）
    # ═══════════════════════════════════════

    async def _set_published(
        self, collection_name: str, doc_id: str, published: bool
    ) -> bool:
        """
        内部复用：上下架单条评论。

        上架时：拒绝 removed_by='user' 的评论（用户主动删除不可逆转）
        下架时：写入 removed_by='admin'（与管理端"用户已删除"区分）

        输入：collection_name, doc_id (MongoDB _id), published
        输出：True
        异常：ResourceNotFoundError — 评论不存在或未变更
              ServiceError(403)    — 用户已删除的评论不可上架
        """
        from utils.errors import ResourceNotFoundError
        from utils.errors import ServiceError

        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            if published:
                doc = await self.db.find_one(
                    table=collection_name,
                    conditions={"_id": doc_id},
                )
                if doc and doc.get("removed_by") == "user":
                    label = "长评" if collection_name == "reviews" else "短评"
                    raise ServiceError(
                        f"该{label}已被用户主动删除，无法上架",
                        status_code=403,
                        code="USER_DELETED",
                    )

            if published:
                data = {
                    "$set": {"is_published": True},
                    "$unset": {"removed_by": ""}
                }
            else:
                data = {
                    "$set": {"is_published": False, "removed_by": "admin"}
                }

            modified = await self.db.update(
                table=collection_name,
                conditions={"_id": doc_id},
                data=data,
            )
            if modified == 0:
                label = "长评" if collection_name == "reviews" else "短评"
                raise ResourceNotFoundError(f"{label}不存在或未变更: {doc_id}")
            return True
        finally:
            self.db._set_type(original_type)

    async def publish_review(self, review_id: str) -> bool:
        return await self._set_published("reviews", review_id, True)

    async def unpublish_review(self, review_id: str) -> bool:
        return await self._set_published("reviews", review_id, False)

    async def publish_comment(self, comment_id: str) -> bool:
        return await self._set_published("comments", comment_id, True)

    async def unpublish_comment(self, comment_id: str) -> bool:
        return await self._set_published("comments", comment_id, False)

    # ═══════════════════════════════════════
    # 写（爬虫 upsert，从 storage.py 迁入）
    # ═══════════════════════════════════════

    async def upsert_review(
        self,
        review_id: str,
        movie_douban_id: str,
        review: Dict[str, Any],
        movie_id: Optional[int] = None,
    ) -> bool:
        """
        写入/更新单条长评。

        参数说明：
            review_id:       str  豆瓣长评 ID（MongoDB _id，如 "16234289"）
            movie_douban_id: str  豆瓣电影 ID（如 "1292052"）⚠️ 注意：不是 int movie_id
            review:          dict 解析后的正文数据
            movie_id:        int  MySQL movies.id（可选，用于跨表关联补中文片名）

        $set: 可变字段（title, author, text, ...）
        $setOnInsert: is_published=True, crawled_at（仅首次写入）
        并发安全: 带 $setOnInsert 的 upsert → insert 失败时回退纯 update

        输出：True=成功写入
        """
        # 运行时类型守卫 — 防止 movie_douban_id(str) 与 movie_id(int) 传反
        assert isinstance(movie_douban_id, str), \
            f"movie_douban_id 必须为 str（豆瓣电影 ID），实际: {type(movie_douban_id).__name__}"
        assert movie_id is None or isinstance(movie_id, int), \
            f"movie_id 必须为 int（MySQL 主键）或 None，实际: {type(movie_id).__name__}"

        set_doc = {
            "movie_douban_id": movie_douban_id,
            "movie_id": movie_id,
            "title": review.get("title", ""),
            "author": self._mask_author(review.get("author", "")),
            "date": review.get("date", ""),
            "votes": review.get("votes", ""),
            "html": review.get("html", ""),
            "text": review.get("text", ""),
            "useful_count": review.get("useful_count", 0),
        }
        set_on_insert = {
            "is_published": True,
            "crawled_at": to_iso(datetime.now(CST)),
        }

        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            modified = await self.db.update(
                "reviews", {"_id": review_id},
                {"$set": set_doc, "$setOnInsert": set_on_insert},
                upsert=True,
            )
            return modified >= 0
        except Exception as e:
            logger.warning(
                f"长评 upsert 带 $setOnInsert 失败（回退到纯 update）: "
                f"review_id={review_id} movie_douban_id={movie_douban_id} error={e}"
            )
            try:
                modified = await self.db.update(
                    "reviews", {"_id": review_id},
                    {"$set": set_doc},
                )
                return modified >= 0
            except Exception as e2:
                logger.error(
                    f"长评纯 update 也失败: "
                    f"review_id={review_id} movie_douban_id={movie_douban_id} error={e2}"
                )
                return False
        finally:
            self.db._set_type(original_type)

    async def upsert_comment(
        self,
        comment_id: str,
        movie_douban_id: str,
        comment: Dict[str, Any],
        movie_id: Optional[int] = None,
    ) -> bool:
        """
        写入/更新单条短评。

        参数说明：
            comment_id:      str  豆瓣短评 ID（MongoDB _id）
            movie_douban_id: str  豆瓣电影 ID（如 "1292052"）⚠️ 注意：不是 int movie_id
            comment:         dict 解析后的短评数据
            movie_id:        int  MySQL movies.id（可选，用于跨表关联补中文片名）

        输出：True=成功写入
        """
        # 运行时类型守卫 — 防止 movie_douban_id(str) 与 movie_id(int) 传反
        assert isinstance(movie_douban_id, str), \
            f"movie_douban_id 必须为 str（豆瓣电影 ID），实际: {type(movie_douban_id).__name__}"
        assert movie_id is None or isinstance(movie_id, int), \
            f"movie_id 必须为 int（MySQL 主键）或 None，实际: {type(movie_id).__name__}"

        set_doc = {
            "movie_douban_id": movie_douban_id,
            "movie_id": movie_id,
            "author": self._mask_author(comment.get("author", "")),
            "rating": comment.get("rating", 0.0),
            "text": comment.get("text", ""),
            "date": comment.get("date", ""),
            "useful_count": comment.get("useful_count", 0),
        }
        set_on_insert = {
            "is_published": True,
            "crawled_at": to_iso(datetime.now(CST)),
        }

        original_type = self.db._get_type()
        self.db.set_database("mongodb")
        try:
            modified = await self.db.update(
                "comments", {"_id": comment_id},
                {"$set": set_doc, "$setOnInsert": set_on_insert},
                upsert=True,
            )
            return modified >= 0
        except Exception as e:
            logger.warning(
                f"短评 upsert 带 $setOnInsert 失败（回退到纯 update）: "
                f"comment_id={comment_id} movie_douban_id={movie_douban_id} error={e}"
            )
            try:
                modified = await self.db.update(
                    "comments", {"_id": comment_id},
                    {"$set": set_doc},
                )
                return modified >= 0
            except Exception as e2:
                logger.error(
                    f"短评纯 update 也失败: "
                    f"comment_id={comment_id} movie_douban_id={movie_douban_id} error={e2}"
                )
                return False
        finally:
            self.db._set_type(original_type)

    # ═══════════════════════════════════════
    # 内部：movie_title 补充 + 作者去敏
    # ═══════════════════════════════════════

    async def _attach_movie_titles(self, items: List[Dict[str, Any]]) -> None:
        """
        批量查询 MySQL movies 表，为每条评论补充 movie_title。

        输入：items — MongoDB 返回的评论列表（每个含 movie_id）
        副作用：为每个 item 注入 movie_title 字段
        """
        movie_ids = {item.get("movie_id") for item in items if item.get("movie_id")}
        if not movie_ids:
            return

        raw = self.db.raw_mysql()
        placeholders = ",".join(["%s"] * len(movie_ids))
        rows = await raw.execute_query(
            f"SELECT id, title FROM movies WHERE id IN ({placeholders})",
            tuple(movie_ids),
        )
        title_map = {row["id"]: row["title"] for row in rows}

        for item in items:
            item["movie_title"] = title_map.get(item.get("movie_id"), "")

    @staticmethod
    def _mask_author(author: str) -> str:
        """
        豆瓣用户昵称去敏 — 保留前2字符 + 掩码。

        输入："影迷小王"
        输出："影迷**"
        """
        if not author:
            return ""
        if len(author) <= 2:
            return author[0] + "*"
        return author[:2] + "*" * min(len(author) - 2, 3)


_review_service: ReviewService = None


def _get_review_service() -> ReviewService:
    if _review_service is None:
        raise RuntimeError("ReviewService 未初始化，请先调用 init_review_service()")
    return _review_service


def init_review_service(db: DatabaseLayerV2) -> ReviewService:
    """
    初始化 ReviewService 单例。

    输入：DatabaseLayerV2 实例（已初始化）
    """
    global _review_service
    _review_service = ReviewService(db)
    logger.info("ReviewService 已初始化")
    return _review_service
