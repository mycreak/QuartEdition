"""
AI 大模型客户端 — 归一化架构。

架构设计：
    BaseAIClient（抽象父类）
      ├─ 统一行为：重试循环 / 指数退避 / 错误快照 / 日志格式 / 状态码校验
      ├─ 抽象接口：子类只需实现 3 个方法，其余行为全部继承
      │   ├─ _build_headers()       → 认证头（Bearer / API-Key / HMAC）
      │   ├─ _build_payload(s, u)   → 请求体（OpenAI 格式 / 厂商私有格式）
      │   └─ _extract_content(resp) → 从响应中提取模型输出的纯文本
      │
      └─ 子类差异化：
          DeepSeekAIClient     — OpenAI 兼容格式，Bearer Token
          DoubaoAIClient       — 火山引擎豆包，API-Key + 私有 header（预置骨架）

使用方式：
    client = get_ai_client()               # 根据 settings.AI_PROVIDER 自动选择
    result = await client.generate_review_summary(reviews)
    words  = await client.generate_comment_wordcloud(comments)

依恋：
    config.settings — AI_PROVIDER / DEEPSEEK_API_KEY / DEEPSEEK_ENDPOINT / DOUBAO_*
"""

import json
import asyncio
import time
import logging
from typing import List, Dict, Optional, Tuple, Any

import aiohttp

from config.settings import settings

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Prompt 模板（所有 AI 服务商共用，不绑定特定厂商）
# ═══════════════════════════════════════════════════════════════

REVIEW_SUMMARY_SYSTEM_PROMPT = """你是一个专业的电影评论分析助手。用户会提供一部电影的若干条观众长评，请你：
1. 综合所有长评的核心观点，生成一段 300 字以内的整体总结。
2. 提取 5-10 个关键词标签，概括观众的主要评价维度（如"剧情紧凑""演技在线""画面精美""节奏拖沓"等）。

你必须以严格的 JSON 格式返回结果，不要添加任何额外文字：
{
  "full_summary": "300字以内的综合总结",
  "tags": ["标签1", "标签2", "标签3", ...]
}"""

REVIEW_SUMMARY_USER_PROMPT_TPL = """以下是某部电影的部分观众长评，请综合这些内容生成总结和标签：

{reviews_text}"""


COMMENT_WORDCLOUD_SYSTEM_PROMPT = """你是一个专业的电影短评分析助手。用户会提供一部电影的若干条观众短评，请你：
1. 从这些短评中提取 30-50 个最具代表性的评价关键词/词组。
2. 每个关键词需要给出权重（0-200），权重越高表示该关键词越能代表观众的整体评价倾向。
3. 优先提取包含具体情感色彩的评价类词组（如"演技炸裂""剧情拖沓"），而非普通形容词。
4. 避免提取无意义高频词（如"电影""不错""还行""好看"这类缺乏信息量的词）。

你必须以严格的 JSON 格式返回结果，不要添加任何额外文字：
{
  "words": [
    {"text": "演技炸裂", "weight": 150},
    {"text": "剧情拖沓", "weight": 120},
    {"text": "画面精美", "weight": 95}
  ]
}"""

COMMENT_WORDCLOUD_USER_PROMPT_TPL = """以下是某部电影的部分观众短评，请从中提取高频关键词和词组用于生成词云：

{comments_text}"""


# ═══════════════════════════════════════════════════════════════
# 抽象父类 — 归一化所有公共行为
# ═══════════════════════════════════════════════════════════════

class AIClientError(Exception):
    """AI 服务异常基类（网络 / 状态码 / 响应结构 / 超时统一由此透出）。"""
    pass


class BaseAIClient:
    """
    AI 客户端抽象父类。

    职责（父类统一实现）：
        1. 输入预处理（截断/拼接提示词）→ generate_review_summary / generate_comment_wordcloud
        2. 重试循环 + 指数退避 + 错误快照收集 → _call()
        3. 日志格式（统一标签 [AI服务:provider_name]）

    子类只需实现（3 个方法）：
        _build_headers()           → 构建 HTTP 认证头
        _build_payload(system, user)→ 构建请求体
        _extract_content(resp_dict)→ 从响应 JSON 中提取模型输出文本
    """

    # ── 子类必须覆盖的属性 ──
    provider_name: str = "unknown"
    endpoint: str = ""
    api_key: str = ""
    model: str = ""
    timeout: int = 30
    max_retries: int = 3
    _input_max_chars: int = 20000

    # ── 最后一次调用的快照（供上层读取，用于失败记录）──
    last_snapshot: Optional[Dict[str, Any]] = None

    # ═══════════════════════════════════════
    # 子类必须实现
    # ═══════════════════════════════════════

    def _build_headers(self) -> Dict[str, str]:
        """构建 HTTP 认证头（子类实现）。"""
        raise NotImplementedError

    def _build_payload(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """构建请求体（子类实现）。"""
        raise NotImplementedError

    def _extract_content(self, response_body: Dict[str, Any]) -> str:
        """从 API 响应 JSON 中提取模型输出的纯文本（子类实现）。"""
        raise NotImplementedError

    # ═══════════════════════════════════════
    # 模板方法 — 统一重试 / 快照 / 日志
    # ═══════════════════════════════════════

    async def _call(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        """
        统一 API 调用 — 重试循环 + 错误快照收集。

        输入：
            system_prompt: 系统提示词
            user_prompt:   用户提示词（已拼接业务数据）
        输出：
            (parsed_json | None, snapshot)
            - 成功 → (dict, {status: "ok", ...})
            - 失败 → (None, {status: "exhausted", last_status: 429, ...})
        副作用：
            调用 AI 服务，消耗 token
            snapshot 可用于 task_failures.snapshot 列
        """
        snapshot: Dict[str, Any] = {
            "provider": self.provider_name,
            "model": self.model,
            "endpoint": self.endpoint,
            "input_chars": len(user_prompt),
            "input_preview": user_prompt[:500] if user_prompt else "",
            "attempts": 0,
            "last_status": None,
            "last_error": None,
            "status": "unknown",
        }

        for attempt in range(self.max_retries):
            snapshot["attempts"] = attempt + 1
            try:
                async with aiohttp.ClientSession() as session:
                    headers = self._build_headers()
                    payload = self._build_payload(system_prompt, user_prompt)
                    async with session.post(
                        self.endpoint,
                        headers=headers,
                        json=payload,
                        timeout=self.timeout,
                    ) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            snapshot["last_status"] = resp.status
                            snapshot["last_error"] = error_text[:500]
                            snapshot["output_preview"] = error_text[:500]
                            logger.error(
                                f"[AI服务:{self.provider_name}] HTTP %s attempt=%s/%s detail=%s",
                                resp.status, attempt + 1, self.max_retries, error_text[:200],
                            )
                            await asyncio.sleep(2 ** attempt)
                            continue

                        result = await resp.json()
                        content = self._extract_content(result)
                        snapshot["last_status"] = 200
                        snapshot["status"] = "ok"
                        snapshot["output_chars"] = len(content)
                        snapshot["output_preview"] = content[:500]
                        return json.loads(content), snapshot

            except asyncio.CancelledError:
                raise
            except json.JSONDecodeError as e:
                snapshot["last_error"] = f"JSON解析失败: {e}"
                if 'content' in dir():
                    snapshot["output_preview"] = content[:500]
                logger.error(
                    f"[AI服务:{self.provider_name}] JSON解析失败 attempt=%s/%s content=%s",
                    attempt + 1, self.max_retries, content[:200] if 'content' in dir() else 'N/A',
                )
                await asyncio.sleep(1)
                continue
            except Exception as e:
                snapshot["last_error"] = str(e)
                logger.error(
                    f"[AI服务:{self.provider_name}] 调用异常 attempt=%s/%s: %s",
                    attempt + 1, self.max_retries, e,
                )
                await asyncio.sleep(2 ** attempt)
                continue

        snapshot["status"] = "exhausted"
        logger.error(
            f"[AI服务:{self.provider_name}] 调用失败，已达最大重试次数 "
            f"last_status=%s last_error=%s",
            snapshot["last_status"], snapshot["last_error"],
        )
        return None, snapshot

    # ═══════════════════════════════════════
    # 业务方法 — 所有子类共享
    # ═══════════════════════════════════════

    async def generate_review_summary(
        self,
        reviews: List[Dict],
        max_chars_per_review: int = 1000,
    ) -> Optional[Dict]:
        """
        基于长评列表生成综合总结 + 标签（所有服务商通用）。

        输入：
            reviews: [{"content": "..." , "useful_count": 5}, ...]
            max_chars_per_review: 单条截断长度，-1 不截断
        输出：
            {"full_summary": "...", "tags": ["...", ...]} | None
        """
        if not reviews:
            return None

        review_contents = []
        total_length = 0
        for idx, r in enumerate(reviews, 1):
            raw = r.get('content', '')
            content = raw if max_chars_per_review == -1 else raw[:max_chars_per_review]
            useful = r.get('useful_count', 0)
            review_str = f'【长评{idx}（点赞{useful}）】{content}'
            review_contents.append(review_str)
            total_length += len(review_str)
            if total_length > self._input_max_chars:
                break

        reviews_text = '\n\n'.join(review_contents)
        user_prompt = REVIEW_SUMMARY_USER_PROMPT_TPL.format(reviews_text=reviews_text)

        result, snapshot = await self._call(REVIEW_SUMMARY_SYSTEM_PROMPT, user_prompt)
        self.last_snapshot = snapshot

        if result and 'full_summary' in result and 'tags' in result:
            result['_ai_snapshot'] = snapshot
            return result

        logger.warning(
            f"[AI服务:{self.provider_name}] 总结生成返回结构不完整或失败: %s",
            result,
        )
        return None

    async def generate_comment_wordcloud(
        self,
        comments: List[str],
    ) -> Optional[List[Dict]]:
        """
        基于短评列表生成词云关键词（所有服务商通用）。

        输入：
            comments: 短评纯文本列表
        输出：
            [{"text": "演技炸裂", "weight": 150}, ...] | None
        """
        if not comments:
            return None

        comments_text = '\n'.join(f'· {c}' for c in comments)
        if len(comments_text) > self._input_max_chars:
            comments_text = comments_text[:self._input_max_chars]

        user_prompt = COMMENT_WORDCLOUD_USER_PROMPT_TPL.format(comments_text=comments_text)

        result, snapshot = await self._call(COMMENT_WORDCLOUD_SYSTEM_PROMPT, user_prompt)
        self.last_snapshot = snapshot

        if result:
            words = result.get('words', [])
            if isinstance(words, list) and len(words) > 0:
                if all('text' in w and 'weight' in w for w in words):
                    return words

        logger.warning(
            f"[AI服务:{self.provider_name}] 词云生成返回结构不完整或失败: %s",
            result,
        )
        return None


# ═══════════════════════════════════════════════════════════════
# 子类：DeepSeek（OpenAI 兼容格式）
# ═══════════════════════════════════════════════════════════════

class DeepSeekAIClient(BaseAIClient):
    """
    DeepSeek 大模型 — OpenAI 兼容 API。

    差异点（与父类相比）：
        - 认证：Bearer Token
        - 请求体：标准 OpenAI chat/completions 格式
        - 响应解析：choices[0].message.content
    """

    def __init__(self):
        self.provider_name = "deepseek"
        self.api_key = settings.DEEPSEEK_API_KEY
        self.endpoint = settings.DEEPSEEK_ENDPOINT
        self.model = "deepseek-v4-flash"
        self.timeout = 30
        self.max_retries = 3

    def _build_headers(self) -> Dict[str, str]:
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

    def _build_payload(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        return {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': 0.3,
            'response_format': {'type': 'json_object'},
        }

    def _extract_content(self, response_body: Dict[str, Any]) -> str:
        return response_body['choices'][0]['message']['content']


# ═══════════════════════════════════════════════════════════════
# 子类：豆包（火山引擎）— 预置骨架
# ═══════════════════════════════════════════════════════════════

class DoubaoAIClient(BaseAIClient):
    """
    火山引擎豆包大模型。

    差异点（与 DeepSeek 相比）：
        - 认证：API-Key → Authorization: Bearer {key}（兼容）
        - 域：通常为 ark.cn-beijing.volces.com
        - 模型：doubao-lite-32k 或 doubao-pro-128k

    接入后需要：
        1. 在 .env 中设置 DOUBAO_API_KEY + DOUBAO_ENDPOINT + DOUBAO_MODEL
        2. 确认火山引擎控制台已开通模型推理权限
    """

    def __init__(self):
        from config.settings import settings as s
        self.provider_name = "doubao"
        self.api_key = getattr(s, 'DOUBAO_API_KEY', '')
        self.endpoint = getattr(s, 'DOUBAO_ENDPOINT', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
        self.model = getattr(s, 'DOUBAO_MODEL', 'doubao-lite-32k')
        self.timeout = 30
        self.max_retries = 3

    def _build_headers(self) -> Dict[str, str]:
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

    def _build_payload(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        return {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': 0.3,
        }

    def _extract_content(self, response_body: Dict[str, Any]) -> str:
        return response_body['choices'][0]['message']['content']


# ═══════════════════════════════════════════════════════════════
# 工厂 + 单例
# ═══════════════════════════════════════════════════════════════

_ai_client: Optional[BaseAIClient] = None

_PROVIDER_REGISTRY: Dict[str, type] = {
    "deepseek": DeepSeekAIClient,
    "doubao": DoubaoAIClient,
}


def get_ai_client() -> BaseAIClient:
    """
    获取 AI 客户端单例。

    根据 settings.AI_PROVIDER（默认 "deepseek"）选择子类。
    """
    global _ai_client
    if _ai_client is None:
        provider = getattr(settings, 'AI_PROVIDER', 'deepseek') or 'deepseek'
        cls = _PROVIDER_REGISTRY.get(provider)
        if cls is None:
            logger.warning(
                "AI_PROVIDER=%s 不在注册表中，回退到 DeepSeek。已注册: %s",
                provider, list(_PROVIDER_REGISTRY.keys()),
            )
            cls = DeepSeekAIClient
        _ai_client = cls()
        logger.info(
            "AI 客户端已初始化: provider=%s model=%s endpoint=%s",
            _ai_client.provider_name, _ai_client.model, _ai_client.endpoint,
        )
    return _ai_client
