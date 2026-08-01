"""LLM 聊天插件配置模型"""

from typing import List
from pydantic import BaseModel, Field


class Config(BaseModel):
    """LLM 聊天插件配置"""

    # DeepSeek API
    deepseek_api_key: str = Field(default="")
    deepseek_base_url: str = Field(default="https://api.deepseek.com")
    deepseek_model: str = Field(default="deepseek-chat")

    # 角色扮演
    llm_system_prompt: str = Field(
        default="你是一个友好的QQ群聊机器人助手，请自然地参与群聊讨论。如果消息与你无关或你不想插话，只回复 [SKIP]。如果要回应，请简练自然地回复。"
    )
    # 系统提示词文件路径（优先级高于 llm_system_prompt，适合长文本提示词）
    llm_system_prompt_file: str = Field(default="")
    # 分类常识库文件路径（可选，启动时会追加到系统提示词末尾）
    llm_knowledge_dir: str = Field(default="knowledge")
    # Few-shot 对话风格示例文件（可选，启动时追加到系统提示词末尾）
    llm_few_shot_file: str = Field(default="")
    # 场景触发映射文件（可选，YAML 格式，用于话题→剧情锚点的场景检测）
    llm_scene_triggers_file: str = Field(default="knowledge/scene_triggers.yaml")

    # 目标群 (空列表=所有群生效)
    llm_target_groups: List[int] = Field(default_factory=list)

    # 冷却时间控制（模拟真人聊天节奏）
    llm_cooldown_base: float = Field(default=8.0, ge=1.0, le=120.0)
    llm_cooldown_ceiling: float = Field(default=60.0, ge=5.0, le=300.0)
    # 消息缓冲区：CD 期间暂存消息，CD 到期后一起发给 LLM
    llm_buffer_max: int = Field(default=15, ge=1, le=50)

    # 上下文控制
    llm_max_history: int = Field(default=20, ge=1, le=100)
    llm_temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=512, ge=1, le=4096)

    class Config:
        extra = "ignore"
