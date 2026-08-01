"""场景检测器 - 基于关键词模式匹配，识别群聊话题并返回剧情锚点"""

import yaml
from pathlib import Path
from nonebot import logger


class SceneDetector:
    """场景检测器：加载 YAML 配置，检测消息中的场景模式"""

    def __init__(self, config_path: str = "knowledge/scene_triggers.yaml"):
        self._scenes: list = []
        config = Path(config_path)
        if not config.is_absolute():
            config = Path.cwd() / config
        if config.exists():
            try:
                data = yaml.safe_load(config.read_text(encoding="utf-8"))
                self._scenes = data.get("scenes", [])
                logger.info(
                    f"场景检测器已加载: {len(self._scenes)} 个场景, {config}"
                )
            except Exception as e:
                logger.error(f"加载场景触发配置失败: {e}")
        else:
            logger.warning(f"场景触发配置文件不存在: {config}")

    @property
    def is_ready(self) -> bool:
        return len(self._scenes) > 0

    def detect(self, text: str) -> list[str]:
        """检测文本中的场景，返回匹配的场景上下文列表（按 priority 降序，最多 2 个）"""
        matched = []
        for scene in self._scenes:
            patterns = scene.get("patterns", [])
            if any(p in text for p in patterns):
                matched.append((scene.get("priority", 5), scene.get("context", "")))
        matched.sort(key=lambda x: x[0], reverse=True)
        return [ctx for _, ctx in matched[:2]]
