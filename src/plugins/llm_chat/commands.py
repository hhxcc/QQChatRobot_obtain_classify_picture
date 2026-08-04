"""群聊指令处理器 - 响应以 / 开头的群聊命令"""

import time
from typing import Dict, Set, Callable
from collections import deque

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

from .knowledge_store import KnowledgeStore
from .vision.commands import handle_vision_command

# ── 可用指令注册表 ──
COMMANDS: Dict[str, str] = {
    "clear": "清除当前群的对话记忆",
    "help": "显示所有可用指令",
    "memory": "检索知识库记忆：/memory <关键词>",
    "pause": "暂停在此群的自动回复",
    "resume": "恢复在此群的自动回复",
    "status": "查看当前群的状态信息",
    "vision": "视觉开关：/vision on|off|status",
}


async def handle_slash_command(
    bot: Bot,
    event: GroupMessageEvent,
    raw_text: str,
    group_id: int,
    histories: Dict[int, deque],
    buffers: Dict[int, list],
    cds: Dict[int, float],
    last_action_time: Dict[int, float],
    cd_base: float,
    pause_set: Set[int],
    knowledge_store: KnowledgeStore | None,
    cancel_flush: Callable[[int], None] | None = None,
) -> bool:
    """处理以 / 开头的群聊指令。

    Args:
        bot: OneBot 实例
        event: 群消息事件
        raw_text: 原始文本（含 /）
        group_id: 群号
        histories: 群聊历史字典
        buffers: 消息缓冲字典
        cds: 冷却时间字典
        pause_set: 暂停群集合
        knowledge_store: 知识库实例（可选）
        last_action_time: 上次动作时间戳字典
        cd_base: 冷却时间基准值

    Returns:
        True 表示已处理（阻断后续 LLM 流程），False 表示未识别
    """
    cmd_line = raw_text[1:].strip()
    if not cmd_line:
        return False

    parts = cmd_line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd not in COMMANDS:
        return False  # 未知指令，交给 LLM 处理

    # ── /clear ──
    if cmd == "clear":
        histories[group_id].clear()
        buffers[group_id] = []
        cds[group_id] = 8.0
        if cancel_flush:
            cancel_flush(group_id)
        logger.info(f"[CMD] /clear | group={group_id}")
        await bot.send_group_msg(
            group_id=group_id,
            message="唔，刚才聊到哪了？我都忘掉啦。",
        )
        return True

    # ── /help ──
    if cmd == "help":
        lines = ["可用的指令："]
        for name, desc in COMMANDS.items():
            lines.append(f"/{name} — {desc}")
        await bot.send_group_msg(
            group_id=group_id,
            message="\n".join(lines),
        )
        return True

    # ── /memory <关键词> ──
    if cmd == "memory":
        if not arg:
            await bot.send_group_msg(
                group_id=group_id,
                message="唔，要检索什么记忆呢？请告诉我关键词哦。",
            )
            return True
        if knowledge_store is None or not knowledge_store.is_ready:
            await bot.send_group_msg(
                group_id=group_id,
                message="......知识库还没有准备好呢。",
            )
            return True

        chunks = knowledge_store.search(arg, top_k=3)
        if not chunks:
            await bot.send_group_msg(
                group_id=group_id,
                message=f"唔，关于「{arg}」......我好像没什么印象。",
            )
        else:
            results = []
            for i, c in enumerate(chunks, 1):
                snippet = c.content[:150].replace("\n", " ")
                results.append(f"{i}. 【{c.title}】{snippet}...")
            logger.info(
                f"[CMD] /memory | group={group_id} | "
                f"query={arg} | {len(chunks)} hits"
            )
            await bot.send_group_msg(
                group_id=group_id,
                message=f"关于「{arg}」，我想起这些：\n\n" + "\n\n".join(results),
            )
        return True

    # ── /pause ──
    if cmd == "pause":
        pause_set.add(group_id)
        if cancel_flush:
            cancel_flush(group_id)
        logger.info(f"[CMD] /pause | group={group_id}")
        await bot.send_group_msg(
            group_id=group_id,
            message="好哦，我先安静一会儿。需要我的时候说 /resume 就好。",
        )
        return True

    # ── /resume ──
    if cmd == "resume":
        pause_set.discard(group_id)
        cds[group_id] = 8.0
        logger.info(f"[CMD] /resume | group={group_id}")
        await bot.send_group_msg(
            group_id=group_id,
            message="我回来啦。你们聊到哪了？",
        )
        return True

    # ── /status ──
    if cmd == "status":
        is_paused = group_id in pause_set
        hist_len = len(histories.get(group_id, []))
        buf_len = len(buffers.get(group_id, []))
        current_cd = cds.get(group_id, cd_base)
        last_time = last_action_time.get(group_id, 0)
        remaining = max(0.0, current_cd - (time.time() - last_time))

        lines = [
            f"状态：{'已暂停 ⏸' if is_paused else '运行中 ▶'}",
            f"对话记忆：{hist_len} 条",
            f"缓冲消息：{buf_len} 条",
            f"冷却时间：{current_cd:.0f}s / {cd_base:.0f}s",
        ]
        if not is_paused and remaining > 0:
            lines.append(f"冷却剩余：{remaining:.0f}s")
        if knowledge_store and knowledge_store.is_ready:
            stats = knowledge_store.stats()
            lines.append(f"知识库：{stats.get('total_chunks', '?')} 块")
        else:
            lines.append("知识库：未加载")

        logger.info(f"[CMD] /status | group={group_id}")
        await bot.send_group_msg(
            group_id=group_id,
            message="\n".join(lines),
        )
        return True

    # ── /vision ──
    if cmd == "vision":
        return await handle_vision_command(bot, event, arg)

    return False
