"""
models/user_action.py

用户行为 Pydantic 模型 — 请求/响应数据契约。

映射表: user_movie_status / user_action_log / user_tag_score
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ActionRequest(BaseModel):
    """POST /user/movies/<id>/<action> 请求体（大部分操作无需额外参数）"""
    review_text: Optional[str] = Field(None, description="评论正文（仅 review 操作需要）")
    rating: Optional[float] = Field(None, description="评分 0~5（仅 review 操作需要）")


class ActionResult(BaseModel):
    """操作成功的响应体"""
    action: str = Field(..., description="want_watch|watching|watched|favorite|comment")
    movie_id: int
    score_total: float = Field(..., description="本次操作总加分")
    tag_count: int = Field(..., description="本次操作触发的标签数量")


class MovieStatusResponse(BaseModel):
    """GET /user/movies/<id>/status 响应体"""
    movie_id: int
    want_watch: bool
    watching: bool
    watched: bool
    favorite: bool
    reviewed: bool


class TagItem(BaseModel):
    """单个标签画像项"""
    dimension: str
    label: str
    score: float
    confidence: Optional[float] = Field(None, description="AI 可信度，douban 来源为 null")
    source: str = Field(..., description="douban|ai")


class TagProfileResponse(BaseModel):
    """GET /user/profile/tags 响应体"""
    user_id: int
    tags: List[TagItem]
    total_tags: int
