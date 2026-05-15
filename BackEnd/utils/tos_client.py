"""
utils/tos_client.py

火山引擎 TOS 对象存储客户端。

职责：
    1. 上传文件（头像 / 海报）
    2. 从外部 URL 下载并转存到 TOS（海报场景核心方法）
    3. 生成对象访问 URL

设计原则：
    - mirror_from_url 失败不抛异常，返回 None（爬虫容忍图片下载失败）
    - 使用模块级单例，延迟初始化
    - aiohttp 异步下载外部图片，不阻塞 Worker

使用方式：
    from utils.tos_client import get_tos_client
    client = get_tos_client()
    url = await client.mirror_from_url("https://img3.doubanio.com/...", "covers/poster_xxx.webp")
"""

import logging
import hashlib
from typing import Optional

import aiohttp
from tos import TosClientV2

from config.settings import settings

logger = logging.getLogger(__name__)

_tos_client: Optional["TOSClient"] = None


def init_tos_client() -> "TOSClient":
    """
    初始化 TOSClient 单例（在 app.py 启动时调用）。

    副作用：设置模块级全局 _tos_client
    """
    global _tos_client
    _tos_client = TOSClient()
    logger.info("TOSClient 已初始化")
    return _tos_client


def get_tos_client() -> Optional["TOSClient"]:
    """
    获取 TOSClient 单例。

    返回：TOSClient 实例，未初始化则返回 None
    """
    return _tos_client


class TOSClient:
    """
    火山引擎 TOS 对象存储客户端。

    输入（从 settings 读取）：
        - TOS_ENDPOINT: 服务地址
        - TOS_REGION: 区域
        - TOS_ACCESS_KEY / TOS_SECRET_KEY: 认证凭证
        - TOS_BUCKET: 桶名
    """

    def __init__(self):
        self._client: Optional[TosClientV2] = None
        self._bucket: str = settings.TOS_BUCKET
        self._enabled: bool = bool(
            settings.TOS_ACCESS_KEY and settings.TOS_SECRET_KEY
        )

        if not self._enabled:
            logger.warning("TOS 凭证未配置（TOS_ACCESS_KEY / TOS_SECRET_KEY 为空），海报转存已禁用")
            return

        try:
            self._client = TosClientV2(
                settings.TOS_ACCESS_KEY,
                settings.TOS_SECRET_KEY,
                settings.TOS_ENDPOINT,
                settings.TOS_REGION,
            )
            logger.info(
                f"TOSClient 就绪: bucket={self._bucket} "
                f"endpoint={settings.TOS_ENDPOINT}"
            )
        except Exception as e:
            logger.error(f"TOSClient 初始化失败: {e}")
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self._client is not None

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "image/webp",
    ) -> Optional[str]:
        """
        上传字节流到 TOS。

        输入：
            key:          对象 Key（如 "covers/poster_1292052.webp"）
            data:         图片字节数据
            content_type: MIME 类型
        输出：
            成功 → 对象 URL（不含签名），失败 → None
        副作用：
            写入 TOS 对象存储
        """
        if not self.enabled:
            return None

        try:
            resp = await self._run_in_executor(
                self._client.put_object,
                self._bucket, key,
                content=data,
                content_type=content_type,
            )
            if resp.status_code == 200:
                url = f"https://{self._bucket}.{settings.TOS_ENDPOINT}/{key}"
                logger.info(f"TOS 上传成功: {key}")
                return url
            else:
                logger.warning(f"TOS 上传失败: key={key} status={resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"TOS 上传异常: key={key} err={e}")
            return None

    async def mirror_from_url(
        self,
        src_url: str,
        dest_key: str,
        max_size: int = 5 * 1024 * 1024,
    ) -> Optional[str]:
        """
        从外部 URL 下载图片 → 转存到 TOS。

        输入：
            src_url:  源图片 URL（如豆瓣 CDN 链接）
            dest_key: 目标对象 Key（如 "covers/poster_1292052.webp"）
            max_size: 最大图片大小（字节），默认 5MB
        输出：
            成功 → TOS 对象 URL，失败 → None（不抛异常）
        副作用：
            aiohttp GET 外部 URL → TOS put_object
        """
        if not self.enabled or not src_url:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    src_url,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                                      "Chrome/125.0.0.0 Safari/537.36",
                        "Referer": "https://movie.douban.com/",
                    },
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"TOS mirror 下载失败: src={src_url[:80]}... "
                            f"status={resp.status}"
                        )
                        return None

                    content_length = resp.content_length
                    if content_length and content_length > max_size:
                        logger.warning(
                            f"TOS mirror 图片过大: src={src_url[:80]}... "
                            f"size={content_length}/{max_size}"
                        )
                        return None

                    data = await resp.read()
                    if not data or len(data) < 100:
                        logger.warning(
                            f"TOS mirror 图片数据异常: src={src_url[:80]}... "
                            f"len={len(data)}"
                        )
                        return None

                    if len(data) > max_size:
                        logger.warning(
                            f"TOS mirror 图片超过限制: src={src_url[:80]}... "
                            f"size={len(data)}/{max_size}"
                        )
                        return None

            return await self.upload(dest_key, data)

        except aiohttp.ClientError as e:
            logger.warning(f"TOS mirror 网络异常: src={src_url[:80]}... err={e}")
            return None
        except Exception as e:
            logger.error(f"TOS mirror 未知异常: src={src_url[:80]}... err={e}")
            return None

    def sign_url(self, key: str, ttl: int = None) -> Optional[str]:
        """
        生成带签名的临时访问 URL。

        输入：
            key: 对象 Key（如 "avatars/avatar_xxx.webp"）
            ttl: 有效期秒数，默认取 settings.TOS_SIGNED_URL_TTL
        输出：
            带签名的临时 URL，失败/未启用 → None
        """
        if not self.enabled or not key:
            return None

        if ttl is None:
            ttl = settings.TOS_SIGNED_URL_TTL

        try:
            url = self._client.pre_signed_url(
                method="GET",
                bucket=self._bucket,
                key=key,
                expires=ttl,
            )
            return url
        except Exception as e:
            logger.warning(f"TOS sign_url 失败: key={key} err={e}")
            return None

    async def _run_in_executor(self, func, *args, **kwargs):
        """
        在线程池中执行同步的 TOS SDK 操作，避免阻塞事件循环。

        tos SDK 是同步的，通过 asyncio.to_thread（Python 3.9+）
        或 loop.run_in_executor 放到线程池执行。
        """
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
