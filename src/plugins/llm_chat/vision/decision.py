"""视觉决策器 - 决定是否升级调用视觉 API

决策不依赖缓存（缓存由 VisionService 负责），只根据触发场景与本地预筛结果判断。
"""

from dataclasses import dataclass

from .config import VisionConfig


@dataclass
class VisionDecision:
    should_analyze: bool   # 是否调视觉 API
    reason: str            # 决策原因（日志/调试）


class VisionDecisionMaker:
    """根据触发场景 + CLIP 结果决定是否升级调视觉 API"""

    def __init__(self, config: VisionConfig):
        self._config = config

    def decide(
        self,
        *,
        is_mentioned: bool,
        has_text: bool,
        clip_category: str,
        clip_conf: float,
    ) -> VisionDecision:
        # ① 被 @ 提及 + 发图 → 必调
        if self._config.reply_on_at and is_mentioned:
            return VisionDecision(True, "被@提及，必回")

        # ② 图 + 文字混发 → 调（图文结合理解）
        if self._config.reply_on_text_img and has_text:
            return VisionDecision(True, "图文混发")

        # ③ 纯图片消息 → 仅当 CLIP 命中有效类别且达阈值才调（受冷却约束）
        if self._config.reply_on_image_only:
            if clip_category != "其他" and clip_conf >= self._config.clip_threshold:
                return VisionDecision(
                    True, f"纯图命中类别:{clip_category}({clip_conf:.0%})"
                )
            return VisionDecision(
                False, f"纯图未达阈值:{clip_category}({clip_conf:.0%})"
            )

        return VisionDecision(False, "视觉触发未开启")
