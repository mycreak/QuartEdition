"""
config/settings.py

应用级全局配置（非 DB 专用）。

v2 — 使用 pydantic-settings：
    - 自动从 .env 文件加载（优先级：环境变量 > .env > 默认值）
    - 类型校验（端口必须 int、JWT 算法必须 str 等）
    - IDE 友好的类型提示和自动补全

使用方式：
    from config.settings import settings

    jwt_secret = settings.JWT_SECRET
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

环境变量命名（在 .env 或系统环境变量中设置）：
    JWT_SECRET=your-production-secret
    JWT_ALGORITHM=HS256
    JWT_EXPIRE_SECONDS=604800
    BCRYPT_ROUNDS=12
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """QuartEdition 应用全局设置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── JWT ──
    JWT_SECRET: str = ""  # 空字符串 = 必须通过 .env 显式设置
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_SECONDS: int = 86400 * 7  # 7 天

    # ── Bcrypt ──
    BCRYPT_ROUNDS: int = 12

    # ── 服务 ──
    BIND: str = ""  # 绑定地址，空=用 hypercorn 默认 0.0.0.0:8000
    SNOWFLAKE_MACHINE_ID: int = Field(
        default=1,
        ge=0,
        le=1023,
        description="Snowflake 机器编号（0~1023），多实例部署时通过 .env 覆盖",
    )

    # ── AI 大模型 ──
    AI_PROVIDER: str = "deepseek"  # deepseek | doubao — 选择 AI 服务商
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_ENDPOINT: str = "https://api.deepseek.com/v1/chat/completions"
    DOUBAO_API_KEY: str = ""
    DOUBAO_ENDPOINT: str = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    DOUBAO_MODEL: str = "doubao-lite-32k"

    # ── MySQL ──
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "movie_db"

    # ── MongoDB ──
    MONGO_HOST: str = "localhost"
    MONGO_PORT: int = 27017
    MONGO_USER: str = ""
    MONGO_PASSWORD: str = ""
    MONGO_DATABASE: str = "movie_db"

    # ── 火山引擎 TOS 图床 ──
    TOS_ENDPOINT: str = "tos-cn-guangzhou.volces.com"
    TOS_REGION: str = "cn-guangzhou"
    TOS_ACCESS_KEY: str = ""  # 通过 .env 设置
    TOS_SECRET_KEY: str = ""  # 通过 .env 设置
    TOS_BUCKET: str = "movie-poster"
    TOS_SIGNED_URL_TTL: int = 86400
    POSTER_MAX_SIZE_MB: int = 5

    # ── 头像上传限制 ──
    AVATAR_MAX_SIZE_MB: int = 2
    AVATAR_ALLOWED_TYPES: str = "image/png,image/jpeg,image/webp"
    DEFAULT_AVATAR_URL: str = "https://movie-poster.tos-cn-guangzhou.volces.com/user-avatar/default-avatar.png"

    # ── 付费代理种子注入（启动时写入 proxy_pool，InfraView 管理的数据持久化到 proxies.json） ──
    # 格式: "host:port:user:pass,host2:port2:user2:pass2"
    # 示例: "1.2.3.4:8080:user:pass,5.6.7.8:9090:user2:pass2"
    PAID_PROXIES: str = ""


# 全局设置单例（模块导入即创建，自动读 .env）
settings = Settings()
