
"""
AI大模型客户端封装，支持DeepSeek、火山引擎豆包等主流大模型。
统一异步调用接口，内置重试、超时、错误处理机制。
"""
import json
import asyncio
import aiohttp
import logging
from typing import List, Dict, Optional
from config.settings import settings
from scripts.ai_prompts import (
    REVIEW_SUMMARY_SYSTEM_PROMPT,
    REVIEW_SUMMARY_USER_PROMPT_TPL,
    COMMENT_WORDCLOUD_SYSTEM_PROMPT,
    COMMENT_WORDCLOUD_USER_PROMPT_TPL,
)

logger = logging.getLogger(__name__)

class AIClientError(Exception):
    """AI调用异常基类"""
    pass

class BaseAIClient:
    """AI客户端抽象基类"""
    async def generate_review_summary(self, reviews: List[Dict]) -> Optional[Dict]:
        """
        基于长评列表生成综合总结、标签。
        返回结构：{
            "full_summary": "string, 300字以内综合总结",
            "tags": ["string", "剧情紧凑", "演技在线", ...]
        }
        """
        raise NotImplementedError

class DeepSeekAIClient(BaseAIClient):
    """DeepSeek大模型实现，适配V4 Flash版本"""
    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.endpoint = settings.DEEPSEEK_ENDPOINT
        self.timeout = 30  # 超时时间30秒
        self.max_retries = 3  # 最大重试次数
        self.model = "deepseek-v4-flash"  # V4 Flash模型

    async def generate_review_summary(self, reviews: List[Dict], max_chars_per_review: int = 1000) -> Optional[Dict]:
        """
        基于长评列表生成综合总结、标签。

        Args:
            reviews: 长评列表，每项含 content 和 useful_count
            max_chars_per_review: 每条长评最多取多少字，-1 表示不截断

        返回结构：{
            "full_summary": "string, 300字以内综合总结",
            "tags": ["string", "剧情紧凑", "演技在线", ...]
        }
        """
        if not reviews:
            return None

        # 拼接长评内容，控制总长度，避免超过上下文窗口
        review_contents = []
        total_length = 0
        for idx, r in enumerate(reviews, 1):
            raw = r.get('content', '')
            content = raw if max_chars_per_review == -1 else raw[:max_chars_per_review]
            useful = r.get('useful_count', 0)
            review_str = f'【长评{idx}（点赞{useful}）】{content}'
            review_contents.append(review_str)
            total_length += len(review_str)
            if total_length > 20000:  # 总长度控制在2万字以内
                break
        
        reviews_text = '\n\n'.join(review_contents)
        
        # 系统Prompt，明确输出格式要求
        system_prompt = REVIEW_SUMMARY_SYSTEM_PROMPT
        
        # 用户Prompt，填充影评内容
        user_prompt = REVIEW_SUMMARY_USER_PROMPT_TPL.format(reviews_text=reviews_text)

        # 重试机制
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {self.api_key}'
                    }
                    payload = {
                        'model': self.model,
                        'messages': [
                            {'role': 'system', 'content': system_prompt},
                            {'role': 'user', 'content': user_prompt}
                        ],
                        'temperature': 0.3,  # 低温度，保证输出稳定
                        'response_format': {'type': 'json_object'}  # 要求返回JSON格式
                    }
                    async with session.post(
                        self.endpoint,
                        headers=headers,
                        json=payload,
                        timeout=self.timeout
                    ) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            logger.error(f'DeepSeek API调用失败 status={resp.status}, error={error_text}')
                            await asyncio.sleep(2 ** attempt)  # 指数退避重试
                            continue
                        
                        result = await resp.json()
                        content = result['choices'][0]['message']['content']
                        parsed = json.loads(content)
                        
                        # 校验返回结构
                        if all(k in parsed for k in ['full_summary', 'tags']):
                            return parsed
                        else:
                            logger.warning(f'AI返回结构不完整：{parsed}')
                            await asyncio.sleep(1)
                            continue

            except Exception as e:
                logger.error(f'AI调用异常 attempt={attempt+1}: {e}', exc_info=True)
                await asyncio.sleep(2 ** attempt)
                continue
        
        logger.error('AI总结生成失败，已达到最大重试次数')
        return None

    async def generate_comment_wordcloud(self, comments: List[str]) -> Optional[List[Dict]]:
        """
        基于短评列表生成词云关键词。

        输入：
            comments: 短评纯文本列表，每条是一个用户的短评字符串
        输出：
            成功 → [{text: "演技炸裂", weight: 150}, ...]
            失败 → None
        副作用：
            调用 DeepSeek API，消耗 token
        """
        if not comments:
            return None

        comments_text = '\n'.join(f'· {c}' for c in comments)
        if len(comments_text) > 15000:
            comments_text = comments_text[:15000]

        system_prompt = COMMENT_WORDCLOUD_SYSTEM_PROMPT
        user_prompt = COMMENT_WORDCLOUD_USER_PROMPT_TPL.format(comments_text=comments_text)

        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {self.api_key}'
                    }
                    payload = {
                        'model': self.model,
                        'messages': [
                            {'role': 'system', 'content': system_prompt},
                            {'role': 'user', 'content': user_prompt}
                        ],
                        'temperature': 0.3,
                        'response_format': {'type': 'json_object'}
                    }
                    async with session.post(
                        self.endpoint,
                        headers=headers,
                        json=payload,
                        timeout=self.timeout
                    ) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            logger.error(f'DeepSeek wordcloud调用失败 status={resp.status}, error={error_text}')
                            await asyncio.sleep(2 ** attempt)
                            continue

                        result = await resp.json()
                        content = result['choices'][0]['message']['content']
                        parsed = json.loads(content)

                        words = parsed.get('words', [])
                        if isinstance(words, list) and len(words) > 0:
                            if all('text' in w and 'weight' in w for w in words):
                                return words
                        logger.warning(f'wordcloud AI返回结构不完整: {parsed}')
                        await asyncio.sleep(1)
                        continue

            except Exception as e:
                logger.error(f'AI wordcloud调用异常 attempt={attempt+1}: {e}', exc_info=True)
                await asyncio.sleep(2 ** attempt)
                continue

        logger.error('AI wordcloud生成失败，已达到最大重试次数')
        return None

# 模块级单例
_ai_client: Optional[BaseAIClient] = None

def get_ai_client() -> BaseAIClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = DeepSeekAIClient()
    return _ai_client
