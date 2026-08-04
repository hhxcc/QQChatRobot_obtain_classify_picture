"""VisionProvider 抽象接口 - 视觉模型解耦的核心

未来更换视觉模型（Qwen-VL / GPT-4o 等）只需：
1. 新增一个实现本接口的 Provider 类
2. 在 service.py 中根据 VISION_PROVIDER 配置实例化对应类
其余代码零改动。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ImageDescription:
    """图片理解结果（由视觉模型返回，结构化为 JSON）"""

    description: str = ""       # 画面描述
    worth_reply: bool = True    # 是否值得回复
    topic: str = ""             # 话题类别
    sentiment: str = ""         # 情绪基调
    raw: str = ""               # 原始返回（调试用）


class VisionProvider(ABC):
    """视觉模型抽象接口"""

    @abstractmethod
    async def describe_image(
        self, image_bytes: bytes, context: str = ""
    ) -> ImageDescription:
        """分析图片，返回结构化描述

        Args:
            image_bytes: 原始图片字节
            context: 可选的群聊上下文文字

        Returns:
            ImageDescription；失败时返回 description 为空、worth_reply=False 的对象
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Provider 是否已配置可用"""
