"""看门狗插件 - 连接监控与自动保活

功能:
1. 监控 WebSocket 连接状态
2. 定时心跳保活
3. 断线自动告警日志
"""
import asyncio
from nonebot import get_driver, logger, get_bot
from nonebot.adapters.onebot.v11 import Bot
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="看门狗",
    description="定时心跳保活，监控连接状态，防止掉线",
    usage="自动运行，无需手动触发",
)

driver = get_driver()
_heartbeat_task: asyncio.Task | None = None


async def _heartbeat_loop():
    """每 5 分钟发送一次心跳检查，保持连接活跃"""
    await asyncio.sleep(60)  # 启动后等 1 分钟再开始
    while True:
        try:
            bot: Bot = get_bot()
            # 尝试获取登录信息来检查连接
            login_info = await bot.get_login_info()
            logger.info(f"💓 心跳正常 | QQ: {login_info.get('nickname', 'N/A')}({login_info.get('user_id', 'N/A')})")
        except Exception as e:
            logger.error(f"💔 心跳检测失败，连接可能已断开: {e}")
        await asyncio.sleep(300)  # 每 5 分钟一次


@driver.on_bot_connect
async def on_bot_connect(bot: Bot):
    """Bot 连接成功"""
    logger.info(f"🔗 Bot 已连接: {bot.self_id}")
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())


@driver.on_bot_disconnect
async def on_bot_disconnect(bot: Bot):
    """Bot 断开连接"""
    logger.warning(f"🔌 Bot 已断开: {bot.self_id}")
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
        _heartbeat_task = None


@driver.on_startup
async def _():
    logger.info("🛡️ 看门狗插件已启动")


@driver.on_shutdown
async def _():
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
    logger.info("🛡️ 看门狗插件已关闭")
