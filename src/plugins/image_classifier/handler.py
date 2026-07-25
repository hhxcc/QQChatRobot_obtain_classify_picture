"""群消息处理器 - 监听图片消息并触发分类流程"""

import hashlib
from typing import Set

from nonebot import on_message, logger, get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.rule import Rule

from .config import Config
from .downloader import download_image
from .classifier import classify_image
from .storage import save_image


# 获取全局配置
_driver = get_driver()
_plugin_config: Config = Config()


def _init_config():
    """延迟初始化配置"""
    global _plugin_config
    try:
        config_dict = {
            k: getattr(_driver.config, k, v.default)
            for k, v in Config.model_fields.items()
        }
        _plugin_config = Config(**config_dict)
    except Exception:
        logger.warning("无法解析插件配置，使用默认值")


# 去重集合
_seen_images: Set[str] = set()

# 只响应群消息
group_msg = on_message(rule=Rule(lambda event: isinstance(event, GroupMessageEvent)))


@group_msg.handle()
async def handle_group_message(bot: Bot, event: GroupMessageEvent):
    """处理群消息，提取图片并分类"""
    group_id = event.group_id

    # 检查是否为目标群
    if _plugin_config.target_groups and group_id not in _plugin_config.target_groups:
        return

    # 提取图片消息段
    image_segments = [seg for seg in event.message if seg.type == "image"]
    if not image_segments:
        return

    for seg in image_segments:
        file_id = seg.data.get("file", "")
        file_url = seg.data.get("url", "")

        if not file_url:
            logger.warning(f"图片缺少URL，跳过: {file_id}")
            continue

        # 去重
        img_hash = hashlib.md5(file_id.encode()).hexdigest()
        if img_hash in _seen_images:
            logger.debug(f"重复图片，跳过: {file_id}")
            continue
        _seen_images.add(img_hash)
        if len(_seen_images) > 10000:
            _seen_images.clear()

        try:
            logger.info(f"下载图片: group={group_id}, file={file_id[:20]}...")
            img_data = await download_image(file_url)

            is_anime, confidence = await classify_image(img_data, _plugin_config)

            if is_anime:
                save_path = save_image(img_data, group_id, file_id, confidence, _plugin_config)
                logger.info(f"✅ 二次元图片已保存: {save_path} (置信度: {confidence:.2%})")
            else:
                logger.info(f"❌ 非二次元图片跳过 (置信度: {confidence:.2%})")

        except Exception as e:
            logger.error(f"处理图片失败 [{file_id[:20]}]: {e}")
