"""视觉服务 - 对上层(handler)暴露的单一入口

职责：
1. 懒加载 Provider / 本地预筛 / 决策器
2. 完整流程：下载图片 → 本地预筛 → 决策 → (缓存) → 视觉 API → 返回描述
3. 运行期全局开关（/vision on|off 动态切换）
4. 提供 status() 供 /vision status 展示

换视觉模型：只需在 _create_provider 中按 VISION_PROVIDER 分支实例化不同 Provider。
"""

import asyncio
import hashlib
import time
from typing import Dict, Optional, Tuple

import httpx
from nonebot import logger

from .config import VisionConfig
from .decision import VisionDecisionMaker
from .glm_provider import GLMVisionProvider
from .local_vision import LocalMeta, LocalVision
from .ollama_provider import OllamaVisionProvider
from .provider import ImageDescription, VisionProvider

# 熔断参数：连续失败达到阈值后，暂停视觉 API 调用一段时间
_CIRCUIT_FAIL_THRESHOLD = 3
_CIRCUIT_OPEN_SECONDS = 300


class VisionService:
    """视觉功能统一入口"""

    def __init__(self, config: VisionConfig):
        self._config = config
        self._enabled = config.enabled
        self._provider: Optional[VisionProvider] = None
        self._local: Optional[LocalVision] = None
        self._decision: Optional[VisionDecisionMaker] = None
        # md5 -> (timestamp, ImageDescription)
        self._cache: Dict[str, Tuple[float, ImageDescription]] = {}
        # 熔断状态
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    # ── 状态 ──

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool):
        self._enabled = bool(value)
        logger.info(f"[Vision] 全局开关 -> {'开' if self._enabled else '关'}")

    @property
    def is_ready(self) -> bool:
        return self._provider is not None and self._provider.is_available()

    # ── 初始化 ──

    async def ensure_loaded(self):
        """懒加载各组件（可重入）"""
        if self._local is None:
            self._local = LocalVision(
                clip_enabled=self._config.clip_enabled,
                ocr_enabled=self._config.ocr_enabled,
                clip_model_path=self._config.clip_model_path,
            )
        if self._decision is None:
            self._decision = VisionDecisionMaker(self._config)
        if self._provider is None:
            self._provider = self._create_provider()

    def _create_provider(self) -> Optional[VisionProvider]:
        """按配置实例化视觉 Provider（解耦点：换模型在此扩展）"""
        provider_type = (self._config.provider or "glm").lower()

        # 本地 Ollama：走原生 /api/chat，无需 API Key
        if provider_type == "ollama":
            base_url = self._config.base_url
            if not base_url or base_url == "https://open.bigmodel.cn/api/paas/v4":
                base_url = "http://localhost:11434"
            return OllamaVisionProvider(
                model=self._config.model or "qwen3.5:4B",
                base_url=base_url,
                # 本地冷启动/推理较慢，放宽超时
                timeout=max(self._config.timeout, 120.0),
                think=self._config.ollama_think,
            )

        api_key = self._config.api_key
        if not api_key or api_key in ("your-api-key-here", "sk-xxxxxxxx"):
            logger.warning(
                "[Vision] VISION_API_KEY 未配置或为占位值，视觉 API 不可用"
            )
            return None
        if provider_type == "glm":
            return GLMVisionProvider(
                api_key=api_key,
                model=self._config.model,
                base_url=self._config.base_url,
                timeout=self._config.timeout,
            )
        # 未来扩展：qwen / openai 等（OpenAI 兼容，可复用 GLM provider）
        logger.warning(f"[Vision] 未知 Provider 类型: {provider_type}，使用 GLM")
        return GLMVisionProvider(
            api_key=api_key,
            model=self._config.model,
            base_url=self._config.base_url,
            timeout=self._config.timeout,
        )

    # ── 图片下载 ──

    @staticmethod
    async def download_image(url: str, timeout: int = 15) -> bytes:
        """从 URL 下载图片（复用 image_classifier 的下载模式）"""
        headers = {
            "User-Agent": "QQBot-LLMChat/1.0",
            "Accept": "image/*",
        }
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True
        ) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content

    # ── 核心流程 ──

    async def analyze_image(
        self,
        image_bytes: bytes,
        *,
        is_mentioned: bool = False,
        has_text: bool = False,
        context: str = "",
    ) -> Tuple[Optional[ImageDescription], Optional[LocalMeta]]:
        """完整流程：本地预筛 → 决策 → (缓存) → 视觉 API

        Returns:
            (视觉描述, 本地预筛结果)；视觉被跳过时描述为 None
        """
        await self.ensure_loaded()

        # 本地预筛（CLIP + OCR）
        local_meta: Optional[LocalMeta] = None
        if self._local and self._local.is_ready:
            try:
                local_meta = await self._local.analyze(image_bytes)
            except Exception as e:
                logger.error(f"[Vision] 本地预筛异常: {e}")

        # 决策：是否值得升级调视觉 API
        if self._decision is None:
            return None, local_meta
        decision = self._decision.decide(
            is_mentioned=is_mentioned,
            has_text=has_text,
            clip_category=local_meta.clip_category if local_meta else "其他",
            clip_conf=local_meta.clip_conf if local_meta else 0.0,
        )
        if not decision.should_analyze:
            logger.debug(f"[Vision] 决策不调 API: {decision.reason}")
            return None, local_meta

        # 缓存命中？
        img_hash = hashlib.md5(image_bytes).hexdigest()
        cached = self._cache.get(img_hash)
        if cached:
            ts, desc = cached
            if time.time() - ts < self._config.cache_ttl:
                logger.debug(f"[Vision] 缓存命中 | {decision.reason}")
                return desc, local_meta
            self._cache.pop(img_hash, None)

        # 调视觉 API
        if self._provider is None or not self._provider.is_available():
            logger.warning(
                f"[Vision] 视觉 API 不可用，跳过 | 决策={decision.reason}"
            )
            return None, local_meta

        # 熔断检查：熔断期内跳过视觉 API，仅用本地预筛结果
        if time.time() < self._circuit_open_until:
            remain = int(self._circuit_open_until - time.time())
            logger.warning(f"[Vision] 熔断中（{remain}s 后恢复），跳过视觉 API")
            return None, local_meta

        try:
            desc = await asyncio.wait_for(
                self._provider.describe_image(image_bytes, context=context),
                timeout=self._config.timeout + 5.0,
            )
        except asyncio.TimeoutError:
            logger.warning("[Vision] 视觉 API 超时")
            self._record_failure()
            return None, local_meta
        except Exception as e:
            logger.error(f"[Vision] 视觉 API 异常: {e}")
            self._record_failure()
            return None, local_meta

        # 成功/失败记账（用于熔断）
        if desc and desc.description:
            self._record_success()
        else:
            self._record_failure()

        # 写缓存（仅缓存成功返回）
        if desc and desc.description:
            self._cache[img_hash] = (time.time(), desc)
        logger.info(
            f"[Vision] 已分析图片 | {decision.reason} | "
            f"topic={desc.topic or local_meta.clip_category if local_meta else ''} | "
            f"描述={desc.description[:40]}"
        )
        return desc, local_meta

    async def screen_image(
        self,
        image_bytes: bytes,
        *,
        is_mentioned: bool = False,
        has_text: bool = False,
    ) -> Tuple[bool, Optional[LocalMeta]]:
        """仅执行本地预筛（CLIP + OCR）+ 决策，**不调用视觉 API**。

        用于 direct 端到端模式：由预筛判断“这张图是否值得交给多模态聊天模型”，
        由聊天模型自己看图回复，省去“视觉模型先出描述”的一步。

        Returns:
            (是否值得分析, 本地预筛结果)
        """
        await self.ensure_loaded()

        local_meta: Optional[LocalMeta] = None
        if self._local and self._local.is_ready:
            try:
                local_meta = await self._local.analyze(image_bytes)
            except Exception as e:
                logger.error(f"[Vision] 本地预筛异常: {e}")

        # 无决策器 → 默认放行（宁可多带一张，也不要漏看）
        if self._decision is None:
            return True, local_meta

        decision = self._decision.decide(
            is_mentioned=is_mentioned,
            has_text=has_text,
            clip_category=local_meta.clip_category if local_meta else "其他",
            clip_conf=local_meta.clip_conf if local_meta else 0.0,
        )
        logger.debug(
            f"[Vision] direct 预筛={decision.should_analyze} | {decision.reason}"
        )
        return decision.should_analyze, local_meta

    # ── 熔断辅助 ──

    def _record_failure(self):
        """记录一次失败，达到阈值则打开熔断"""
        self._consecutive_failures += 1
        if self._consecutive_failures >= _CIRCUIT_FAIL_THRESHOLD:
            self._circuit_open_until = time.time() + _CIRCUIT_OPEN_SECONDS
            self._consecutive_failures = 0
            logger.warning(
                f"[Vision] 连续 {_CIRCUIT_FAIL_THRESHOLD} 次失败，"
                f"熔断 {_CIRCUIT_OPEN_SECONDS}s"
            )

    def _record_success(self):
        """成功则重置熔断计数"""
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    # ── 状态报告 ──

    def status(self) -> dict:
        return {
            "enabled": self._enabled,
            "provider": (self._config.provider or "glm"),
            "model": self._config.model,
            "api_ready": self.is_ready,
            "clip_enabled": self._config.clip_enabled,
            "ocr_enabled": self._config.ocr_enabled,
            "cache_size": len(self._cache),
            "circuit_open": self._circuit_open_until > time.time(),
            "consecutive_failures": self._consecutive_failures,
        }
