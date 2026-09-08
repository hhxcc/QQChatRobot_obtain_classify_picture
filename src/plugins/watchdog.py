"""看门狗插件 - 连接监控与自动保活

功能:
1. 监控 WebSocket 连接状态
2. 监听 QQ 登录态失效 (bot_offline 通知)
3. 定时心跳保活
4. 断线/掉线自动退出，由守护脚本重启
"""
import asyncio
import os
from nonebot import get_driver, logger, get_bot, on_notice
from nonebot.adapters.onebot.v11 import Bot, NoticeEvent
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="看门狗",
    description="定时心跳保活，监控连接状态，检测登录失效并自动重启",
    usage="自动运行，无需手动触发",
)

driver = get_driver()
_heartbeat_task: asyncio.Task | None = None
_exit_task: asyncio.Task | None = None
_offline_detected: bool = False


# ── 监听所有通知事件，从中过滤 QQ 登录态失效 ──
bot_offline = on_notice(block=False)


@bot_offline.handle()
async def handle_bot_offline(event: NoticeEvent):
    """捕获所有 notice 事件，只处理 bot_offline"""
    global _offline_detected

    if event.notice_type != "bot_offline":
        return

    _offline_detected = True
    extra = event.dict(exclude={"time", "self_id", "post_type", "notice_type"})
    logger.critical(
        f"🚨 QQ 账号 {event.self_id} 登录已失效！详情: {extra}"
    )
    logger.critical("⏳ 3 秒后退出进程，由 start_bot.bat 守护脚本重启...")
    await asyncio.sleep(3)
    os._exit(1)


# ── 定时心跳 ──
async def _heartbeat_loop():
    """每 3 分钟发送心跳检查，保持连接活跃并检测 QQ 是否真正在线"""
    await asyncio.sleep(30)
    while True:
        try:
            bot: Bot = get_bot()
            login_info = await bot.get_login_info()
            nickname = login_info.get("nickname", "N/A")
            uid = login_info.get("user_id", "N/A")

            # 额外检测：调用 get_group_list 验证 QQ 协议层是否存活
            try:
                groups = await bot.get_group_list()
                group_count = len(groups)
            except Exception:
                group_count = -1

            if group_count < 0:
                logger.error(
                    f"💔 QQ 协议层无响应！WebSocket 连接正常但 QQ 可能已离线 | "
                    f"QQ: {nickname}({uid})"
                )
            else:
                logger.info(
                    f"💓 心跳正常 | QQ: {nickname}({uid}) | 群数: {group_count}"
                )
        except Exception as e:
            logger.error(f"💔 心跳检测失败，连接可能已断开: {e}")
        await asyncio.sleep(180)  # 每 3 分钟


# ── WebSocket 连接事件 ──
@driver.on_bot_connect
async def on_bot_connect(bot: Bot):
    logger.info(f"🔗 Bot 已连接: {bot.self_id}")
    global _heartbeat_task, _exit_task, _offline_detected
    _offline_detected = False

    # 取消断连退出定时器（重连成功，不需要退出了）
    if _exit_task and not _exit_task.done():
        _exit_task.cancel()
        _exit_task = None
        logger.info("🔄 Bot 重连成功，已取消退出定时器")

    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())


@driver.on_bot_disconnect
async def on_bot_disconnect(bot: Bot):
    logger.warning(f"🔌 Bot WebSocket 已断开: {bot.self_id}")
    global _heartbeat_task, _exit_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
        _heartbeat_task = None

    # 不立即退出，给协议端(SnowLuma)60 秒时间重连
    # 如果 60 秒内重连成功，on_bot_connect 会取消此任务
    if _exit_task and not _exit_task.done():
        _exit_task.cancel()

    async def delayed_exit():
        await asyncio.sleep(60)
        logger.critical("⏰ 60 秒内未重连，退出进程由 start_bot.bat 重启...")
        # 两阶段退出：先尝试干净退出，再强制杀死
        import sys
        try:
            sys.exit(1)
        except SystemExit:
            pass
        os._exit(1)

    _exit_task = asyncio.create_task(delayed_exit())
    logger.warning("⏳ WS 断开，等待 60 秒重连，超时后退出...")


@driver.on_startup
async def _():
    logger.info("🛡️ 看门狗插件已启动")


@driver.on_shutdown
async def _():
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
    logger.info("🛡️ 看门狗插件已关闭")


# ── 诊断命令 + 自测命令（on_message 内部过滤）──
from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent

status_cmd = on_message(block=False)


@status_cmd.handle()
async def status_cmd(bot: Bot, event: GroupMessageEvent):
    """诊断机器人状态"""
    text = str(event.get_plaintext()).strip()
    if text not in (".status", "/status"):
        return

    try:
        login_info = await bot.get_login_info()
        nickname = login_info.get("nickname", "N/A")
        uid = login_info.get("user_id", "N/A")
    except Exception:
        nickname, uid = "N/A", "N/A"

    targets = getattr(driver.config, "target_groups", [])
    heartbeat_status = "运行中" if _heartbeat_task and not _heartbeat_task.done() else "未启动"
    msg = (
        f"🤖 Bot 状态报告\n"
        f"QQ: {nickname}({uid})\n"
        f"监听群组: {targets if targets else '全部群'}\n"
        f"心跳任务: {heartbeat_status}"
    )
    await bot.send(event=event, message=msg)


test_cmd = on_message(block=False)


@test_cmd.handle()
async def test_offline_cmd(bot: Bot, event: GroupMessageEvent):
    """模拟 bot_offline 通知，验证看门狗是否能检测"""
    text = str(event.get_plaintext()).strip()
    if text not in (".test_offline", "/test_offline"):
        return

    logger.warning("🧪 收到 test_offline 命令，模拟 bot_offline 事件...")
    await bot.send(event=event, message="🧪 触发 bot_offline 事件，Bot 即将退出重启...")
    await asyncio.sleep(1)
    fake_event = NoticeEvent(
        time=0,
        self_id=int(bot.self_id),
        post_type="notice",
        notice_type="bot_offline",
        user_id=int(bot.self_id),
    )
    await bot.handle_event(fake_event)
