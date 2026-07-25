"""配置模型"""

from typing import List, Optional
from pydantic import BaseModel, Field


class Config(BaseModel):
    """图片分类器配置"""

    # OneBot 连接
    onebot_ws_url: str = Field(default="ws://127.0.0.1:3001")

    # 目标群 (空列表=监听所有群)
    target_groups: List[int] = Field(default_factory=list)

    # 分类配置
    anime_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    yolo_model_path: str = Field(default="models/yolov8n-cls.pt")
    use_gpu: bool = Field(default=True)

    # 保存配置
    image_save_dir: str = Field(default="data/images")
    retention_days: int = Field(default=30, ge=0)

    class Config:
        extra = "ignore"
