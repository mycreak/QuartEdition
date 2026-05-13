"""
config/crawler_config.py

爬虫行为配置 — 翻页深度、限速、重试等运行时参数。

设计原则：
    与 puller_config / monitor_config 保持一致风格（全部 pydantic-settings）。
    环境变量前缀 CRAWLER_，可通过 .env 覆盖。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class CrawlerConfig(BaseSettings):
    """
    爬虫运行时配置。

    分页控制：
        review_list_pages: 长评摘要每任务最大翻页数（默认 3 页 ≈ 60 条）
        comment_list_pages: 短评每任务最大翻页数（默认 5 页 ≈ 100 条）

    长评爬取控制（v3 增强版）：
        review_crawl_max_new: 每次 review_crawl 最多取的新评论数（默认 5 条，顺延偏移）
        review_crawl_pre_sleep: 翻页前等待秒数（默认 45s，反反爬）长评正文控制：
        review_body_between_sleep: 已废弃（v4 改单条模式后不再使用，间隔由 worker_rest 控制）
        review_body_page_wait: 等待动态内容加载（默认 15s）
        review_body_verify_wait: 点击验证按钮后等待（默认 45s）
        review_body_content_wait: 等待内容完全加载（默认 5s）

    AI总结控制：
        ai_summary_min_reviews: 触发AI总结的最小长评数（默认 5 条）
        ai_summary_max_reviews: AI总结最多使用长评数，按useful_count取topN（默认 10 条）
        ai_summary_max_chars: 每条长评截取字数（默认 800 字）

    并发控制：
        api_concurrency: 通用 API 并发上限（默认 5）
        browser_concurrency: BrowserFetcher 并发上限（默认 2）

    子任务抖动窗口：
        subtask_jitter_seconds: movie_crawl 子任务 ZSET score 随机偏移窗口（默认 5s）
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CRAWLER_",
        extra="ignore",
    )

    review_list_pages: int = 3
    comment_list_pages: int = 5
    page_size: int = 20
    review_body_max_per_task: int = 20
    api_concurrency: int = 5
    browser_concurrency: int = 2
    subtask_jitter_seconds: float = 5.0

    review_crawl_max_new: int = 5
    review_crawl_pre_sleep: float = 45.0
    review_body_between_sleep: float = 120.0
    review_body_page_wait: float = 15.0
    review_body_verify_wait: float = 45.0
    review_body_content_wait: float = 5.0

    ai_summary_min_reviews: int = 5
    ai_summary_max_reviews: int = 10
    ai_summary_max_chars: int = 800


# 模块级默认配置 — 自动从 .env 读取 CRAWLER_* 环境变量
crawler_config = CrawlerConfig()
