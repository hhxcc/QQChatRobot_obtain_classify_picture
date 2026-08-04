"""GLM-4.6V-Flash 视觉模型实现（OpenAI 兼容接口）

使用项目已有的 openai SDK 调用智谱开放平台视觉模型，
通过结构化 JSON Prompt 让模型返回可解析的图片描述。
内置 429 限流指数退避重试。
"""

import asyncio
import base64
import json
import re
from typing import Optional

from openai import AsyncOpenAI
from nonebot import logger

from .provider import VisionProvider, ImageDescription

# 结构化输出 Prompt：要求模型严格返回 JSON
_PROMPT = (
    "请分析这张图片，并严格只返回一个 JSON 对象（不要包含```json、注释或任何其他文字）：\n"
    '{"description": "用一句中文客观描述画面内容",'
    ' "worth_reply": true,'
    ' "topic": "图片所属类别，从这些里选：宠物/美食/饮品/风景/自拍/人物/日常/表情包/截图/动漫/其他",'
    ' "sentiment": "画面情绪基调：温馨/搞笑/严肃/恐怖/中性"}'
)


def _is_rate_limited(err: str) -> bool:
    """判断错误是否为 429 限流"""
    return "429" in err or "1305" in err or "访问量过大" in err


class GLMVisionProvider(VisionProvider):
    """GLM-4V-Flash 视觉模型实现"""

    def __init__(
        self,
        api_key: str,
        model: str = "glm-4.6v-flash",
        base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        timeout: float = 15.0,
    ):
        self._api_key = api_key
        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    def is_available(self) -> bool:
        return bool(self._api_key) and self._api_key not in (
            "your-api-key-here",
            "sk-xxxxxxxx",
        )

    async def describe_image(
        self, image_bytes: bytes, context: str = ""
    ) -> ImageDescription:
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        content = []
        if context:
            content.append({"type": "text", "text": f"群聊上下文：{context}"})
        content.append({"type": "text", "text": _PROMPT})
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )

        # 429 限流指数退避重试（最多额外 2 次，间隔 3s/6s）
        last_err = ""
        for attempt in range(3):
            try:
                resp = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": content}],
                    temperature=0.2,
                    max_tokens=300,
                )
                text = resp.choices[0].message.content or ""
                return self._parse(text)
            except Exception as e:
                last_err = str(e)
                if attempt < 2 and _is_rate_limited(last_err):
                    wait = 3 * (attempt + 1)
                    logger.warning(
                        f"[Vision] GLM 429 限流，{wait}s 后重试 "
                        f"({attempt + 1}/2)"
                    )
                    await asyncio.sleep(wait)
                else:
                    break

        logger.error(f"[Vision] GLM API 调用失败: {last_err}")
        return ImageDescription(description="", worth_reply=False, raw=last_err)

    def _parse(self, text: str) -> ImageDescription:
        """容错解析模型返回的 JSON（容忍 ```json 包裹、前后多余文字）"""
        desc = ImageDescription(raw=text.strip())
        json_str = self._extract_json(text)
        if not json_str:
            logger.warning(f"[Vision] 模型未返回有效 JSON: {text[:80]!r}")
            # 兜底：把纯文本当作描述
            if text.strip():
                desc.description = text.strip()
            return desc
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"[Vision] JSON 解析失败: {e} | {json_str[:80]!r}")
            return desc

        desc.description = str(data.get("description", "")).strip()
        desc.worth_reply = bool(data.get("worth_reply", True))
        desc.topic = str(data.get("topic", "")).strip()
        desc.sentiment = str(data.get("sentiment", "")).strip()
        return desc

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """从文本中提取第一个 {...} JSON 对象"""
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start : end + 1]
