"""视觉模块配置模型 - 独立于主配置，便于解耦更换视觉模型"""

from pydantic import BaseModel, Field


class VisionConfig(BaseModel):
    """视觉功能配置（从 .env 读取，字段映射见 from_driver）"""

    # 总开关（运行期可由 /vision 指令动态切换）
    enabled: bool = Field(default=False)

    # 视觉模型 Provider（解耦：glm | ollama | qwen | openai | none）
    provider: str = Field(default="glm")
    api_key: str = Field(default="")
    model: str = Field(default="glm-4.6v-flash")
    base_url: str = Field(default="https://open.bigmodel.cn/api/paas/v4")
    timeout: float = Field(default=15.0)

    # 本地预筛
    clip_enabled: bool = Field(default=True)
    clip_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    # CLIP 模型路径（本地优先；为空/不存在时回退到 HF 在线加载）
    clip_model_path: str = Field(default="models/clip-vit-base-patch32")
    ocr_enabled: bool = Field(default=True)

    # 触发策略
    reply_on_at: bool = Field(default=True)
    reply_on_text_img: bool = Field(default=True)
    reply_on_image_only: bool = Field(default=True)

    # 缓存（同一张图 TTL 秒内不重复调视觉 API）
    cache_ttl: float = Field(default=3600.0)

    class Config:
        extra = "ignore"

    @classmethod
    def from_driver(cls, driver_config) -> "VisionConfig":
        """从 NoneBot driver.config 读取 vision_* 配置"""
        return cls(
            enabled=bool(getattr(driver_config, "llm_vision_enabled", False)),
            provider=str(getattr(driver_config, "vision_provider", "glm")),
            api_key=str(getattr(driver_config, "vision_api_key", "")),
            model=str(getattr(driver_config, "vision_model", "glm-4.6v-flash")),
            base_url=str(
                getattr(
                    driver_config,
                    "vision_base_url",
                    "https://open.bigmodel.cn/api/paas/v4",
                )
            ),
            timeout=float(getattr(driver_config, "vision_timeout", 15.0)),
            clip_enabled=bool(getattr(driver_config, "vision_clip_enabled", True)),
            clip_threshold=float(
                getattr(driver_config, "vision_clip_threshold", 0.6)
            ),
            clip_model_path=str(
                getattr(
                    driver_config,
                    "vision_clip_model_path",
                    "models/clip-vit-base-patch32",
                )
            ),
            ocr_enabled=bool(getattr(driver_config, "vision_ocr_enabled", True)),
            reply_on_at=bool(getattr(driver_config, "vision_reply_on_at", True)),
            reply_on_text_img=bool(
                getattr(driver_config, "vision_reply_on_text_img", True)
            ),
            reply_on_image_only=bool(
                getattr(driver_config, "vision_reply_on_image_only", True)
            ),
            cache_ttl=float(getattr(driver_config, "vision_cache_ttl", 3600.0)),
        )
