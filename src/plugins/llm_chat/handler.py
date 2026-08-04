"""群消息处理器 - 监听文字消息并交由 LLM 决策回复"""

import asyncio
import time
from collections import defaultdict, deque
from typing import Dict, Set

from nonebot import on_message, logger, get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.rule import Rule

from .config import Config
from .llm_client import LLMClient
from .knowledge_store import KnowledgeStore
from .scene_detector import SceneDetector
from .commands import handle_slash_command
from .vision import get_vision


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
# 上次实际发送回复的时间戳: {group_id: timestamp}
_last_reply_time: Dict[int, float] = {}
# 并发防护
_in_flight: Set[int] = set()
# 暂停群集合
_paused_groups: Set[int] = set()
# 延迟刷新任务: {group_id: asyncio.Task}
_pending_flush: Dict[int, "asyncio.Task"] = {}

# ── 对话模式 / 本地预判 ──
_CONVERSATION_WINDOW = 30.0       # 回复后 30 秒内视为「对话模式」
_SKIP_CD_BOOST = 120.0            # 安静模式下 [SKIP] 后 CD 跳至此值
TOPIC_KEYWORDS = [
    "调酒", "酒吧", "鸡尾酒", "饮品", "龙舌兰酒", "喝一杯", "酒",
    "龙舌兰", "埃内斯托", "潘乔", "哥哥", "爸爸", "养父", "家人",
    "玻利瓦尔", "多索雷斯", "罗德岛",
    "战斗", "打仗", "武器", "战场", "军人", "士兵",
    "紫丁香", "花束",
    "博士",
    "方舟", "干员", "近卫", "术师", "源石", "矿石病", "感染者",
    "羽毛笔", "拉菲艾拉", "拉珐",
]


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


def _in_conversation(group_id: int) -> bool:
    """群当前是否处于「对话模式」（最近刚回复过某人）"""
    last_reply = _last_reply_time.get(group_id, 0)
    return (time.time() - last_reply) < _CONVERSATION_WINDOW


def _should_skip_locally(text: str, group_id: int) -> bool:
    """本地预判：只有四关全部不命中，才确定可以跳过 LLM 调用。
    返回 True 表示「应该跳过」，False 表示「不确定，调 LLM」。
    """
    # 第1关：被叫名字？
    if any(name in text for name in ["羽毛笔", "拉珐", "拉菲艾拉"]):
        return False
    # 第2关：涉及角色相关话题？
    if any(kw in text for kw in TOPIC_KEYWORDS):
        return False
    # 第3关：有人在提问？
    if any(q in text for q in ["?", "？", "吗", "呢", "什么", "怎么", "谁", "哪"]):
        return False
    # 第4关：群冷场了？（超过 2 分钟无人触发）
    if time.time() - _last_action_time.get(group_id, 0) > 120:
        return False
    return True


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
        _last_reply_time[group_id] = time.time()
        return True
    except Exception as e:
        logger.error(f"[LLM] 发送失败: {e}")
        return False


def _update_cd(group_id: int, did_reply: bool):
    """更新冷却时间：
    对话模式 ─ 回复→累加, SKIP→衰减
    安静模式 ─ 回复→累加, SKIP→跳至 _SKIP_CD_BOOST（大幅延长）
    """
    base = _plugin_config.llm_cooldown_base
    ceiling = _plugin_config.llm_cooldown_ceiling
    current = _current_cd.get(group_id, base)
    if did_reply:
        new_cd = min(current + base, ceiling)
    elif _in_conversation(group_id):
        # 对话模式：SKIP 衰减
        new_cd = max(current / 2, base)
    else:
        # 安静模式：SKIP → 大幅 CD，等人主动叫
        new_cd = max(current, _SKIP_CD_BOOST)
    _current_cd[group_id] = new_cd
    _last_action_time[group_id] = time.time()


async def _process_and_reply(
    bot: Bot,
    group_id: int,
    combined: str,
    history: deque,
    skip_local_check: bool = False,
):
    """处理消息并回复（CD 到期后的核心逻辑，供正常流程和延迟刷新复用）

    Args:
        skip_local_check: 是否跳过本地预判（纯图片消息已由视觉决策把关，直接调 LLM）
    """
    in_conv = _in_conversation(group_id)
    if (
        not skip_local_check
        and not in_conv
        and _should_skip_locally(combined, group_id)
    ):
        logger.debug(f"[预判] 跳过 | group={group_id} | {combined[:60]}")
        _current_cd[group_id] = _SKIP_CD_BOOST
        _last_action_time[group_id] = time.time()
        return
    history.append({"role": "user", "content": combined})
    reply = await _call_llm(group_id, history)
    did_reply = await _send_if_valid(bot, group_id, reply, history)
    _update_cd(group_id, did_reply)


def _cancel_pending_flush(group_id: int):
    """取消群的延迟刷新任务"""
    task = _pending_flush.pop(group_id, None)
    if task and not task.done():
        task.cancel()


def _schedule_flush(group_id: int, delay: float, bot: Bot):
    """调度延迟刷新：CD 到期后自动处理缓冲区（解决缓冲卡死问题）"""
    _cancel_pending_flush(group_id)

    async def _delayed():
        await asyncio.sleep(delay)
        if group_id in _in_flight:
            return
        buf = _message_buffer.get(group_id, [])
        if not buf:
            return
        _update_deque(group_id)
        history = _group_histories[group_id]
        lines = [m["formatted"] for m in buf]
        # 缓冲消息全部为纯图时，跳过本地预判（视觉决策已把关）
        all_pure_image = all(m.get("pure_image", False) for m in buf)
        _message_buffer[group_id] = []
        combined = "\n".join(lines)
        logger.info(
            f"[LLM] 延迟刷新 | group={group_id} | {len(lines)} 条消息"
        )
        await _process_and_reply(
            bot, group_id, combined, history, skip_local_check=all_pure_image
        )

    _pending_flush[group_id] = asyncio.create_task(_delayed())


def _clear_group_state(group_id: int):
    """清除群的缓冲、刷新任务和冷却（供 /clear 和 /pause 调用）"""
    _cancel_pending_flush(group_id)
    _message_buffer[group_id] = []
    _current_cd[group_id] = _plugin_config.llm_cooldown_base
    _last_action_time[group_id] = time.time()


# ── 事件处理器 ──

group_msg = on_message(rule=Rule(lambda event: isinstance(event, GroupMessageEvent)))


async def _build_image_context(
    bot: Bot,
    event: GroupMessageEvent,
    image_segments: list,
    *,
    is_mentioned: bool,
    has_text: bool,
    text: str,
) -> str:
    """下载图片并调用视觉服务，返回可注入 LLM 的图片上下文文本。

    仅当视觉开启时被调用；返回空串表示无需附加（下载失败/不值得分析）。
    """
    vision = get_vision()
    if vision is None or not vision.enabled:
        return ""

    seg = image_segments[0]
    url = seg.data.get("url", "")
    if not url:
        return ""

    try:
        img_bytes = await vision.download_image(url, timeout=15)
    except Exception as e:
        logger.warning(f"[Vision] 图片下载失败: {e}")
        return ""

    desc, local = await vision.analyze_image(
        img_bytes,
        is_mentioned=is_mentioned,
        has_text=has_text,
        context=text,
    )

    parts = []
    has_desc = bool(desc and desc.description)
    has_extra = False
    if local:
        if local.has_text:
            parts.append(f"图上文字：{local.ocr_text}")
            has_extra = True
        if local.clip_category and local.clip_category != "其他":
            parts.append(f"图片类别：{local.clip_category}（{local.clip_conf:.0%}）")
            has_extra = True
    if has_desc:
        parts.append(f"画面描述：{desc.description}")
    elif has_extra:
        # 视觉识别失败：明确禁止 LLM 编造画面内容（宁可不回，不瞎猜）
        parts.append(
            "（画面识别失败，请勿猜测或编造画面细节，"
            "仅基于已有信息简单回应，或回复 [SKIP]）"
        )

    if not parts:
        return ""
    return "[发来一张图片]\n" + "\n".join(parts)


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

    # 提取文字与图片
    text_segments = [seg for seg in event.message if seg.type == "text"]
    image_segments = [seg for seg in event.message if seg.type == "image"]
    if not text_segments and not image_segments:
        return
    sender_name = event.sender.card or event.sender.nickname or str(event.user_id)
    raw_text_original = "".join(
        seg.data.get("text", "") for seg in text_segments
    ).strip()

    # ── 视觉：构建图片上下文（有图且视觉开启时）──
    image_context = ""
    pure_image = False
    vision = get_vision()
    if (
        image_segments
        and vision
        and vision.enabled
        and not raw_text_original.startswith("/")
    ):
        image_context = await _build_image_context(
            bot,
            event,
            image_segments,
            is_mentioned=_is_mentioned(event),
            has_text=bool(raw_text_original),
            text=raw_text_original,
        )

    # 纯图片消息：以图片上下文为消息主体（跳过本地预判，由视觉决策把关）
    if not raw_text_original:
        if not image_context:
            return
        raw_text = image_context
        pure_image = True
    else:
        # 图文混发：图片上下文作为附加信息，文字为主
        raw_text = raw_text_original + (
            f"\n{image_context}" if image_context else ""
        )

    if len(raw_text) < 2 and not raw_text.isalpha():
        return

    formatted = f"{sender_name}: {raw_text}"
    mentioned = _is_mentioned(event)

    # ── / 指令拦截 ──
    if raw_text.startswith("/"):
        handled = await handle_slash_command(
            bot, event, raw_text, group_id,
            _group_histories, _message_buffer, _current_cd,
            _last_action_time, _plugin_config.llm_cooldown_base,
            _paused_groups, _knowledge_store,
            _cancel_pending_flush,
        )
        if handled:
            return

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

    # ── 暂停检查（@mention 之后，/指令和@仍可触发回复）──
    if group_id in _paused_groups:
        return

    # ── 情况: LLM 调用进行中 → 消息进缓冲区 ──
    if group_id in _in_flight:
        _message_buffer[group_id].append(
            {
                "name": sender_name,
                "text": raw_text,
                "formatted": formatted,
                "pure_image": pure_image,
            }
        )
        _trim_buffer(group_id)
        return

    # ── CD 检查 ──
    base = _plugin_config.llm_cooldown_base
    current_cd = _current_cd.get(group_id, base)
    last_time = _last_action_time.get(group_id, 0)
    cd_expired = (time.time() - last_time) >= current_cd

    if cd_expired:
        # ── 取消该群的延迟刷新任务（手动触发了）──
        _cancel_pending_flush(group_id)

        # ── CD 到期 → 处理缓冲区 + 当前消息 ──
        _update_deque(group_id)
        history = _group_histories[group_id]
        buf = _message_buffer.get(group_id, [])
        _message_buffer[group_id] = []

        if buf:
            lines = [m["formatted"] for m in buf]
            lines.append(formatted)
            combined = "\n".join(lines)
            # 仅当缓冲消息与当前消息都是纯图时才跳过本地预判
            pure_image = pure_image and all(
                m.get("pure_image", False) for m in buf
            )
            logger.info(
                f"[LLM] 缓冲释放 | group={group_id} | {len(lines)} 条消息"
            )
        else:
            combined = formatted
            logger.info(f"[LLM] 收到消息 | group={group_id} | {formatted[:80]}")

        await _process_and_reply(
            bot, group_id, combined, history, skip_local_check=pure_image
        )
    else:
        # ── 情况②/④: CD 未到期 → 消息进缓冲区 ──
        _message_buffer[group_id].append(
            {
                "name": sender_name,
                "text": raw_text,
                "formatted": formatted,
                "pure_image": pure_image,
            }
        )
        _trim_buffer(group_id)
        remaining = current_cd - (time.time() - last_time)
        logger.debug(
            f"[LLM] 缓冲 | group={group_id} | "
            f"CD剩余={remaining:.0f}s | 缓冲={len(_message_buffer[group_id])}条"
        )
        # 调度延迟刷新：CD 到期后自动处理缓冲区
        _schedule_flush(group_id, remaining + 0.5, bot)


def _trim_buffer(group_id: int):
    """裁剪超出上限的缓冲消息"""
    buf = _message_buffer[group_id]
    limit = _plugin_config.llm_buffer_max
    if len(buf) > limit:
        _message_buffer[group_id] = buf[-limit:]


# ── 私聊处理器 ──

# 私聊状态（key=user_id）
_private_histories: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
_private_last_action: Dict[int, float] = {}
_private_last_reply: Dict[int, float] = {}
_PRIVATE_CD = 4.0  # 私聊 CD 更短，因为是 1v1

private_msg = on_message(rule=Rule(lambda event: isinstance(event, PrivateMessageEvent)))


@private_msg.handle()
async def handle_private_message(bot: Bot, event: PrivateMessageEvent):
    """私聊消息处理：始终回复，简化缓冲"""
    if _llm_client is None:
        return
    if event.user_id == event.self_id:
        return

    user_id = event.user_id
    text_segments = [seg for seg in event.message if seg.type == "text"]
    if not text_segments:
        return
    raw_text = "".join(seg.data.get("text", "") for seg in text_segments).strip()
    if not raw_text:
        return

    # ── / 指令拦截 ──
    if raw_text.startswith("/"):
        # 私聊中把 user_id 当 group_id 传给指令处理
        handled = await handle_slash_command(
            bot, event, raw_text, user_id,
            _private_histories, {}, _current_cd,
            _private_last_action, _PRIVATE_CD,
            set(), _knowledge_store,
        )
        if handled:
            return

    # ── CD 检查 ──
    last_time = _private_last_action.get(user_id, 0)
    cd_expired = (time.time() - last_time) >= _PRIVATE_CD

    if not cd_expired:
        return  # 私聊不缓冲，直接丢弃（太快就等等）

    # ── 构建历史 ──
    history = _private_histories[user_id]
    if history.maxlen != _plugin_config.llm_max_history:
        _private_histories[user_id] = deque(list(history), maxlen=_plugin_config.llm_max_history)
        history = _private_histories[user_id]

    combined = f"对方: {raw_text}"

    # ── 知识库检索 ──
    messages = list(history)
    if _knowledge_store and _knowledge_store.is_ready:
        recent = [m["content"] for m in messages[-5:] if m["role"] == "user"]
        recent.append(combined)
        query = " ".join(recent)
        chunks = _knowledge_store.search(query, top_k=3)
        if chunks:
            knowledge_text = "\n".join(
                f"【{c.title}】{c.content[:400]}" for c in chunks
            )
            messages.insert(0, {
                "role": "system",
                "content": (
                    "以下是与当前对话相关的参考知识，"
                    "请根据角色人设选择性参考，不相关则忽略:\n"
                    + knowledge_text
                ),
            })

    # ── 场景检测 ──
    if _scene_detector and _scene_detector.is_ready:
        scene_contexts = _scene_detector.detect(combined)
        if scene_contexts:
            messages.insert(0, {"role": "system", "content": "\n".join(scene_contexts)})

    history.append({"role": "user", "content": combined})
    messages.append({"role": "user", "content": combined})

    # ── 调 LLM ──
    try:
        reply = await asyncio.wait_for(
            _llm_client.chat(messages),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[私聊] API 超时 | user={user_id}")
        return
    except Exception as e:
        logger.error(f"[私聊] API 异常: {e}")
        return

    if reply is None:
        return
    reply = reply.strip()
    if reply.upper() == "[SKIP]":
        logger.info(f"[私聊] 决策跳过 | user={user_id}")
        _private_last_action[user_id] = time.time()
        return

    try:
        await bot.send_private_msg(user_id=user_id, message=reply)
        logger.info(f"[私聊] 已回复 | user={user_id} | {reply[:60]}")
        history.append({"role": "assistant", "content": reply})
        _private_last_reply[user_id] = time.time()
    except Exception as e:
        logger.error(f"[私聊] 发送失败: {e}")

    _private_last_action[user_id] = time.time()
