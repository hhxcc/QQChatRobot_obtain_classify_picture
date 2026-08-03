"""LLM 聊天插件 - NoneBot2 入口"""

from pathlib import Path

from nonebot import get_driver, logger
from nonebot.plugin import PluginMetadata

from .config import Config
from .knowledge_store import KnowledgeStore
from .scene_detector import SceneDetector

# ⚠️ 必须在模块级导入 handler，确保 on_message matcher 在插件加载时注册
# 不能放在 on_startup 中延迟导入，否则 matcher 注册时机太晚不会生效
from .handler import _init_config, _init_client, _set_knowledge_store, _set_scene_detector, _clear_group_state

__plugin_meta__ = PluginMetadata(
    name="LLM 聊天",
    description="监听群聊文字消息，交由 DeepSeek 大模型决策是否回复，支持角色扮演",
    usage="自动运行，无需手动触发。配置见 .env 文件。",
    config=Config,
)

driver = get_driver()
plugin_config = Config()
_knowledge_store: KnowledgeStore | None = None
_scene_detector: SceneDetector | None = None


@driver.on_startup
async def on_startup():
    """机器人启动时初始化 LLM 客户端"""
    global plugin_config, _knowledge_store, _scene_detector

    # 从 driver.config 读取配置
    config_dict = {
        k: getattr(driver.config, k, v.default)
        for k, v in Config.model_fields.items()
    }

    # 如果指定了系统提示词文件，从文件读取（优先级高于 LLM_SYSTEM_PROMPT）
    prompt_file = config_dict.get("llm_system_prompt_file", "")
    if prompt_file:
        prompt_path = Path(prompt_file)
        if not prompt_path.is_absolute():
            prompt_path = Path.cwd() / prompt_path
        if prompt_path.exists():
            try:
                file_content = prompt_path.read_text(encoding="utf-8").strip()
                if file_content:
                    config_dict["llm_system_prompt"] = file_content
                    logger.info(f"已从文件加载系统提示词: {prompt_path} ({len(file_content)} 字符)")
                else:
                    logger.warning(f"系统提示词文件为空: {prompt_path}")
            except Exception as e:
                logger.error(f"读取系统提示词文件失败: {prompt_path}, 错误: {e}")
        else:
            logger.error(f"系统提示词文件不存在: {prompt_path}")

    # 加载 few-shot 对话示例（可选，追加到系统提示词末尾）
    few_shot_file = config_dict.get("llm_few_shot_file", "")
    if few_shot_file:
        few_shot_path = Path(few_shot_file)
        if not few_shot_path.is_absolute():
            few_shot_path = Path.cwd() / few_shot_path
        if few_shot_path.exists():
            try:
                few_shot_content = few_shot_path.read_text(encoding="utf-8").strip()
                if few_shot_content:
                    current_prompt = config_dict.get("llm_system_prompt", "")
                    config_dict["llm_system_prompt"] = (
                        current_prompt + "\n\n" + few_shot_content
                    )
                    logger.info(
                        f"已加载对话风格示例: {few_shot_path} "
                        f"({len(few_shot_content)} 字符)"
                    )
            except Exception as e:
                logger.error(f"读取对话风格示例文件失败: {few_shot_path}, 错误: {e}")
        else:
            logger.warning(f"对话风格示例文件不存在: {few_shot_path}")

    try:
        plugin_config = Config(**config_dict)
        logger.info(
            f"LLM 插件配置已加载: "
            f"model={plugin_config.deepseek_model}, "
            f"target_groups={plugin_config.llm_target_groups}"
        )
    except Exception as e:
        logger.warning(f"LLM 插件配置解析失败，使用默认值: {e}")

    # 构建 FTS5 知识库索引
    knowledge_dir = plugin_config.llm_knowledge_dir
    if knowledge_dir:
        _knowledge_store = KnowledgeStore(knowledge_dir)
        if _knowledge_store.build_index():
            stats = _knowledge_store.stats()
            logger.info(
                f"知识库已就绪: {stats['total_chunks']} 块, "
                f"主题: {stats['topics']}"
            )
            _set_knowledge_store(_knowledge_store)
        else:
            logger.warning("知识库为空或构建失败，LLM 将以无知识库模式运行")
            _knowledge_store = None
    else:
        logger.info("未配置知识库目录，LLM 将以无知识库模式运行")

    # 初始化场景检测器（P3）
    scene_file = plugin_config.llm_scene_triggers_file
    if scene_file:
        _scene_detector = SceneDetector(scene_file)
        _set_scene_detector(_scene_detector)
    else:
        _set_scene_detector(None)

    # 同步配置给 handler（传入已加载的 plugin_config，防止被覆盖）
    _init_config(plugin_config)
    await _init_client()

    logger.info("✅ LLM 聊天插件已启动")


@driver.on_shutdown
async def on_shutdown():
    """机器人关闭时清理资源"""
    global _knowledge_store
    if _knowledge_store:
        _knowledge_store.close()
        _knowledge_store = None
    logger.info("LLM 聊天插件已关闭")
