
"""
movie Pydantic 模型单元测试
覆盖: MovieCreate, MovieUpdate, MovieRead, PeopleRead, GenreRead, RegionRead,
RatingCreate, RatingRead, CreditRead, MovieDetail, GenreStat
"""
import pytest
import json
from datetime import date, datetime
from decimal import Decimal
from pydantic import ValidationError
from models.movie_models import (
    MovieCreate,
    MovieUpdate,
    MovieRead,
    PeopleRead,
    GenreRead,
    RegionRead,
    RatingCreate,
    RatingRead,
    CreditRead,
    MovieDetail,
    GenreStat,
)


class TestMovieCreate:
    """电影创建入参验证"""

    def test_valid_full_input(self):
        """完整输入"""
        movie = MovieCreate(
            douban_id="1234567",
            title="肖申克的救赎",
            original_title="The Shawshank Redemption",
            release_year=1994,
            release_date=date(1994, 9, 10),
            duration=142,
            poster_url="https://example.com/poster.jpg",
            imdb_id="tt0111161",
        )
        assert movie.douban_id == "1234567"
        assert movie.title == "肖申克的救赎"
        assert movie.release_year == 1994

    def test_valid_minimal_input(self):
        """仅必填字段"""
        movie = MovieCreate(douban_id="1234567", title="肖申克的救赎")
        assert movie.original_title is None
        assert movie.release_year is None
        assert movie.release_date is None
        assert movie.duration is None
        assert movie.poster_url is None
        assert movie.imdb_id is None

    def test_douban_id_missing(self):
        """douban_id 必填缺失"""
        with pytest.raises(ValidationError):
            MovieCreate(title="肖申克的救赎")

    def test_title_missing(self):
        """title 必填缺失"""
        with pytest.raises(ValidationError):
            MovieCreate(douban_id="1234567")

    def test_title_too_long(self):
        """title 超过 512 字符"""
        with pytest.raises(ValidationError):
            MovieCreate(douban_id="1234567", title="a" * 513)

    def test_release_year_too_low(self):
        """release_year <0"""
        with pytest.raises(ValidationError):
            MovieCreate(
                douban_id="1234567",
                title="肖申克的救赎",
                release_year=-1,
            )

    def test_release_year_too_high(self):
        """release_year >2100"""
        with pytest.raises(ValidationError):
            MovieCreate(
                douban_id="1234567",
                title="肖申克的救赎",
                release_year=2101,
            )

    def test_duration_too_low(self):
        """duration <1"""
        with pytest.raises(ValidationError):
            MovieCreate(
                douban_id="1234567",
                title="肖申克的救赎",
                duration=0,
            )


class TestMovieUpdate:
    """电影更新入参验证"""

    def test_update_no_fields(self):
        """空更新 - 合法"""
        update = MovieUpdate()
        assert update.title is None
        assert update.original_title is None
        assert update.release_year is None
        assert update.release_date is None
        assert update.duration is None
        assert update.poster_url is None
        assert update.imdb_id is None
        assert update.is_published is None

    def test_update_single_field(self):
        """只更新一个字段"""
        update = MovieUpdate(title="新标题")
        assert update.title == "新标题"
        assert update.release_year is None

    def test_update_multiple_fields(self):
        """同时更新多个字段"""
        update = MovieUpdate(
            title="新标题",
            release_year=2024,
            is_published=False,
        )
        assert update.title == "新标题"
        assert update.release_year == 2024
        assert update.is_published is False

    def test_update_title_too_long(self):
        """更新的 title 超过 512 字符"""
        with pytest.raises(ValidationError):
            MovieUpdate(title="a" * 513)

    def test_update_release_year_invalid(self):
        """更新的 release_year 无效"""
        with pytest.raises(ValidationError):
            MovieUpdate(release_year=2101)


class TestMovieRead:
    """电影读出模型测试"""

    def test_construct_full(self):
        """完整数据构造"""
        movie = MovieRead(
            id=1,
            douban_id="1234567",
            title="肖申克的救赎",
            original_title="The Shawshank Redemption",
            release_year=1994,
            release_date=date(1994, 9, 10),
            duration=142,
            poster_url="https://example.com/poster.jpg",
            imdb_id="tt0111161",
            is_published=True,
            created_at=datetime(2024, 1, 1, 0, 0, 0),
            updated_at=datetime(2024, 2, 1, 0, 0, 0),
        )
        assert movie.id == 1
        assert movie.title == "肖申克的救赎"

    def test_construct_minimal(self):
        """最小数据构造"""
        movie = MovieRead(
            id=1,
            title="肖申克的救赎",
            is_published=True,
            created_at=datetime(2024, 1, 1, 0, 0, 0),
            updated_at=datetime(2024, 2, 1, 0, 0, 0),
        )
        assert movie.douban_id is None
        assert movie.release_year is None

    def test_model_dump(self):
        """序列化为字典"""
        movie = MovieRead(
            id=1,
            title="肖申克的救赎",
            is_published=True,
            created_at=datetime(2024, 1, 1, 0, 0, 0),
            updated_at=datetime(2024, 2, 1, 0, 0, 0),
        )
        dump = movie.model_dump()
        assert isinstance(dump, dict)
        assert dump["id"] == 1
        assert dump["title"] == "肖申克的救赎"


class TestRatingRead:
    """评分读出模型（含自定义解析！）"""

    def test_distribution_is_dict(self):
        """distribution 是 dict（原样保留）"""
        rating = RatingRead(
            movie_id=1,
            average=Decimal("9.7"),
            count=2800000,
            distribution={"5": Decimal("80"), "4": Decimal("15")},
            created_at=datetime(2024, 1, 1, 0, 0, 0),
            updated_at=datetime(2024, 2, 1, 0, 0, 0),
        )
        assert isinstance(rating.distribution, dict)
        assert rating.distribution["5"] == Decimal("80")

    def test_distribution_is_json_str(self):
        """distribution 是 JSON 字符串（自动解析）"""
        # 用 model_validate_json 测试
        rating = RatingRead.model_validate_json(
            json.dumps(
                {
                    "movie_id": 1,
                    "average": 9.7,
                    "count": 2800000,
                    "distribution": '{"5": 80, "4": 15}',
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-02-01T00:00:00",
                }
            )
        )
        assert isinstance(rating.distribution, dict)
        assert rating.distribution["5"] == 80
        assert rating.distribution["4"] == 15

    def test_distribution_is_none(self):
        """distribution 是 None"""
        rating = RatingRead(
            movie_id=1,
            average=Decimal("9.7"),
            count=2800000,
            distribution=None,
            created_at=datetime(2024, 1, 1, 0, 0, 0),
            updated_at=datetime(2024, 2, 1, 0, 0, 0),
        )
        assert rating.distribution is None


class TestRatingCreate:
    """评分创建/更新入参验证"""

    def test_valid_full(self):
        """完整输入"""
        rating = RatingCreate(
            average=Decimal("9.7"),
            count=2800000,
            distribution={"5": Decimal("80")},
        )
        assert rating.average == Decimal("9.7")
        assert rating.count == 2800000

    def test_average_invalid_too_low(self):
        """average <0"""
        with pytest.raises(ValidationError):
            RatingCreate(average=Decimal("-1"), count=1000)

    def test_average_invalid_too_high(self):
        """average >10"""
        with pytest.raises(ValidationError):
            RatingCreate(average=Decimal("10.1"), count=1000)

    def test_average_invalid_decimal_places(self):
        """average 超过 1 位小数"""
        with pytest.raises(ValidationError):
            RatingCreate(average=Decimal("9.77"), count=1000)

    def test_count_invalid_negative(self):
        """count <0"""
        with pytest.raises(ValidationError):
            RatingCreate(average=Decimal("9.7"), count=-100)

    def test_distribution_optional(self):
        """distribution 可选"""
        rating1 = RatingCreate(average=Decimal("9.7"), count=1000)
        assert rating1.distribution is None
        rating2 = RatingCreate(
            average=Decimal("9.7"), count=1000, distribution=None
        )
        assert rating2.distribution is None


class TestSimpleModels:
    """简单模型测试（PeopleRead/GenreRead/RegionRead/GenreStat/CreditRead）"""

    def test_people_read(self):
        """人员读出模型"""
        person = PeopleRead(
            id=1, name="弗兰克·德拉邦特", douban_id="1054394"
        )
        assert person.id == 1
        assert person.name == "弗兰克·德拉邦特"

    def test_genre_read(self):
        """类型读出模型"""
        genre = GenreRead(id=1, name="剧情", is_published=True)
        assert genre.id == 1
        assert genre.name == "剧情"

    def test_region_read(self):
        """地区读出模型"""
        region = RegionRead(id=1, name="美国")
        assert region.id == 1
        assert region.name == "美国"

    def test_genre_stat(self):
        """类型统计模型"""
        stat = GenreStat(
            type_num=1,
            genre_name="剧情",
            movie_count=100,
            avg_rating=Decimal("8.5"),
        )
        assert stat.type_num == 1
        assert stat.movie_count == 100

    def test_credit_read(self):
        """角色关联读出模型"""
        credit = CreditRead(
            movie_id=1, person_id=10, role_type="director", person_name="导演甲"
        )
        assert credit.movie_id == 1
        assert credit.role_type == "director"


class TestMovieDetail:
    """电影详情聚合视图测试"""

    def test_movie_detail_full(self):
        """完整的聚合数据"""
        movie = MovieRead(
            id=1,
            title="肖申克的救赎",
            is_published=True,
            created_at=datetime(2024, 1, 1, 0, 0, 0),
            updated_at=datetime(2024, 2, 1, 0, 0, 0),
        )
        rating = RatingRead(
            movie_id=1,
            average=Decimal("9.7"),
            count=2800000,
            created_at=datetime(2024, 1, 1, 0, 0, 0),
            updated_at=datetime(2024, 2, 1, 0, 0, 0),
        )
        detail = MovieDetail(
            movie=movie,
            rating=rating,
            directors=[PeopleRead(id=1, name="导演1")],
            actors=[PeopleRead(id=2, name="演员1")],
            crew={"writer": [PeopleRead(id=3, name="编剧1")]},
            genres=[GenreRead(id=1, name="剧情", is_published=True)],
            regions=[RegionRead(id=1, name="美国")],
        )
        assert detail.movie.title == "肖申克的救赎"
        assert len(detail.directors) == 1
        assert len(detail.genres) == 1
        assert len(detail.regions) == 1

    def test_movie_detail_empty_lists(self):
        """所有列表都是空的也合法"""
        movie = MovieRead(
            id=1,
            title="肖申克的救赎",
            is_published=True,
            created_at=datetime(2024, 1, 1, 0, 0, 0),
            updated_at=datetime(2024, 2, 1, 0, 0, 0),
        )
        detail = MovieDetail(movie=movie)
        assert detail.directors == []
        assert detail.actors == []
        assert detail.crew == {}
        assert detail.genres == []
        assert detail.regions == []
        assert detail.rating is None

