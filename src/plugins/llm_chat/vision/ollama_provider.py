"""Ollama 本地视觉 Provider - 走 Ollama 原生 /api/chat

为什么不用 OpenAI 兼容 /v1:
  实测 qwen3.5:4B 在 /v1 下即使传 think=false 仍会残留 reasoning,
  低 max_tokens 时把 content 挤空 / JSON 截断;而原生 /api/chat +
  images 数组 + think=false 稳定干净(约 4s/张,JSON 完整)。

适用: 本地 Ollama 部署的多模态模型(如 qwen3.5:4B)。
无需 API Key;base_url 默认 http://localhost:11434(可指向远程 Ollama)。
"""

import base64
import json
from typing import Optional

import httpx
from nonebot import logger

from .provider import VisionProvider, ImageDescription

# 与 glm_provider._PROMPT 保持一致的强结构化 Prompt
_PROMPT = (
    "请分析这张图片，并严格只返回一个 JSON 对象（不要包含```json、注释或任何其他文字）：\n"
    '{"description": "用一句中文客观描述画面内容",'
    ' "worth_reply": true,'
    ' "topic": "图片所属类别，从这些里选：宠物/美食/饮品/风景/自拍/人物/日常/表情包/截图/动漫/其他",'
    ' "sentiment": "画面情绪基调：温馨/搞笑/严肃/恐怖/中性"}'
)

# qwen3.5 系默认开 thinking,须关闭否则答案进 thinking 导致 content 为空
_THINK_OFF = False
_TEMPERATURE = 0.2
_NUM_PREDICT = 1024


class OllamaVisionProvider(VisionProvider):
    """Ollama 原生多模态视觉模型实现"""

    def __init__(
        self,
        model: str = "qwen3.5:4B",
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def is_available(self) -> bool:
        return bool(self._model) and bool(self._base_url)

    async def describe_image(
        self, image_bytes: bytes, context: str = ""
    ) -> ImageDescription:
        b64 = base64.b64encode(image_bytes).decode("utf-8")

        content = _PROMPT
        if context:
            content = f"群聊上下文：{context}\n{_PROMPT}"

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                    "images": [b64],  # Ollama 原生: 裸 base64
                }
            ],
            "stream": False,
            "think": _THINK_OFF,
            "options": {
                "temperature": _TEMPERATURE,
                "num_predict": _NUM_PREDICT,
            },
        }
        url = f"{self._base_url}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            raw = (data.get("message") or {}).get("content") or ""
            return self._parse(raw)
        except Exception as e:
            logger.error(f"[Vision] Ollama 调用失败: {e}")
            return ImageDescription(description="", worth_reply=False, raw=str(e))

    def _parse(self, text: str) -> ImageDescription:
        """容错解析(与 glm_provider 行为一致)"""
        desc = ImageDescription(raw=text.strip())
        json_str = self._extract_json(text)
        if not json_str:
            logger.warning(f"[Vision] Ollama 未返回有效 JSON: {text[:80]!r}")
            if text.strip():
                desc.description = text.strip()
            return desc
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"[Vision] Ollama JSON 解析失败: {e} | {json_str[:80]!r}")
            return desc

        desc.description = str(data.get("description", "")).strip()
        desc.worth_reply = bool(data.get("worth_reply", True))
        desc.topic = str(data.get("topic", "")).strip()
        desc.sentiment = str(data.get("sentiment", "")).strip()
        return desc

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        if not text:
            return None
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return text[start : end + 1]
