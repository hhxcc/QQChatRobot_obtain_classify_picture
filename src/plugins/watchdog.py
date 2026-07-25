"""看门狗插件 - 连接监控与自动保活

功能:
1. 监控 WebSocket 连接状态
2. 监听 QQ 登录态失效 (bot_offline 通知)
3. 定时心跳保活
4. 断线/掉线自动退出，由守护脚本重启
"""
import asyncio
import sys
from nonebot import get_driver, logger, get_bot, on_notice
from nonebot.adapters.onebot.v11 import Bot, NoticeEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule

__plugin_meta__ = PluginMetadata(
    name="看门狗",
    description="定时心跳保活，监控连接状态，检测登录失效并自动重启",
    usage="自动运行，无需手动触发",
)

driver = get_driver()
_heartbeat_task: asyncio.Task | None = None
_offline_detected: bool = False


# ── 监听 QQ 登录态失效 ──
def is_bot_offline(event: NoticeEvent) -> bool:
    return event.notice_type == "bot_offline"


bot_offline = on_notice(rule=Rule(is_bot_offline), block=False)


@bot_offline.handle()
async def handle_bot_offline(event: NoticeEvent):
    """QQ 账号登录失效（被挤下线/登录过期）"""
    global _offline_detected
    _offline_detected = True
    extra = event.dict(exclude={"time", "self_id", "post_type", "notice_type"})
    logger.critical(
        f"🚨 QQ 账号 {event.self_id} 登录已失效！详情: {extra}"
    )
    logger.critical("⏳ 5 秒后退出 Bot 进程，由 start_bot.bat 守护脚本重启...")
    await asyncio.sleep(5)
    sys.exit(1)


# ── 定时心跳 ──
async def _heartbeat_loop():
    """每 5 分钟发送一次心跳检查，保持连接活跃"""
    await asyncio.sleep(60)
    while True:
        try:
            bot: Bot = get_bot()
            login_info = await bot.get_login_info()
            logger.info(
                f"💓 心跳正常 | QQ: {login_info.get('nickname', 'N/A')}"
                f"({login_info.get('user_id', 'N/A')})"
            )
        except Exception as e:
            logger.error(f"💔 心跳检测失败，连接可能已断开: {e}")
        await asyncio.sleep(300)


# ── WebSocket 连接事件 ──
@driver.on_bot_connect
async def on_bot_connect(bot: Bot):
    logger.info(f"🔗 Bot 已连接: {bot.self_id}")
    global _heartbeat_task, _offline_detected
    _offline_detected = False
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())


@driver.on_bot_disconnect
async def on_bot_disconnect(bot: Bot):
    logger.warning(f"🔌 Bot WebSocket 已断开: {bot.self_id}")
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
