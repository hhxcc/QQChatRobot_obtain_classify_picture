"""视觉模块 - 图片理解与看图对话（解耦设计）

对外提供：
- init_vision(driver_config)  在插件启动时初始化全局服务
- get_vision()               获取全局视觉服务（可能为 None）
- is_vision_enabled()        视觉功能当前是否开启

解耦说明：
- 换视觉模型：新增 Provider 实现 + service._create_provider 加分支
- 换 API Key / 模型名：改 .env 的 VISION_* 配置
- 关闭功能：.env 设 LLM_VISION_ENABLED=false 或 /vision off
"""

from nonebot import logger

from .config import VisionConfig
from .decision import VisionDecisionMaker, VisionDecision
from .glm_provider import GLMVisionProvider
from .local_vision import LocalMeta, LocalVision
from .ollama_provider import OllamaVisionProvider
from .provider import ImageDescription, VisionProvider
from .service import VisionService

__all__ = [
    "VisionConfig",
    "VisionService",
    "VisionProvider",
    "ImageDescription",
    "GLMVisionProvider",
    "OllamaVisionProvider",
    "LocalVision",
    "LocalMeta",
    "VisionDecisionMaker",
    "VisionDecision",
    "init_vision",
    "get_vision",
    "is_vision_enabled",
]

# 全局单例
_service: VisionService | None = None


def init_vision(driver_config) -> VisionService:
    """初始化全局视觉服务（由插件 on_startup 调用，可重入）"""
    global _service
    if _service is None:
        config = VisionConfig.from_driver(driver_config)
        _service = VisionService(config)
        logger.info(
            f"视觉服务已初始化: enabled={_service.enabled}, "
            f"provider={config.provider}, model={config.model}"
        )
    return _service


def get_vision() -> VisionService | None:
    """获取全局视觉服务"""
    return _service


def is_vision_enabled() -> bool:
    """视觉功能是否开启"""
    return _service is not None and _service.enabled
