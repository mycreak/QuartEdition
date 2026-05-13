"""
test_movie_service.py

MovieService 服务层集成测试。

测试标记：
  - @pytest.mark.integration
  - @pytest.mark.services
  - @pytest.mark.movie
"""

import pytest
import random
import time
from datetime import datetime
from typing import Dict, Any

from db.database_v2 import DatabaseLayerV2
from services.movie_service import MovieService
from models.movie_models import (
    MovieCreate, MovieUpdate, MovieRead, MovieDetail,
    RatingCreate, RatingRead, CreditCreate,
    MovieFilters,
)
from utils.errors import ResourceNotFoundError


# ==================== 测试辅助函数 ====================

def random_title() -> str:
    """生成随机电影标题"""
    timestamp = int(time.time() * 1000)
    suffix = random.randint(1000, 9999)
    return f"测试电影_{timestamp}_{suffix}"


def create_test_movie_data(
    title: str | None = None,
    douban_id: str | None = None,
    **kwargs
) -> MovieCreate:
    """创建测试电影数据"""
    if title is None:
        title = random_title()
    if douban_id is None:
        douban_id = f"test_douban_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    
    return MovieCreate(
        title=title,
        douban_id=douban_id,
        year=2024,
        duration=120,
        rating_douban=7.8,
        rating_imdb=7.5,
        summary="这是一部测试电影的简介",
        poster_url="https://example.com/poster.jpg",
        **kwargs,
    )


async def create_test_movie(
    movie_service: MovieService,
    title: str | None = None,
    douban_id: str | None = None,
    **kwargs
) -> MovieRead:
    """创建并返回测试电影"""
    movie_data = create_test_movie_data(title, douban_id, **kwargs)
    return await movie_service.create_movie(movie_data)


async def ensure_test_genres(db: DatabaseLayerV2):
    """确保有测试用的类型数据"""
    await db.execute_raw("""
        INSERT IGNORE INTO genres (id, name, name_cn, published) VALUES
        (1, 'drama', '剧情', 1),
        (2, 'comedy', '喜剧', 1),
        (3, 'action', '动作', 1),
        (4, 'thriller', '惊悚', 0)
    """)


async def ensure_test_regions(db: DatabaseLayerV2):
    """确保有测试用的地区数据"""
    await db.execute_raw("""
        INSERT IGNORE INTO regions (id, name, name_cn) VALUES
        (1, 'cn', '中国大陆'),
        (2, 'us', '美国'),
        (3, 'jp', '日本')
    """)


async def ensure_test_persons(db: DatabaseLayerV2):
    """确保有测试用的人员数据"""
    await db.execute_raw("""
        INSERT IGNORE INTO persons (id, name, name_cn, gender, douban_id, imdb_id) VALUES
        (1, 'Director One', '导演一', 1, 'director_1', 'nm0000001'),
        (2, 'Actor One', '演员一', 1, 'actor_1', 'nm0000002'),
        (3, 'Actor Two', '演员二', 0, 'actor_2', 'nm0000003')
    """)


# ==================== SC-Movie-01 字典表查询 ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.movie
class TestMovieServiceDictQueries:
    """字典表查询测试"""

    async def test_list_genres_all(self, db: DatabaseLayerV2):
        """TC-Movie-01-01: list_genres - 不限制 published，返回全部类型"""
        await ensure_test_genres(db)
        service = MovieService(db)
        
        genres = await service.list_genres(published_only=False)
        assert isinstance(genres, list)
        assert len(genres) >= 3  # drama, comedy, action, thriller
        
        genre_codes = [g.code for g in genres]
        assert "drama" in genre_codes
        assert "comedy" in genre_codes
        assert "action" in genre_codes
        assert "thriller" in genre_codes

    async def test_list_genres_published_only(self, db: DatabaseLayerV2):
        """TC-Movie-01-02: list_genres - published_only=True，只返回上架类型"""
        await ensure_test_genres(db)
        service = MovieService(db)
        
        genres = await service.list_genres(published_only=True)
        assert isinstance(genres, list)
        
        genre_codes = [g.code for g in genres]
        assert "drama" in genre_codes
        assert "comedy" in genre_codes
        assert "action" in genre_codes
        assert "thriller" not in genre_codes

    async def test_list_regions(self, db: DatabaseLayerV2):
        """TC-Movie-01-03: list_regions - 返回全部地区，按 id 排序"""
        await ensure_test_regions(db)
        service = MovieService(db)
        
        regions = await service.list_regions()
        assert isinstance(regions, list)
        assert len(regions) >= 3
        
        # 检查按 id 排序
        region_ids = [r.id for r in regions]
        assert region_ids == sorted(region_ids)
        
        region_codes = [r.code for r in regions]
        assert "cn" in region_codes
        assert "us" in region_codes
        assert "jp" in region_codes


# ==================== SC-Movie-02 电影 CRUD ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.movie
class TestMovieServiceCRUD:
    """电影 CRUD 测试"""

    async def test_create_movie_success(self, db: DatabaseLayerV2):
        """TC-Movie-02-01: create_movie - 正常创建，返回 MovieRead"""
        service = MovieService(db)
        movie_data = create_test_movie_data()
        
        movie = await service.create_movie(movie_data)
        
        assert movie is not None
        assert movie.id is not None
        assert movie.title == movie_data.title
        assert movie.douban_id == movie_data.douban_id

    async def test_create_movie_writes_history(self, db: DatabaseLayerV2):
        """TC-Movie-02-02: create_movie - 创建同时写入 movies_history 版本记录"""
        service = MovieService(db)
        movie_data = create_test_movie_data()
        
        movie = await service.create_movie(movie_data)
        
        # 检查历史记录
        histories = await db.query(
            "movies_history",
            filters={"movie_id": movie.id},
        )
        assert len(histories) == 1
        assert histories[0]["operation_type"] == "create"

    async def test_get_movie_exists(self, db: DatabaseLayerV2):
        """TC-Movie-02-03: get_movie - 存在的电影，返回 MovieRead"""
        service = MovieService(db)
        created_movie = await create_test_movie(service)
        
        movie = await service.get_movie(created_movie.id)
        assert movie is not None
        assert movie.id == created_movie.id
        assert movie.title == created_movie.title

    async def test_get_movie_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-02-04: get_movie - 不存在的电影，返回 None"""
        service = MovieService(db)
        
        movie = await service.get_movie(9999999)
        assert movie is None

    async def test_get_movie_by_douban_id_exists(self, db: DatabaseLayerV2):
        """TC-Movie-02-05: get_movie_by_douban_id - 存在的豆瓣ID，返回 MovieRead"""
        service = MovieService(db)
        douban_id = f"test_douban_exists_{int(time.time())}"
        await create_test_movie(service, douban_id=douban_id)
        
        movie = await service.get_movie_by_douban_id(douban_id)
        assert movie is not None
        assert movie.douban_id == douban_id

    async def test_get_movie_by_douban_id_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-02-06: get_movie_by_douban_id - 不存在的豆瓣ID，返回 None"""
        service = MovieService(db)
        
        movie = await service.get_movie_by_douban_id("nonexistent_douban_id")
        assert movie is None

    async def test_get_movie_by_douban_id_empty(self, db: DatabaseLayerV2):
        """TC-Movie-02-07: get_movie_by_douban_id - 空豆瓣ID，返回 None"""
        service = MovieService(db)
        
        movie = await service.get_movie_by_douban_id("")
        assert movie is None
        
        movie = await service.get_movie_by_douban_id(None)
        assert movie is None

    async def test_update_movie_success(self, db: DatabaseLayerV2):
        """TC-Movie-02-08: update_movie - 正常更新，返回更新后的 MovieRead"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        new_title = f"更新后的标题_{int(time.time())}"
        update_data = MovieUpdate(title=new_title, duration=150)
        
        updated = await service.update_movie(movie.id, update_data)
        
        assert updated is not None
        assert updated.title == new_title
        assert updated.duration == 150

    async def test_update_movie_writes_history(self, db: DatabaseLayerV2):
        """TC-Movie-02-09: update_movie - 更新同时写入 movies_history 版本记录"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        update_data = MovieUpdate(title="更新标题2")
        await service.update_movie(movie.id, update_data)
        
        # 检查历史记录
        histories = await db.query(
            "movies_history",
            filters={"movie_id": movie.id, "operation_type": "update"},
        )
        assert len(histories) >= 1

    async def test_update_movie_empty_data(self, db: DatabaseLayerV2):
        """TC-Movie-02-10: update_movie - 传入空数据（全None），原样返回"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        update_data = MovieUpdate()  # 全 None
        updated = await service.update_movie(movie.id, update_data)
        
        assert updated is not None
        assert updated.title == movie.title
        assert updated.duration == movie.duration

    async def test_update_movie_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-02-11: update_movie - 更新不存在的电影，返回 None"""
        service = MovieService(db)
        
        update_data = MovieUpdate(title="不存在")
        updated = await service.update_movie(9999999, update_data)
        assert updated is None

    async def test_delete_movie_exists(self, db: DatabaseLayerV2):
        """TC-Movie-02-12: delete_movie - 删除存在的电影，返回 1"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        deleted_count = await service.delete_movie(movie.id)
        assert deleted_count == 1
        
        # 验证已删除
        deleted = await service.get_movie(movie.id)
        assert deleted is None

    async def test_delete_movie_writes_history(self, db: DatabaseLayerV2):
        """TC-Movie-02-13: delete_movie - 删除前先写入 movies_history 版本记录"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        await service.delete_movie(movie.id)
        
        # 检查历史记录
        histories = await db.query(
            "movies_history",
            filters={"movie_id": movie.id, "operation_type": "delete"},
        )
        assert len(histories) == 1

    async def test_delete_movie_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-02-14: delete_movie - 删除不存在的电影，返回 0"""
        service = MovieService(db)
        
        deleted_count = await service.delete_movie(9999999)
        assert deleted_count == 0


# ==================== SC-Movie-03 上下架管理 ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.movie
class TestMovieServicePublish:
    """上下架管理测试"""

    async def test_set_movie_published_publish(self, db: DatabaseLayerV2):
        """TC-Movie-03-01: set_movie_published - 正常上架，返回 True"""
        service = MovieService(db)
        movie = await create_test_movie(service, published=False)
        
        result = await service.set_movie_published(movie.id, True)
        assert result is True
        
        updated = await service.get_movie(movie.id)
        assert updated.published is True

    async def test_set_movie_published_publish_idempotent(self, db: DatabaseLayerV2):
        """TC-Movie-03-02: set_movie_published - 已上架再上架（幂等），返回 True"""
        service = MovieService(db)
        movie = await create_test_movie(service, published=True)
        
        # 清理可能的旧历史记录
        await db.execute_raw("DELETE FROM movies_history WHERE movie_id = %s", [movie.id])
        
        result = await service.set_movie_published(movie.id, True)
        assert result is True
        
        updated = await service.get_movie(movie.id)
        assert updated.published is True

    async def test_set_movie_published_unpublish(self, db: DatabaseLayerV2):
        """TC-Movie-03-03: set_movie_published - 正常下架，返回 True"""
        service = MovieService(db)
        movie = await create_test_movie(service, published=True)
        
        result = await service.set_movie_published(movie.id, False)
        assert result is True
        
        updated = await service.get_movie(movie.id)
        assert updated.published is False

    async def test_set_movie_published_unpublish_idempotent(self, db: DatabaseLayerV2):
        """TC-Movie-03-04: set_movie_published - 已下架再下架（幂等），返回 True"""
        service = MovieService(db)
        movie = await create_test_movie(service, published=False)
        
        result = await service.set_movie_published(movie.id, False)
        assert result is True
        
        updated = await service.get_movie(movie.id)
        assert updated.published is False

    async def test_set_movie_published_writes_history_on_change(self, db: DatabaseLayerV2):
        """TC-Movie-03-05: set_movie_published - 状态变更时写入 history 记录"""
        service = MovieService(db)
        movie = await create_test_movie(service, published=False)
        
        # 清理旧历史
        await db.execute_raw("DELETE FROM movies_history WHERE movie_id = %s", [movie.id])
        
        await service.set_movie_published(movie.id, True)
        
        histories = await db.query(
            "movies_history",
            filters={"movie_id": movie.id, "operation_type": "publish"},
        )
        assert len(histories) >= 1

    async def test_set_movie_published_no_history_when_idempotent(self, db: DatabaseLayerV2):
        """TC-Movie-03-06: set_movie_published - 幂等时不写入 history 记录"""
        service = MovieService(db)
        movie = await create_test_movie(service, published=True)
        
        # 清理旧历史
        await db.execute_raw("DELETE FROM movies_history WHERE movie_id = %s", [movie.id])
        
        await service.set_movie_published(movie.id, True)
        
        histories = await db.query(
            "movies_history",
            filters={"movie_id": movie.id, "operation_type": "publish"},
        )
        assert len(histories) == 0

    async def test_set_movie_published_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-03-07: set_movie_published - 电影不存在，抛出 ResourceNotFoundError"""
        service = MovieService(db)
        
        with pytest.raises(ResourceNotFoundError):
            await service.set_movie_published(9999999, True)

    async def test_set_type_published_success(self, db: DatabaseLayerV2):
        """TC-Movie-03-08: set_type_published - 正常设置类型上下架，返回 True"""
        await ensure_test_genres(db)
        service = MovieService(db)
        
        result = await service.set_type_published(1, False)
        assert result is True
        
        genres = await service.list_genres(published_only=False)
        drama = next((g for g in genres if g.id == 1), None)
        assert drama.published is False

    async def test_set_type_published_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-03-09: set_type_published - 设置不存在的类型，返回 False"""
        service = MovieService(db)
        
        result = await service.set_type_published(9999, True)
        assert result is False


# ==================== SC-Movie-04 列表查询 ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.movie
class TestMovieServiceListQueries:
    """列表查询测试"""

    async def test_list_movies_all(self, db: DatabaseLayerV2):
        """TC-Movie-04-01: list_movies - 无过滤，返回全部电影"""
        service = MovieService(db)
        await create_test_movie(service)
        await create_test_movie(service)
        
        movies = await service.list_movies(published_only=False)
        assert isinstance(movies, list)
        assert len(movies) >= 2

    async def test_list_movies_published_only(self, db: DatabaseLayerV2):
        """TC-Movie-04-02: list_movies - published_only=True，只返回上架电影"""
        service = MovieService(db)
        movie1 = await create_test_movie(service, published=True)
        movie2 = await create_test_movie(service, published=False)
        
        movies = await service.list_movies(published_only=True)
        movie_ids = [m.id for m in movies]
        assert movie1.id in movie_ids
        assert movie2.id not in movie_ids

    async def test_list_movies_pagination(self, db: DatabaseLayerV2):
        """TC-Movie-04-03: list_movies - 分页，检查返回条数和 total"""
        service = MovieService(db)
        for i in range(5):
            await create_test_movie(service)
        
        movies, total = await service.list_movies(
            published_only=False,
            page=1,
            page_size=3,
        )
        assert len(movies) <= 3
        assert total >= 5

    async def test_batch_list_movies_all(self, db: DatabaseLayerV2):
        """TC-Movie-04-04: batch_list_movies - 无过滤，返回全部电影"""
        service = MovieService(db)
        await create_test_movie(service)
        
        result = await service.batch_list_movies()
        assert "items" in result
        assert "total" in result

    async def test_batch_list_movies_by_keyword(self, db: DatabaseLayerV2):
        """TC-Movie-04-05: batch_list_movies - 关键词搜索，按片名模糊匹配"""
        service = MovieService(db)
        keyword = f"unique_{int(time.time())}"
        await create_test_movie(service, title=f"{keyword} 电影 1")
        await create_test_movie(service, title=f"其他电影 {keyword}")
        await create_test_movie(service, title="完全无关电影")
        
        filters = MovieFilters(keyword=keyword)
        result = await service.batch_list_movies(filters=filters)
        
        assert result["total"] >= 2
        titles = [m["title"] for m in result["items"]]
        assert all(keyword in t for t in titles)

    async def test_batch_list_movies_by_genre(self, db: DatabaseLayerV2):
        """TC-Movie-04-06: batch_list_movies - 类型过滤，只返回指定类型电影"""
        await ensure_test_genres(db)
        service = MovieService(db)
        
        movie1 = await create_test_movie(service)
        movie2 = await create_test_movie(service)
        
        # 给 movie1 添加类型
        await service.add_genre_to_movie(movie1.id, 1)  # drama
        
        filters = MovieFilters(genres=[1])
        result = await service.batch_list_movies(filters=filters)
        
        movie_ids = [m["id"] for m in result["items"]]
        assert movie1.id in movie_ids
        assert movie2.id not in movie_ids

    async def test_batch_list_movies_published_1(self, db: DatabaseLayerV2):
        """TC-Movie-04-07: batch_list_movies - 上下架过滤（1/仅上架）"""
        service = MovieService(db)
        movie1 = await create_test_movie(service, published=True)
        movie2 = await create_test_movie(service, published=False)
        
        filters = MovieFilters(published_status=1)
        result = await service.batch_list_movies(filters=filters)
        
        movie_ids = [m["id"] for m in result["items"]]
        assert movie1.id in movie_ids
        assert movie2.id not in movie_ids

    async def test_batch_list_movies_published_0(self, db: DatabaseLayerV2):
        """TC-Movie-04-08: batch_list_movies - 上下架过滤（0/仅下架）"""
        service = MovieService(db)
        movie1 = await create_test_movie(service, published=True)
        movie2 = await create_test_movie(service, published=False)
        
        filters = MovieFilters(published_status=0)
        result = await service.batch_list_movies(filters=filters)
        
        movie_ids = [m["id"] for m in result["items"]]
        assert movie1.id not in movie_ids
        assert movie2.id in movie_ids

    async def test_batch_list_movies_by_rating_ranges(self, db: DatabaseLayerV2):
        """TC-Movie-04-09: batch_list_movies - 评分区间过滤（多个区间）"""
        service = MovieService(db)
        movie1 = await create_test_movie(service, rating_douban=7.5)  # 7-8
        movie2 = await create_test_movie(service, rating_douban=8.5)  # 8-9
        movie3 = await create_test_movie(service, rating_douban=5.5)  # 5-6
        
        filters = MovieFilters(rating_ranges=["7-8", "8-9"])
        result = await service.batch_list_movies(filters=filters)
        
        movie_ids = [m["id"] for m in result["items"]]
        assert movie1.id in movie_ids
        assert movie2.id in movie_ids
        assert movie3.id not in movie_ids

    async def test_batch_list_movies_invalid_rating_ignored(self, db: DatabaseLayerV2):
        """TC-Movie-04-10: batch_list_movies - 评分区间过滤（无效格式自动跳过）"""
        service = MovieService(db)
        await create_test_movie(service, rating_douban=7.5)
        
        filters = MovieFilters(rating_ranges=["invalid", "7-8"])
        result = await service.batch_list_movies(filters=filters)
        assert result["total"] >= 1

    async def test_batch_list_movies_combined_filters(self, db: DatabaseLayerV2):
        """TC-Movie-04-11: batch_list_movies - 组合条件过滤（搜索+类型+评分）"""
        await ensure_test_genres(db)
        service = MovieService(db)
        keyword = f"combo_{int(time.time())}"
        
        movie1 = await create_test_movie(service, title=f"{keyword} A", rating_douban=7.8)
        await service.add_genre_to_movie(movie1.id, 1)
        
        movie2 = await create_test_movie(service, title=f"{keyword} B", rating_douban=8.2)
        await service.add_genre_to_movie(movie2.id, 2)
        
        await create_test_movie(service, title=f"No {keyword}")
        
        filters = MovieFilters(
            keyword=keyword,
            genres=[1, 2],
            rating_ranges=["7-9"],
            published_status=1,
        )
        result = await service.batch_list_movies(filters=filters)
        
        assert result["total"] >= 2

    async def test_batch_list_movies_has_rating_and_genres(self, db: DatabaseLayerV2):
        """TC-Movie-04-12: batch_list_movies - 检查返回数据是否含 rating 和 genres"""
        await ensure_test_genres(db)
        service = MovieService(db)
        movie = await create_test_movie(service, rating_douban=7.8)
        await service.add_genre_to_movie(movie.id, 1)
        
        result = await service.batch_list_movies()
        first_movie = result["items"][0] if result["items"] else None
        
        assert first_movie is not None
        assert "rating" in first_movie
        assert "genres" in first_movie


# ==================== SC-Movie-05 评分管理 ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.movie
class TestMovieServiceRating:
    """评分管理测试"""

    async def test_set_rating_create(self, db: DatabaseLayerV2):
        """TC-Movie-05-01: set_rating - 首次设置，创建评分记录"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        rating_data = RatingCreate(
            movie_id=movie.id,
            source="douban",
            value=7.8,
            votes=1000,
        )
        
        rating = await service.set_rating(rating_data)
        assert rating is not None
        assert rating.movie_id == movie.id
        assert rating.source == "douban"
        assert rating.value == 7.8

    async def test_set_rating_update(self, db: DatabaseLayerV2):
        """TC-Movie-05-02: set_rating - 再次设置（幂等），更新现有记录"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        # 首次设置
        rating_data1 = RatingCreate(movie_id=movie.id, source="douban", value=7.8)
        await service.set_rating(rating_data1)
        
        # 再次设置
        rating_data2 = RatingCreate(movie_id=movie.id, source="douban", value=8.2, votes=2000)
        rating = await service.set_rating(rating_data2)
        
        assert rating.value == 8.2
        assert rating.votes == 2000

    async def test_set_rating_with_distribution(self, db: DatabaseLayerV2):
        """TC-Movie-05-03: set_rating - 含 distribution 数据，JSON 序列化"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        distribution = {
            "1": 10, "2": 20, "3": 30, "4": 40, "5": 50,
            "6": 100, "7": 200, "8": 300, "9": 200, "10": 100,
        }
        
        rating_data = RatingCreate(
            movie_id=movie.id,
            source="douban",
            value=7.5,
            votes=1000,
            distribution=distribution,
        )
        
        rating = await service.set_rating(rating_data)
        assert rating.distribution == distribution

    async def test_get_rating_exists(self, db: DatabaseLayerV2):
        """TC-Movie-05-04: get_rating - 存在评分，返回 RatingRead"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        rating_data = RatingCreate(movie_id=movie.id, source="douban", value=7.8)
        await service.set_rating(rating_data)
        
        rating = await service.get_rating(movie.id, "douban")
        assert rating is not None
        assert rating.value == 7.8

    async def test_get_rating_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-05-05: get_rating - 不存在评分，返回 None"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        rating = await service.get_rating(movie.id, "nonexistent_source")
        assert rating is None


# ==================== SC-Movie-06 角色关联管理 ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.movie
class TestMovieServiceCredits:
    """角色关联管理测试"""

    async def test_add_credit_director(self, db: DatabaseLayerV2):
        """TC-Movie-06-01: add_credit - 添加导演角色，返回 1"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        credit = CreditCreate(
            movie_id=movie.id,
            person_id=1,
            role_type="director",
            order_num=1,
        )
        
        count = await service.add_credit(credit)
        assert count == 1

    async def test_add_credit_actor(self, db: DatabaseLayerV2):
        """TC-Movie-06-02: add_credit - 添加演员角色，返回 1"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        credit = CreditCreate(
            movie_id=movie.id,
            person_id=2,
            role_type="actor",
            role_name="男主角",
            order_num=1,
        )
        
        count = await service.add_credit(credit)
        assert count == 1

    async def test_add_credit_duplicate(self, db: DatabaseLayerV2):
        """TC-Movie-06-03: add_credit - 重复添加同一角色（INSERT IGNORE），返回 0"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        credit = CreditCreate(
            movie_id=movie.id,
            person_id=1,
            role_type="director",
            order_num=1,
        )
        
        count1 = await service.add_credit(credit)
        count2 = await service.add_credit(credit)
        
        assert count1 == 1
        assert count2 == 0

    async def test_add_credit_writes_history(self, db: DatabaseLayerV2):
        """TC-Movie-06-04: add_credit - 添加时写入 movie_credits_history"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        credit = CreditCreate(
            movie_id=movie.id,
            person_id=1,
            role_type="director",
            order_num=1,
        )
        await service.add_credit(credit)
        
        histories = await db.query(
            "movie_credits_history",
            filters={"movie_id": movie.id, "operation_type": "add"},
        )
        assert len(histories) >= 1

    async def test_remove_credit_exists(self, db: DatabaseLayerV2):
        """TC-Movie-06-05: remove_credit - 删除存在的角色，返回 1"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        credit = CreditCreate(
            movie_id=movie.id,
            person_id=1,
            role_type="director",
            order_num=1,
        )
        await service.add_credit(credit)
        
        count = await service.remove_credit(movie.id, 1, "director")
        assert count == 1

    async def test_remove_credit_writes_history(self, db: DatabaseLayerV2):
        """TC-Movie-06-06: remove_credit - 删除前先写入 movie_credits_history"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        credit = CreditCreate(
            movie_id=movie.id,
            person_id=1,
            role_type="director",
            order_num=1,
        )
        await service.add_credit(credit)
        
        # 清理旧历史
        await db.execute_raw("DELETE FROM movie_credits_history WHERE movie_id = %s", [movie.id])
        
        await service.remove_credit(movie.id, 1, "director")
        
        histories = await db.query(
            "movie_credits_history",
            filters={"movie_id": movie.id, "operation_type": "remove"},
        )
        assert len(histories) >= 1

    async def test_remove_credit_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-06-07: remove_credit - 删除不存在的角色，返回 0"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        count = await service.remove_credit(movie.id, 9999, "director")
        assert count == 0


# ==================== SC-Movie-07 类型关联管理 ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.movie
class TestMovieServiceGenres:
    """类型关联管理测试"""

    async def test_add_genre_to_movie(self, db: DatabaseLayerV2):
        """TC-Movie-07-01: add_genre_to_movie - 添加类型，返回 1"""
        await ensure_test_genres(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        count = await service.add_genre_to_movie(movie.id, 1)
        assert count == 1

    async def test_add_genre_to_movie_writes_history(self, db: DatabaseLayerV2):
        """TC-Movie-07-02: add_genre_to_movie - 添加时写入 movie_genres_history"""
        await ensure_test_genres(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        await service.add_genre_to_movie(movie.id, 1)
        
        histories = await db.query(
            "movie_genres_history",
            filters={"movie_id": movie.id, "operation_type": "add"},
        )
        assert len(histories) >= 1

    async def test_remove_genre_from_movie_exists(self, db: DatabaseLayerV2):
        """TC-Movie-07-03: remove_genre_from_movie - 删除存在的类型，返回 1"""
        await ensure_test_genres(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        await service.add_genre_to_movie(movie.id, 1)
        count = await service.remove_genre_from_movie(movie.id, 1)
        assert count == 1

    async def test_remove_genre_from_movie_writes_history(self, db: DatabaseLayerV2):
        """TC-Movie-07-04: remove_genre_from_movie - 删除前先写入 movie_genres_history"""
        await ensure_test_genres(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        await service.add_genre_to_movie(movie.id, 1)
        
        # 清理旧历史
        await db.execute_raw("DELETE FROM movie_genres_history WHERE movie_id = %s", [movie.id])
        
        await service.remove_genre_from_movie(movie.id, 1)
        
        histories = await db.query(
            "movie_genres_history",
            filters={"movie_id": movie.id, "operation_type": "remove"},
        )
        assert len(histories) >= 1

    async def test_remove_genre_from_movie_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-07-05: remove_genre_from_movie - 删除不存在的类型，返回 0"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        count = await service.remove_genre_from_movie(movie.id, 9999)
        assert count == 0


# ==================== SC-Movie-08 地区关联管理 ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.movie
class TestMovieServiceRegions:
    """地区关联管理测试"""

    async def test_add_region_to_movie(self, db: DatabaseLayerV2):
        """TC-Movie-08-01: add_region_to_movie - 添加地区，返回 1"""
        await ensure_test_regions(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        count = await service.add_region_to_movie(movie.id, 1)
        assert count == 1

    async def test_add_region_to_movie_writes_history(self, db: DatabaseLayerV2):
        """TC-Movie-08-02: add_region_to_movie - 添加时写入 movie_regions_history"""
        await ensure_test_regions(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        await service.add_region_to_movie(movie.id, 1)
        
        histories = await db.query(
            "movie_regions_history",
            filters={"movie_id": movie.id, "operation_type": "add"},
        )
        assert len(histories) >= 1

    async def test_remove_region_from_movie_exists(self, db: DatabaseLayerV2):
        """TC-Movie-08-03: remove_region_from_movie - 删除存在的地区，返回 1"""
        await ensure_test_regions(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        await service.add_region_to_movie(movie.id, 1)
        count = await service.remove_region_from_movie(movie.id, 1)
        assert count == 1

    async def test_remove_region_from_movie_writes_history(self, db: DatabaseLayerV2):
        """TC-Movie-08-04: remove_region_from_movie - 删除前先写入 movie_regions_history"""
        await ensure_test_regions(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        await service.add_region_to_movie(movie.id, 1)
        
        # 清理旧历史
        await db.execute_raw("DELETE FROM movie_regions_history WHERE movie_id = %s", [movie.id])
        
        await service.remove_region_from_movie(movie.id, 1)
        
        histories = await db.query(
            "movie_regions_history",
            filters={"movie_id": movie.id, "operation_type": "remove"},
        )
        assert len(histories) >= 1

    async def test_remove_region_from_movie_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-08-05: remove_region_from_movie - 删除不存在的地区，返回 0"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        count = await service.remove_region_from_movie(movie.id, 9999)
        assert count == 0


# ==================== SC-Movie-09 复合查询 ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.movie
class TestMovieServiceComplexQueries:
    """复合查询测试"""

    async def test_get_movie_detail_exists(self, db: DatabaseLayerV2):
        """TC-Movie-09-01: get_movie_detail - 存在的电影，返回 MovieDetail（聚合数据完整）"""
        await ensure_test_genres(db)
        await ensure_test_regions(db)
        await ensure_test_persons(db)
        
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        detail = await service.get_movie_detail(movie.id)
        assert detail is not None
        assert detail.id == movie.id
        assert detail.title == movie.title

    async def test_get_movie_detail_not_exists(self, db: DatabaseLayerV2):
        """TC-Movie-09-02: get_movie_detail - 电影不存在，抛出 ResourceNotFoundError"""
        service = MovieService(db)
        
        with pytest.raises(ResourceNotFoundError):
            await service.get_movie_detail(9999999)

    async def test_get_movie_detail_has_directors(self, db: DatabaseLayerV2):
        """TC-Movie-09-03: get_movie_detail - 包含导演信息"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        credit = CreditCreate(movie_id=movie.id, person_id=1, role_type="director", order_num=1)
        await service.add_credit(credit)
        
        detail = await service.get_movie_detail(movie.id)
        assert "directors" in detail.model_dump()
        assert len(detail.directors) >= 1

    async def test_get_movie_detail_has_actors(self, db: DatabaseLayerV2):
        """TC-Movie-09-04: get_movie_detail - 包含演员信息"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        credit = CreditCreate(movie_id=movie.id, person_id=2, role_type="actor", order_num=1)
        await service.add_credit(credit)
        
        detail = await service.get_movie_detail(movie.id)
        assert "actors" in detail.model_dump()
        assert len(detail.actors) >= 1

    async def test_get_movie_detail_has_crew(self, db: DatabaseLayerV2):
        """TC-Movie-09-05: get_movie_detail - 包含 crew（writer/producer/art_director/music/other）"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        credit = CreditCreate(movie_id=movie.id, person_id=3, role_type="writer", order_num=1)
        await service.add_credit(credit)
        
        detail = await service.get_movie_detail(movie.id)
        assert "crew" in detail.model_dump()
        assert "writers" in detail.crew
        assert len(detail.crew.writers) >= 1

    async def test_get_movie_detail_has_genres(self, db: DatabaseLayerV2):
        """TC-Movie-09-06: get_movie_detail - 包含类型信息"""
        await ensure_test_genres(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        await service.add_genre_to_movie(movie.id, 1)
        
        detail = await service.get_movie_detail(movie.id)
        assert "genres" in detail.model_dump()
        assert len(detail.genres) >= 1

    async def test_get_movie_detail_has_regions(self, db: DatabaseLayerV2):
        """TC-Movie-09-07: get_movie_detail - 包含地区信息"""
        await ensure_test_regions(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        await service.add_region_to_movie(movie.id, 1)
        
        detail = await service.get_movie_detail(movie.id)
        assert "regions" in detail.model_dump()
        assert len(detail.regions) >= 1

    async def test_has_director_true(self, db: DatabaseLayerV2):
        """TC-Movie-09-08: has_director - 有导演，返回 True"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        credit = CreditCreate(movie_id=movie.id, person_id=1, role_type="director", order_num=1)
        await service.add_credit(credit)
        
        has_director = await service.has_director(movie.id)
        assert has_director is True

    async def test_has_director_false(self, db: DatabaseLayerV2):
        """TC-Movie-09-09: has_director - 无导演，返回 False"""
        service = MovieService(db)
        movie = await create_test_movie(service)
        
        has_director = await service.has_director(movie.id)
        assert has_director is False

    async def test_get_credits_by_person(self, db: DatabaseLayerV2):
        """TC-Movie-09-10: get_credits_by_person - 返回此人所有参演/导作品"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie1 = await create_test_movie(service)
        movie2 = await create_test_movie(service)
        
        credit1 = CreditCreate(movie_id=movie1.id, person_id=1, role_type="director", order_num=1)
        credit2 = CreditCreate(movie_id=movie2.id, person_id=1, role_type="actor", order_num=1)
        
        await service.add_credit(credit1)
        await service.add_credit(credit2)
        
        credits = await service.get_credits_by_person(1)
        assert len(credits) >= 2

    async def test_get_movies_by_director(self, db: DatabaseLayerV2):
        """TC-Movie-09-11: get_movies_by_director - 返回此人导演的所有电影"""
        await ensure_test_persons(db)
        service = MovieService(db)
        movie1 = await create_test_movie(service)
        movie2 = await create_test_movie(service)
        
        credit1 = CreditCreate(movie_id=movie1.id, person_id=1, role_type="director", order_num=1)
        credit2 = CreditCreate(movie_id=movie2.id, person_id=1, role_type="actor", order_num=1)
        
        await service.add_credit(credit1)
        await service.add_credit(credit2)
        
        movies = await service.get_movies_by_director(1)
        movie_ids = [m.id for m in movies]
        assert movie1.id in movie_ids
        assert movie2.id not in movie_ids

    async def test_search_movies_by_keyword(self, db: DatabaseLayerV2):
        """TC-Movie-09-12: search_movies - 按片名关键词搜索"""
        service = MovieService(db)
        keyword = f"search_{int(time.time())}"
        
        movie1 = await create_test_movie(service, title=f"{keyword} 测试电影")
        movie2 = await create_test_movie(service, title="其他电影")
        
        movies = await service.search_movies(keyword=keyword)
        movie_ids = [m.id for m in movies]
        assert movie1.id in movie_ids
        assert movie2.id not in movie_ids

    async def test_search_movies_by_genre(self, db: DatabaseLayerV2):
        """TC-Movie-09-13: search_movies - 按类型搜索"""
        await ensure_test_genres(db)
        service = MovieService(db)
        
        movie1 = await create_test_movie(service)
        movie2 = await create_test_movie(service)
        
        await service.add_genre_to_movie(movie1.id, 1)
        
        movies = await service.search_movies(genre_ids=[1])
        movie_ids = [m.id for m in movies]
        assert movie1.id in movie_ids
        assert movie2.id not in movie_ids

    async def test_search_movies_combined(self, db: DatabaseLayerV2):
        """TC-Movie-09-14: search_movies - 组合搜索（关键词+类型）"""
        await ensure_test_genres(db)
        service = MovieService(db)
        keyword = f"combo_{int(time.time())}"
        
        movie1 = await create_test_movie(service, title=f"{keyword} 电影")
        movie2 = await create_test_movie(service, title=f"{keyword} 另一个电影")
        
        await service.add_genre_to_movie(movie1.id, 1)
        
        movies = await service.search_movies(keyword=keyword, genre_ids=[1])
        movie_ids = [m.id for m in movies]
        assert movie1.id in movie_ids
        assert movie2.id not in movie_ids


# ==================== SC-Movie-10 统计查询 ====================

@pytest.mark.integration
@pytest.mark.services
@pytest.mark.movie
class TestMovieServiceStats:
    """统计查询测试"""

    async def test_get_genre_stats(self, db: DatabaseLayerV2):
        """TC-Movie-10-01: get_genre_stats - 返回各类型电影数和平均评分"""
        await ensure_test_genres(db)
        service = MovieService(db)
        
        movie1 = await create_test_movie(service, rating_douban=7.0)
        movie2 = await create_test_movie(service, rating_douban=8.0)
        
        await service.add_genre_to_movie(movie1.id, 1)
        await service.add_genre_to_movie(movie2.id, 1)
        
        stats = await service.get_genre_stats()
        assert isinstance(stats, list)
        
        drama_stat = next((s for s in stats if s.genre_id == 1), None)
        assert drama_stat is not None
        assert drama_stat.movie_count >= 2

    async def test_get_genre_stats_published_only(self, db: DatabaseLayerV2):
        """TC-Movie-10-02: get_genre_stats - published_only=True，只统计上架电影"""
        await ensure_test_genres(db)
        service = MovieService(db)
        
        movie1 = await create_test_movie(service, published=True, rating_douban=7.0)
        movie2 = await create_test_movie(service, published=False, rating_douban=8.0)
        
        await service.add_genre_to_movie(movie1.id, 1)
        await service.add_genre_to_movie(movie2.id, 1)
        
        stats = await service.get_genre_stats(published_only=True)
        drama_stat = next((s for s in stats if s.genre_id == 1), None)
        
        # 至少统计 movie1
        assert drama_stat.movie_count >= 1

    async def test_filter_packet(self, db: DatabaseLayerV2):
        """TC-Movie-10-03: filter_packet - 返回类型列表和评分区间列表（含影片数）"""
        await ensure_test_genres(db)
        service = MovieService(db)
        
        await create_test_movie(service, rating_douban=7.5)
        
        packet = await service.filter_packet()
        assert "genres" in packet
        assert "rating_ranges" in packet

    async def test_filter_packet_published_only(self, db: DatabaseLayerV2):
        """TC-Movie-10-04: filter_packet - published_only=True，只统计上架电影"""
        await ensure_test_genres(db)
        service = MovieService(db)
        
        await create_test_movie(service, published=True, rating_douban=7.5)
        await create_test_movie(service, published=False, rating_douban=8.5)
        
        packet = await service.filter_packet(published_only=True)
        assert "genres" in packet
        assert "rating_ranges" in packet

    async def test_filter_packet_has_10_rating_ranges(self, db: DatabaseLayerV2):
        """TC-Movie-10-05: filter_packet - 检查评分区间数据完整（10个区间）"""
        service = MovieService(db)
        
        packet = await service.filter_packet()
        rating_ranges = packet["rating_ranges"]
        
        assert len(rating_ranges) == 10
        range_names = [r["range"] for r in rating_ranges]
        assert "1-2" in range_names
        assert "9-10" in range_names
