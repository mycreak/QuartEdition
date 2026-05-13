"""
config/db_config.py

MySQL、Redis、MongoDB 连接配置。

v3 — 延迟创建 + pydantic-settings：
    - 自动从 .env 文件加载（优先级：环境变量 > .env > 默认值）
    - 类型校验（端口自动转为 int）
    - 延迟创建：仅在首次调用 get_xxx_config() 时实例化，而非导入时
      解决"导入即执行"问题——调用方可在导入后设置 os.environ 再获取配置
    - 环境变量名通过 env_prefix 自动映射

使用方式：
    from config.db_config import get_mysql_config, get_redis_config, get_mongo_config

    cfg = get_mysql_config()
    host = cfg.host

安全性：
    - 生产环境必须通过环境变量或 .env 设置所有密码
    - password 字段无硬编码默认值，缺失时为空字符串
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class MySQLConfig(BaseSettings):
    """MySQL 连接配置 — 环境变量前缀 MYSQL_"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MYSQL_",
        extra="ignore",
    )

    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""  # 空串=无密码；RedisConfig 用 Optional[str]=None，两者语义等价但类型不一致，调用方统一用 cfg.password or None
    database: str = "movie_db"
    charset: str = "utf8mb4"
    minsize: int = 2
    maxsize: int = 10
    connect_timeout: int = 5


class RedisConfig(BaseSettings):
    """Redis 连接配置 — 环境变量前缀 REDIS_"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="REDIS_",
        extra="ignore",
    )

    host: str = "localhost"
    port: int = 6379
    password: Optional[str] = None  # None=无密码；MySQLConfig 用 str=""，语义等价，调用方统一用 cfg.password or None
    db: int = 0
    minsize: int = 2
    maxsize: int = 10
    socket_timeout: int = 5
    decode_responses: bool = True  # Redis 客户端默认自动解码 bytes→str
    delay_queue_key: str = "crawler:delay_queue"
    rate_limit_key: str = "crawler:last_task_time"


class MongoDBConfig(BaseSettings):
    """MongoDB 连接配置 — 环境变量前缀 MONGO_"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MONGO_",
        extra="ignore",
    )

    host: str = "localhost"
    port: int = 27017
    user: Optional[str] = None
    password: Optional[str] = None
    database: str = "movie_db"
    min_pool_size: int = 2
    max_pool_size: int = 10
    connect_timeout_ms: int = 5000
    collection_name: str = "test_collection"


# ── 延迟创建：调用 get_xxx_config() 时才实例化 ──

_mysql_config: Optional[MySQLConfig] = None
_redis_config: Optional[RedisConfig] = None
_mongo_config: Optional[MongoDBConfig] = None


def get_mysql_config() -> MySQLConfig:
    """获取 MySQL 配置单例（延迟创建，asyncio 单线程安全）。"""
    global _mysql_config
    if _mysql_config is None:
        _mysql_config = MySQLConfig()
    return _mysql_config


def get_redis_config() -> RedisConfig:
    """获取 Redis 配置单例（延迟创建，asyncio 单线程安全）。"""
    global _redis_config
    if _redis_config is None:
        _redis_config = RedisConfig()
    return _redis_config


def get_mongo_config() -> MongoDBConfig:
    """获取 MongoDB 配置单例（延迟创建）。"""
    global _mongo_config
    if _mongo_config is None:
        _mongo_config = MongoDBConfig()
    return _mongo_config
