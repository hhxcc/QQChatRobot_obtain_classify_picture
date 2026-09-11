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

    # ── 视觉回复模式 ──
    # describe=视觉模型先出结构化描述，再交聊天模型（省 token，两步）
    # direct  =图片直接交给支持多模态的聊天模型，端到端看图回复（无损，一步）
    llm_vision_mode: str = Field(default="describe")
    # direct 模式下单条请求最多携带的图片数（控制 token 与耗时）
    llm_vision_max_images: int = Field(default=2, ge=1, le=5)

    # 上下文控制
    llm_max_history: int = Field(default=20, ge=1, le=100)
    llm_temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=512, ge=1, le=4096)
    # 单次 LLM 请求超时（秒）与网络类异常重试次数（应对校园网等不稳定网络）
    llm_timeout: float = Field(default=30.0, ge=5.0, le=180.0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)

    # ── 长期记忆 ──
    llm_memory_enabled: bool = Field(default=True)
    # 记忆数据库路径（sqlite，持久化，重启不丢）
    memory_db_path: str = Field(default="data/memory.db")
    # 蒸馏模型（解耦，可与聊天模型不同；API Key 留空则复用 DeepSeek 聊天配置）
    memory_provider: str = Field(default="deepseek")
    memory_base_url: str = Field(default="")
    memory_api_key: str = Field(default="")
    memory_model: str = Field(default="deepseek-chat")
    # 每人累积多少条消息触发一次蒸馏（消息量触发）
    memory_distill_threshold: int = Field(default=30, ge=2, le=500)
    # 定时兜底蒸馏间隔（秒）
    memory_distill_interval: int = Field(default=1800, ge=60)

    # ── 联网搜索 ──
    llm_web_search_enabled: bool = Field(default=True)
    # 默认搜索方式：bing | duckduckgo | baidu（模型也可调用其他引擎函数）
    search_engine: str = Field(default="bing")
    search_result_count: int = Field(default=5, ge=1, le=10)
    search_timeout: float = Field(default=8.0)
    # 搜索缓存 TTL（秒）：同类问题短时间不重复搜，省时间省流量
    search_cache_ttl: int = Field(default=300, ge=0, le=3600)

    class Config:
        extra = "ignore"
