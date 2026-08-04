"""DeepSeek API 客户端封装 (兼容 OpenAI SDK)

针对不稳定网络（校园网/弱网）做了加固：
- 显式超时：连接 10s，读写 30s（可配置），避免 SDK 默认 connect=5s 在慢速连接上过早失败
- 网络/超时类异常自动重试（指数退避），扛过瞬时抖动
- 每轮调用用 asyncio 超时兜底，避免无限挂起
"""

import asyncio
import time
from typing import Awaitable, Callable, Dict, List, Optional

import httpx
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError
from nonebot import logger

# 会被自动重试的网络/超时类异常
_RETRYABLE_EXC = (
    APITimeoutError,
    APIConnectionError,
    httpx.TimeoutException,
    httpx.TransportError,
    asyncio.TimeoutError,
)


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
        timeout: float = 30.0,
        max_retries: int = 2,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(
                connect=10.0,
                read=timeout,
                write=timeout,
                pool=timeout,
            ),
            # 关闭 SDK 内部重试，统一由本类控制，行为更可预测
            max_retries=0,
        )

    # ── 单次调用（带超时 + 网络重试）──

    async def _create(self, messages: List[dict], tools: Optional[List[dict]] = None):
        """单次调用：网络/超时异常自动重试，成功返回响应，重试耗尽则抛异常"""
        kwargs = {"tools": tools} if tools else {}
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            start = time.monotonic()
            try:
                return await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        **kwargs,
                    ),
                    timeout=self.timeout,
                )
            except _RETRYABLE_EXC as e:
                last_exc = e
                elapsed = time.monotonic() - start
                logger.warning(
                    f"[LLM] 网络/超时异常(第{attempt + 1}/{self.max_retries + 1}次) "
                    f"{type(e).__name__} 耗时{elapsed:.1f}s: {e}"
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(min(1.0 * (2 ** attempt), 4.0))
        raise last_exc  # type: ignore[misc]

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
            response = await self._create(full_messages)
        except Exception as e:
            logger.error(f"LLM API 调用失败: {e}")
            return None
        content = response.choices[0].message.content
        if content is None:
            logger.warning("LLM 返回空内容")
            return None
        return content.strip()

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
        total_start = time.monotonic()

        for round_idx in range(max_rounds):
            try:
                response = await self._create(full_messages, tools=tools)
            except Exception as e:
                logger.error(f"LLM API 调用失败(tools): {e}")
                return None

            msg = response.choices[0].message
            if not msg.tool_calls:
                content = msg.content
                if content is None:
                    logger.warning("LLM 返回空内容(tools)")
                    return None
                logger.info(
                    f"[LLM] 工具对话完成 | 轮数={round_idx + 1} "
                    f"总耗时{time.monotonic() - total_start:.1f}s"
                )
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
                t0 = time.monotonic()
                try:
                    result = await tool_handler(
                        tc.function.name, tc.function.arguments
                    )
                except Exception as e:
                    logger.error(f"[工具] 执行失败 {tc.function.name}: {e}")
                    result = f"工具执行出错: {e}"
                logger.info(
                    f"[工具] {tc.function.name} 执行耗时 {time.monotonic() - t0:.1f}s"
                )
                full_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                )

        logger.warning("LLM 工具调用轮次超限")
        return None
