"""DeepSeek API 客户端封装 (兼容 OpenAI SDK)"""

from typing import Awaitable, Callable, Dict, List, Optional
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

    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[dict],
        tool_handler: Callable[[str, str], Awaitable[str]],
        max_rounds: int = 3,
    ) -> Optional[str]:
        """带 Function Calling 的对话：模型请求工具 → 执行 → 继续，最多 max_rounds 轮

        Args:
            messages: 对话消息（不含 system，自动添加）
            tools: OpenAI tools 定义列表
            tool_handler: 异步回调 (function_name, arguments_json) -> 结果文本
            max_rounds: 最多工具调用轮数（防死循环）

        Returns:
            最终回复文本，失败返回 None
        """
        full_messages: List[dict] = [
            {"role": "system", "content": self.system_prompt}
        ]
        full_messages.extend(messages)

        for _ in range(max_rounds):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    tools=tools,
                )
            except Exception as e:
                logger.error(f"LLM API 调用失败(tools): {e}")
                return None

            msg = response.choices[0].message
            if not msg.tool_calls:
                content = msg.content
                if content is None:
                    logger.warning("LLM 返回空内容(tools)")
                    return None
                return content.strip()

            # 把带 tool_calls 的 assistant 消息追加进上下文
            full_messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
                }
            )
            # 逐个执行工具
            for tc in msg.tool_calls:
                try:
                    result = await tool_handler(
                        tc.function.name, tc.function.arguments
                    )
                except Exception as e:
                    logger.error(
                        f"[工具] 执行失败 {tc.function.name}: {e}"
                    )
                    result = f"工具执行出错: {e}"
                full_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                )

        logger.warning("LLM 工具调用轮次超限")
        return None
