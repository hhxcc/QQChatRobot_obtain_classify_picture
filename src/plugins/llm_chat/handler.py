"""群消息处理器 - 监听文字消息并交由 LLM 决策回复"""

import asyncio
import time
from collections import defaultdict, deque
from typing import Dict, Set

from nonebot import on_message, logger, get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.rule import Rule

from .config import Config
from .llm_client import LLMClient
from .knowledge_store import KnowledgeStore
from .scene_detector import SceneDetector


# 获取全局配置
_driver = get_driver()
_plugin_config: Config = Config()
_llm_client: LLMClient | None = None
_knowledge_store: KnowledgeStore | None = None
_scene_detector: SceneDetector | None = None


def _set_knowledge_store(store: KnowledgeStore | None):
    """由 __init__.py 在启动时注入知识库实例"""
    global _knowledge_store
    _knowledge_store = store


def _set_scene_detector(detector: SceneDetector | None):
    """由 __init__.py 在启动时注入场景检测器实例"""
    global _scene_detector
    _scene_detector = detector


def _init_config(existing_config: Config | None = None):
    """延迟初始化配置（由 __init__.py 的 on_startup 调用）
    
    Args:
        existing_config: 已在 on_startup 中加载好（含文件提示词）的配置。
                         如果提供则直接使用，不再重新从 driver.config 读取。
    """
    global _plugin_config
    if existing_config is not None:
        _plugin_config = existing_config
        return
    try:
        config_dict = {
            k: getattr(_driver.config, k, v.default)
            for k, v in Config.model_fields.items()
        }
        _plugin_config = Config(**config_dict)
    except Exception:
        logger.warning("无法解析 LLM 插件配置，使用默认值")


async def _init_client():
    """初始化 LLM 客户端"""
    global _llm_client

    api_key = _plugin_config.deepseek_api_key
    if not api_key or api_key in ("your-api-key-here", "sk-xxxxxxxx"):
        logger.warning(
            "DEEPSEEK_API_KEY 未配置或为占位值，LLM 聊天功能已禁用。"
            "请在 .env 中设置有效的 API Key。"
        )
        return

    _llm_client = LLMClient(
        api_key=api_key,
        base_url=_plugin_config.deepseek_base_url,
        model=_plugin_config.deepseek_model,
        system_prompt=_plugin_config.llm_system_prompt,
        temperature=_plugin_config.llm_temperature,
        max_tokens=_plugin_config.llm_max_tokens,
    )
    logger.info(
        f"LLM 客户端已初始化: model={_plugin_config.deepseek_model}, "
        f"max_history={_plugin_config.llm_max_history}"
    )
    prompt_preview = _plugin_config.llm_system_prompt[:80].replace("\n", " ")
    logger.info(f"系统提示词: {prompt_preview}... ({len(_plugin_config.llm_system_prompt)} 字符)")


# ── 每群状态 ──
_group_histories: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
# 消息缓冲区: {group_id: [{"name":..., "text":..., "formatted":...}, ...]}
_message_buffer: Dict[int, list] = defaultdict(list)
# 冷却时间: {group_id: current_cd_seconds}
_current_cd: Dict[int, float] = defaultdict(lambda: 8.0)
# 上次 LLM 动作时间戳: {group_id: timestamp}
_last_action_time: Dict[int, float] = {}
# 并发防护
_in_flight: Set[int] = set()


# ── 辅助函数 ──

def _update_deque(group_id: int):
    """确保 deque 大小跟随配置"""
    history = _group_histories[group_id]
    if history.maxlen != _plugin_config.llm_max_history:
        _group_histories[group_id] = deque(
            list(history), maxlen=_plugin_config.llm_max_history
        )


def _is_mentioned(event: GroupMessageEvent) -> bool:
    """检查消息是否 @ 了机器人"""
    at_segments = [seg for seg in event.message if seg.type == "at"]
    return any(seg.data.get("qq") == str(event.self_id) for seg in at_segments)


async def _call_llm(group_id: int, history: deque) -> str | None:
    """调用 LLM，返回回复文本或 None（自动注入知识库检索结果）"""
    _in_flight.add(group_id)
    try:
        # ── 知识库检索 ──
        messages = list(history)
        if _knowledge_store and _knowledge_store.is_ready:
            # 取最近几条消息作为搜索查询
            recent = [m["content"] for m in messages[-5:] if m["role"] == "user"]
            query = " ".join(recent)
            chunks = _knowledge_store.search(query, top_k=3)
            if chunks:
                knowledge_text = "\n".join(
                    f"【{c.title}】{c.content[:400]}" for c in chunks
                )
                # 将知识作为 system 消息注入（插在历史最前面）
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": (
                            "以下是与当前对话相关的参考知识，"
                            "请根据角色人设选择性参考，不相关则忽略:\n"
                            + knowledge_text
                        ),
                    },
                )
                logger.debug(
                    f"[LLM] 知识库命中 | group={group_id} | "
                    f"query={query[:40]}... | {len(chunks)} 块"
                )

        # ── 场景检测（P3）──
        if _scene_detector and _scene_detector.is_ready:
            scene_contexts = _scene_detector.detect(query)
            if scene_contexts:
                combined = "\n".join(scene_contexts)
                messages.insert(
                    0,
                    {"role": "system", "content": combined},
                )
                logger.debug(
                    f"[LLM] 场景命中 | group={group_id} | "
                    f"{len(scene_contexts)} 个场景"
                )

        reply = await asyncio.wait_for(
            _llm_client.chat(messages),
            timeout=15.0,
        )
        return reply
    except asyncio.TimeoutError:
        logger.warning(f"[LLM] API 超时 | group={group_id}")
        return None
    except Exception as e:
        logger.error(f"[LLM] API 异常: {e}")
        return None
    finally:
        _in_flight.discard(group_id)


async def _send_if_valid(
    bot: Bot, group_id: int, reply: str | None, history: deque
) -> bool:
    """发送回复（若非 SKIP），返回是否实际发送"""
    if reply is None:
        return False
    reply = reply.strip()
    if reply.upper() == "[SKIP]":
        logger.info(f"[LLM] 决策跳过 | group={group_id}")
        return False
    try:
        await bot.send_group_msg(group_id=group_id, message=reply)
        logger.info(f"[LLM] 已回复 | group={group_id} | {reply[:60]}")
        history.append({"role": "assistant", "content": reply})
        return True
    except Exception as e:
        logger.error(f"[LLM] 发送失败: {e}")
        return False


def _update_cd(group_id: int, did_reply: bool):
    """更新冷却时间：回复→累加, SKIP→衰减"""
    base = _plugin_config.llm_cooldown_base
    ceiling = _plugin_config.llm_cooldown_ceiling
    current = _current_cd.get(group_id, base)
    if did_reply:
        new_cd = min(current + base, ceiling)
    else:
        new_cd = max(current / 2, base)
    _current_cd[group_id] = new_cd
    _last_action_time[group_id] = time.time()


# ── 事件处理器 ──

group_msg = on_message(rule=Rule(lambda event: isinstance(event, GroupMessageEvent)))


@group_msg.handle()
async def handle_group_message(bot: Bot, event: GroupMessageEvent):
    """缓冲 + 动态冷却 状态机"""
    if _llm_client is None:
        return
    if event.user_id == event.self_id:
        return

    group_id = event.group_id
    if (
        _plugin_config.llm_target_groups
        and group_id not in _plugin_config.llm_target_groups
    ):
        return

    # 提取文字
    text_segments = [seg for seg in event.message if seg.type == "text"]
    if not text_segments:
        return
    sender_name = event.sender.card or event.sender.nickname or str(event.user_id)
    raw_text = "".join(seg.data.get("text", "") for seg in text_segments).strip()
    if not raw_text:
        return
    if len(raw_text) < 2 and not raw_text.isalpha():
        return

    formatted = f"{sender_name}: {raw_text}"
    mentioned = _is_mentioned(event)

    # ── 情况⑤: @mention → 立刻回复，重置 CD ──
    if mentioned:
        logger.info(f"[LLM] @提及 | group={group_id} | {formatted[:60]}")
        _update_deque(group_id)
        history = _group_histories[group_id]

        # 清空缓冲区也一起发给 LLM（提供上下文）
        buf = _message_buffer.get(group_id, [])
        if buf:
            buf_text = "\n".join(m["formatted"] for m in buf)
            history.append({"role": "user", "content": buf_text})
            _message_buffer[group_id] = []
        history.append({"role": "user", "content": formatted})

        reply = await _call_llm(group_id, history)
        did_reply = await _send_if_valid(bot, group_id, reply, history)
        # @mention 回复后将 CD 重置为基准值
        _current_cd[group_id] = _plugin_config.llm_cooldown_base
        _last_action_time[group_id] = time.time()
        return

    # ── 情况: LLM 调用进行中 → 消息进缓冲区 ──
    if group_id in _in_flight:
        _message_buffer[group_id].append(
            {"name": sender_name, "text": raw_text, "formatted": formatted}
        )
        _trim_buffer(group_id)
        return

    # ── CD 检查 ──
    base = _plugin_config.llm_cooldown_base
    current_cd = _current_cd.get(group_id, base)
    last_time = _last_action_time.get(group_id, 0)
    cd_expired = (time.time() - last_time) >= current_cd

    if cd_expired:
        # ── CD 到期 → 处理缓冲区 + 当前消息 ──
        _update_deque(group_id)
        history = _group_histories[group_id]
        buf = _message_buffer.get(group_id, [])
        _message_buffer[group_id] = []

        if buf:
            # 情况③: 缓冲区有积压消息，一起发给 LLM
            lines = [m["formatted"] for m in buf]
            lines.append(formatted)
            combined = "\n".join(lines)
            logger.info(
                f"[LLM] 缓冲释放 | group={group_id} | {len(lines)} 条消息"
            )
        else:
            # 情况①: 缓冲区空，单条消息
            combined = formatted
            logger.info(f"[LLM] 收到消息 | group={group_id} | {formatted[:80]}")

        history.append({"role": "user", "content": combined})
        reply = await _call_llm(group_id, history)
        did_reply = await _send_if_valid(bot, group_id, reply, history)
        _update_cd(group_id, did_reply)
    else:
        # ── 情况②/④: CD 未到期 → 消息进缓冲区 ──
        _message_buffer[group_id].append(
            {"name": sender_name, "text": raw_text, "formatted": formatted}
        )
        _trim_buffer(group_id)
        remaining = int(current_cd - (time.time() - last_time))
        logger.debug(
            f"[LLM] 缓冲 | group={group_id} | "
            f"CD剩余={remaining}s | 缓冲={len(_message_buffer[group_id])}条"
        )


def _trim_buffer(group_id: int):
    """裁剪超出上限的缓冲消息"""
    buf = _message_buffer[group_id]
    limit = _plugin_config.llm_buffer_max
    if len(buf) > limit:
        _message_buffer[group_id] = buf[-limit:]
