"""视觉功能指令 - /vision on|off|status（全局开关）"""

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

from . import get_vision

# 子命令帮助
VISION_HELP = {
    "on": "开启视觉功能（看图说话）",
    "off": "关闭视觉功能",
    "status": "查看视觉功能状态",
}


async def handle_vision_command(
    bot: Bot, event: GroupMessageEvent, arg: str
) -> bool:
    """处理 /vision 指令。返回 True 表示已处理。"""
    vision = get_vision()
    if vision is None:
        await bot.send_group_msg(
            group_id=event.group_id,
            message="👁️ 视觉模块未初始化。",
        )
        return True

    sub = (arg or "status").strip().lower()
    if sub in ("on", "开", "启用"):
        vision.set_enabled(True)
        logger.info(f"[Vision] /vision on | group={event.group_id}")
        await bot.send_group_msg(
            group_id=event.group_id,
            message="👁️ 视觉功能已开启，我会试着看图说话啦。",
        )
        return True

    if sub in ("off", "关", "禁用"):
        vision.set_enabled(False)
        logger.info(f"[Vision] /vision off | group={event.group_id}")
        await bot.send_group_msg(
            group_id=event.group_id,
            message="👁️ 视觉功能已关闭，我只看文字消息了。",
        )
        return True

    # status
    st = vision.status()
    lines = [
        f"👁️ 视觉功能：{'开 ✅' if st['enabled'] else '关 ⛔'}",
        f"Provider：{st['provider']}",
        f"模型：{st['model']}",
        f"API 可用：{'✅' if st['api_ready'] else '❌（未配置 Key 或不可用）'}",
        f"本地预筛：CLIP {'开' if st['clip_enabled'] else '关'} / OCR {'开' if st['ocr_enabled'] else '关'}",
        f"缓存：{st['cache_size']} 张",
    ]
    logger.info(f"[Vision] /vision status | group={event.group_id}")
    await bot.send_group_msg(
        group_id=event.group_id,
        message="\n".join(lines),
    )
    return True
