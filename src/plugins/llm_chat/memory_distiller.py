"""记忆蒸馏模块 - 用独立（可更便宜）模型把原始消息提炼为长期记忆

触发方式（两种）:
1. 消息量：某群友累计消息达到阈值 → 蒸馏个人画像
2. 定时兜底：后台任务周期性蒸馏所有待处理对象（个人 + 群级事件）

模型解耦: 蒸馏使用独立 LLM 客户端（见 __init__.py 构建），
可在 .env 中一行切换更便宜的模型，不占用聊天调用。
"""

import asyncio
import json
from typing import List, Optional

from nonebot import logger

from .llm_client import LLMClient
from .memory_store import MemoryStore


class MemoryDistiller:
    """长期记忆蒸馏器"""

    def __init__(
        self,
        client: Optional[LLMClient],
        store: Optional[MemoryStore],
        threshold: int = 30,
    ):
        self._client = client
        self._store = store
        self._threshold = max(2, threshold)
        # 本轮进程内已归纳过群事件的群（避免重复归纳）
        self._summarized_groups: set = set()

    @property
    def is_ready(self) -> bool:
        return self._client is not None and self._store is not None

    def should_distill_person(self, group_id: int, qq: int) -> bool:
        """判断某群友是否达到消息量阈值，需要蒸馏"""
        if self._store is None:
            return False
        return self._store.pending_count(group_id, qq) >= self._threshold

    # ── 个人画像蒸馏 ──

    async def distill_person(
        self, group_id: int, qq: int, nickname: str = ""
    ) -> bool:
        """蒸馏某群友的个人画像（取出待蒸馏消息 → LLM 提炼 → 写入）"""
        if not self.is_ready or self._store is None:
            return False
        texts = self._store.pop_pending(group_id, qq, limit=self._threshold)
        if not texts:
            return False
        sample = "\n".join(f"- {t[:120]}" for t in texts[: self._threshold])
        prompt = (
            "你是群聊机器人「羽毛笔」的记忆管理助手。根据下面某位群友最近的发言，"
            "提炼出对他的长期记忆画像，用于机器人未来与他更自然地相处。\n\n"
            f"群号: {group_id}\n群友QQ: {qq}\n昵称: {nickname or '未知'}\n\n"
            f"他最近的发言：\n{sample}\n\n"
            "请只输出一个 JSON 对象（不要多余文字），字段：\n"
            '{"nickname": "常用昵称", '
            '"summary": "性格与整体印象，一两句话，第三人称", '
            '"relationship": "他对机器人的态度以及机器人与他的关系，一两句话", '
            '"key_events": ["重要事件1", "重要事件2"]}'
        )
        try:
            result = await asyncio.wait_for(
                self._client.chat([{"role": "user", "content": prompt}]),
                timeout=60.0,
            )
        except Exception as e:
            logger.warning(f"[记忆] 蒸馏 API 失败 | qq={qq}: {e}")
            return False

        data = self._parse_json(result)
        if not data:
            logger.debug(f"[记忆] 蒸馏输出非 JSON，跳过: {str(result)[:80]}")
            return False

        summary = str(data.get("summary") or "").strip()
        relationship = str(data.get("relationship") or "").strip()
        events = data.get("key_events") or []
        if isinstance(events, str):
            events = [events]
        key_events = "\n".join(
            f"- {e}" for e in events if str(e).strip()
        )
        out_nickname = str(data.get("nickname") or nickname or "").strip()

        self._store.upsert_profile(
            group_id, qq, out_nickname, summary, relationship, key_events
        )
        logger.info(
            f"[记忆] 已蒸馏群友画像 | group={group_id} qq={qq} "
            f"nick={out_nickname} | {len(texts)} 条消息"
        )
        return True

    # ── 群级事件归纳 ──

    async def distill_group_events(self, group_id: int) -> bool:
        """归纳群内值得长期记住的事件 / 话题"""
        if not self.is_ready or self._store is None:
            return False
        texts = self._store.recent_group_texts(group_id, limit=30)
        if len(texts) < 5:
            return False
        sample = "\n".join(f"- {t[:120]}" for t in texts)
        prompt = (
            "你是群聊机器人「羽毛笔」的记忆管理助手。根据下面的群聊片段，"
            "归纳出值得长期记住的群级事件或持续话题（如某群友的常用昵称、"
            "最近发生的重要事情、群里的梗等）。\n\n"
            f"群号: {group_id}\n最近发言片段：\n{sample}\n\n"
            "请只输出一个 JSON 数组（不要多余文字），每项："
            '{"title": "事件/话题名", "summary": "一句话摘要"}。'
            "若没有值得记住的，输出 []。"
        )
        try:
            result = await asyncio.wait_for(
                self._client.chat([{"role": "user", "content": prompt}]),
                timeout=60.0,
            )
        except Exception as e:
            logger.warning(f"[记忆] 群事件归纳 API 失败 | group={group_id}: {e}")
            return False

        items = self._parse_json(result)
        if not isinstance(items, list):
            return False
        added = 0
        for item in items[:3]:
            title = str(item.get("title") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if title and summary:
                self._store.add_group_event(group_id, title, summary)
                added += 1
        if added:
            self._summarized_groups.add(group_id)
            logger.info(f"[记忆] 已归纳群事件 | group={group_id} | {added} 条")
        return added > 0

    # ── 定时兜底 ──

    async def flush_all(self) -> None:
        """定时兜底：蒸馏所有待处理个人与群事件（分批，防阻塞）"""
        if not self.is_ready:
            return
        # 个人画像：优先处理达到阈值的，其次处理累积较多的
        people = self._store.pending_people(min_msgs=1)
        for group_id, qq, nickname, cnt in people[:5]:
            if cnt >= self._threshold or cnt >= max(5, self._threshold // 2):
                await self.distill_person(group_id, qq, nickname)
            await asyncio.sleep(0.2)
        # 群级事件：未归纳过的群
        for group_id in self._store.pending_group_ids():
            if group_id in self._summarized_groups:
                continue
            if self._store.recent_group_texts(group_id, limit=5):
                await self.distill_group_events(group_id)
            await asyncio.sleep(0.2)

    @staticmethod
    def _parse_json(text: Optional[str]):
        """容错解析 LLM 返回的 JSON（容忍 ```json 包裹 / 前后杂文）"""
        text = (text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            return json.loads(text)
        except Exception:
            try:
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    return json.loads(text[start : end + 1])
            except Exception:
                pass
            return None
