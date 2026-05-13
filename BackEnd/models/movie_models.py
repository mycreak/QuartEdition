"""
models/movie_models.py

电影业务 Pydantic 数据模型（数据契约层）
覆盖 8 张 MySQL 表：movies / people / genres / regions
                    movie_ratings / movie_genres / movie_regions / movie_credits

命名规范：
    *Create → 写入入参（不含 id / created_at）
    *Read   → 读出结果（含 id / created_at）
    *Detail → 聚合视图（多表拼装）
"""

import json
from typing import Optional, Dict, List, Union, Literal
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════
# 枚举类型定义
# ═══════════════════════════════════════════

RoleType = Literal["director", "actor", "writer", "producer", "art_director", "music", "other"]


# ═══════════════════════════════════════════
# movies 表
# ═══════════════════════════════════════════

class MovieCreate(BaseModel):
    """创建电影 — 入参，不含 id 和 created_at"""
    douban_id: str = Field(..., max_length=32, description="豆瓣电影ID")
    title: str = Field(..., max_length=512, description="中文片名")
    original_title: Optional[str] = Field(None, max_length=512, description="原始片名")
    release_year: Optional[int] = Field(None, ge=0, le=2100, description="发行年份")
    release_date: Optional[date] = Field(None, description="发行日期")
    duration: Optional[int] = Field(None, ge=1, description="片长（分钟）")
    poster_url: Optional[str] = Field(None, max_length=2048, description="海报 URL")
    imdb_id: Optional[str] = Field(None, max_length=20, description="IMDb ID")


class MovieUpdate(BaseModel):
    """更新电影 — 所有字段可选，只更新传入的字段"""
    title: Optional[str] = Field(None, max_length=512)
    original_title: Optional[str] = Field(None, max_length=512)
    release_year: Optional[int] = Field(None, ge=0, le=2100)
    release_date: Optional[date] = None
    duration: Optional[int] = Field(None, ge=1)
    poster_url: Optional[str] = Field(None, max_length=2048)
    imdb_id: Optional[str] = Field(None, max_length=20)
    is_published: Optional[bool] = None


class MovieRead(BaseModel):
    """电影读出 — 含 id 和时间戳"""
    id: int          # MySQL 自增主键
    douban_id: Optional[str] = None    # 豆瓣平台 ID（爬虫写入后必存在）
    title: str
    original_title: Optional[str] = None
    release_year: Optional[int] = None
    release_date: Optional[date] = None
    duration: Optional[int] = None
    poster_url: Optional[str] = None
    imdb_id: Optional[str] = None
    is_published: bool = True
    created_at: datetime
    updated_at: datetime


# ═══════════════════════════════════════════
# people 表
# ═══════════════════════════════════════════

class PeopleRead(BaseModel):
    """人员读出 — created_at 可选，douban_id 可选（聚合查询中不一定取到）"""
    id: int
    name: str
    douban_id: Optional[str] = None
    created_at: Optional[datetime] = None


# ═══════════════════════════════════════════
# genres — 不再有独立表，类型字典由 crawl_progress 承载
# ═══════════════════════════════════════════

class GenreRead(BaseModel):
    """类型读出 — id 即豆瓣 type_num（与 GenreStat.type_num 同义），is_published 来自 crawl_progress"""
    id: int
    name: str
    is_published: bool


# ═══════════════════════════════════════════
# regions 字典表
# ═══════════════════════════════════════════

class RegionRead(BaseModel):
    """地区读出"""
    id: int
    name: str


# ═══════════════════════════════════════════
# movie_ratings 表
# ═══════════════════════════════════════════

class RatingRead(BaseModel):
    """评分读出 — distribution 自动从 JSON 字符串/已解析 dict 转换"""
    movie_id: int
    average: Decimal
    count: int
    distribution: Optional[Dict[str, float]] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("distribution", mode="before")
    @classmethod
    def parse_distribution(cls, v):
        """
        兼容两种输入：
          1. MySQL DictCursor 可能已自动解析为 dict
          2. 部分场景仍为 JSON 字符串
        """
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            return json.loads(v)
        return v


class RatingCreate(BaseModel):
    """创建/更新评分入参 — movie_id 由 service 层填充"""
    average: Decimal = Field(..., ge=0, le=10, max_digits=3, decimal_places=1)
    count: int = Field(..., ge=0)
    distribution: Optional[Dict[str, float]] = None


# ═══════════════════════════════════════════
# movie_credits 表（角色关联）
# ═══════════════════════════════════════════

class CreditRead(BaseModel):
    """
    角色关联读出 — 含人员姓名（JOIN 后结果）。

    字段等价：
        CreditRead.person_id   ←→  PeopleRead.id  （同一概念：人员主键）
        CreditRead.person_name ←→  PeopleRead.name （同一概念：人员姓名）
    展平设计的原因是 SQL JOIN 后字段名自然为 person_id/person_name。
    """
    movie_id: int
    person_id: int
    role_type: str  # "director" | "actor"
    person_name: Optional[str] = None  # JOIN people 后填充


# ═══════════════════════════════════════════
# MovieDetail — 聚合视图
# ═══════════════════════════════════════════

class MovieDetail(BaseModel):
    """
    电影详情聚合视图，拼装自多表：
      movies + movie_ratings + movie_credits(JOIN people) + movie_genres(JOIN genres)
    """
    movie: MovieRead
    rating: Optional[RatingRead] = None
    directors: List[PeopleRead] = Field(default_factory=list)
    actors: List[PeopleRead] = Field(default_factory=list)
    crew: Dict[str, List[PeopleRead]] = Field(default_factory=dict)  # role_type → 人员列表（含 writer/producer/art_director/music/other）
    genres: List[GenreRead] = Field(default_factory=list)
    regions: List[RegionRead] = Field(default_factory=list)
    # 新增AI总结相关字段
    ai_summary: Optional[str] = None
    ai_tags: List[str] = Field(default_factory=list)


# ═══════════════════════════════════════════
# 统计用模型
# ═══════════════════════════════════════════

class GenreStat(BaseModel):
    """类型统计 — type_num 与 GenreRead.id 同义（豆瓣类型编号）"""
    type_num: int
    genre_name: str
    movie_count: int
    avg_rating: Optional[Decimal] = None
