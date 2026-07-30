"""DeepSeek API 客户端封装 (兼容 OpenAI SDK)"""

from typing import List, Dict, Optional
from openai import AsyncOpenAI
from nonebot import logger


class LLMClient:
    """LLM API 客户端，支持 DeepSeek 等 OpenAI 兼容接口"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 512,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    async def chat(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """发送消息到 LLM 并获取回复

        Args:
            messages: 格式 [{"role": "user", "content": "..."}, ...]
                      不含 system 消息（自动添加）

        Returns:
            LLM 回复文本，失败返回 None
        """
        # 构建完整消息列表：system prompt + 历史
        full_messages = [{"role": "system", "content": self.system_prompt}]
        full_messages.extend(messages)

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            content = response.choices[0].message.content
            if content is None:
                logger.warning("LLM 返回空内容")
                return None
            return content.strip()
        except Exception as e:
            logger.error(f"LLM API 调用失败: {e}")
            return None
