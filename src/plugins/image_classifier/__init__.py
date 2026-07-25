"""图片分类器插件 - NoneBot2 入口"""

from nonebot import get_driver, logger
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="图片分类器",
    description="监听QQ群消息，自动下载图片并用YOLOv8分类保存二次元图片",
    usage="自动运行，无需手动触发。配置见 .env 文件。",
    config=Config,
)

driver = get_driver()
plugin_config = Config()


@driver.on_startup
async def on_startup():
    """机器人启动时加载 YOLO 模型并初始化配置"""
    global plugin_config

    # 直接从 driver.config 读取（NoneBot2 已自动合并所有配置）
    config_dict = {
        k: getattr(driver.config, k, v.default)
        for k, v in Config.model_fields.items()
    }
    try:
        plugin_config = Config(**config_dict)
        logger.info(f"插件配置已加载: target_groups={plugin_config.target_groups}")
    except Exception as e:
        logger.warning(f"配置解析失败，使用默认值: {e}")

    # 初始化分类器
    from .classifier import init_classifier
    await init_classifier(plugin_config)

    # 同步配置给 handler
    from .handler import _init_config
    _init_config()

    logger.info("✅ 图片分类器插件已启动")


@driver.on_shutdown
async def on_shutdown():
    """机器人关闭时清理资源"""
    logger.info("图片分类器插件已关闭")
