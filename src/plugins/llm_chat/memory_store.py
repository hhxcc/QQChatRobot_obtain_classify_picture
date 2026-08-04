"""长期记忆存储模块 - 基于 sqlite 的持久化记忆（重启不丢）

存储内容:
- person_msgs     原始消息缓冲（持久化，重启后仍可继续蒸馏，防丢失）
- person_profile  群友个人画像（AI 蒸馏结果：性格 / 关系 / 关键事件）
- group_events    群级事件 / 话题归纳

检索:
- 按 (group_id, qq) 精确获取个人画像
- 按关键词（jieba 分词 + 子串匹配）检索画像与群事件
"""

import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Tuple

import jieba
from nonebot import logger

# 每人最多保留多少条原始消息（蒸馏后清空，防止无限增长）
_MAX_RAW_PER_PERSON = 100


class MemoryStore:
    """长期记忆持久化存储"""

    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS person_msgs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            qq INTEGER NOT NULL,
            nickname TEXT DEFAULT '',
            text TEXT NOT NULL,
            ts REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_person_msgs ON person_msgs(group_id, qq);

        CREATE TABLE IF NOT EXISTS person_profile (
            group_id INTEGER NOT NULL,
            qq INTEGER NOT NULL,
            nickname TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            relationship TEXT DEFAULT '',
            key_events TEXT DEFAULT '',
            updated_at REAL NOT NULL,
            PRIMARY KEY (group_id, qq)
        );

        CREATE TABLE IF NOT EXISTS group_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            title TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            happened_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_group_events ON group_events(group_id);
        """)
        self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # ── 原始消息（蒸馏输入）──

    def append_message(self, group_id: int, qq: int, nickname: str, text: str):
        """记录一条原始消息（供蒸馏），并裁剪该人的最旧记录"""
        self._conn.execute(
            "INSERT INTO person_msgs(group_id, qq, nickname, text, ts) VALUES (?,?,?,?,?)",
            (group_id, qq, nickname, text, time.time()),
        )
        self._conn.execute(
            """
            DELETE FROM person_msgs WHERE id IN (
                SELECT id FROM person_msgs
                WHERE group_id=? AND qq=?
                ORDER BY id DESC LIMIT -1 OFFSET ?
            )
            """,
            (group_id, qq, _MAX_RAW_PER_PERSON),
        )
        self._conn.commit()

    def pending_count(self, group_id: int, qq: int) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM person_msgs WHERE group_id=? AND qq=?",
            (group_id, qq),
        )
        return cur.fetchone()[0]

    def pending_people(self, min_msgs: int = 1) -> List[Tuple[int, int, str, int]]:
        """返回待蒸馏的 (group_id, qq, nickname, 条数)，按条数降序"""
        cur = self._conn.execute(
            """
            SELECT group_id, qq, nickname, COUNT(*) AS cnt
            FROM person_msgs
            GROUP BY group_id, qq
            HAVING cnt >= ?
            ORDER BY cnt DESC
            """,
            (min_msgs,),
        )
        return [(r[0], r[1], r[2] or "", r[3]) for r in cur.fetchall()]

    def pop_pending(self, group_id: int, qq: int, limit: int = 40) -> List[str]:
        """取出并删除某人的待蒸馏消息（按时间顺序），返回文本列表"""
        cur = self._conn.execute(
            """
            SELECT id, text FROM person_msgs
            WHERE group_id=? AND qq=?
            ORDER BY id ASC LIMIT ?
            """,
            (group_id, qq, limit),
        )
        rows = cur.fetchall()
        if not rows:
            return []
        ids = [r[0] for r in rows]
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"DELETE FROM person_msgs WHERE id IN ({placeholders})", ids
        )
        self._conn.commit()
        return [r[1] for r in rows]

    def recent_group_texts(self, group_id: int, limit: int = 30) -> List[str]:
        """取群内最近若干条原始消息（用于群事件归纳）"""
        cur = self._conn.execute(
            """
            SELECT text FROM person_msgs
            WHERE group_id=?
            ORDER BY id DESC LIMIT ?
            """,
            (group_id, limit),
        )
        return [r[0] for r in cur.fetchall()]

    def pending_group_ids(self) -> List[int]:
        """返回有原始消息的群号列表"""
        cur = self._conn.execute("SELECT DISTINCT group_id FROM person_msgs")
        return [r[0] for r in cur.fetchall()]

    # ── 个人画像 ──

    def upsert_profile(
        self,
        group_id: int,
        qq: int,
        nickname: str,
        summary: str,
        relationship: str,
        key_events: str,
    ):
        """写入 / 更新群友画像"""
        self._conn.execute(
            """
            INSERT INTO person_profile(group_id, qq, nickname, summary, relationship, key_events, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(group_id, qq) DO UPDATE SET
                nickname=excluded.nickname,
                summary=excluded.summary,
                relationship=excluded.relationship,
                key_events=excluded.key_events,
                updated_at=excluded.updated_at
            """,
            (group_id, qq, nickname, summary, relationship, key_events, time.time()),
        )
        self._conn.commit()

    def get_profile(self, group_id: int, qq: int) -> Optional[dict]:
        """按 (group_id, qq) 精确获取画像"""
        cur = self._conn.execute(
            """
            SELECT nickname, summary, relationship, key_events, updated_at
            FROM person_profile WHERE group_id=? AND qq=?
            """,
            (group_id, qq),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "nickname": row[0] or "",
            "summary": row[1] or "",
            "relationship": row[2] or "",
            "key_events": row[3] or "",
            "updated_at": row[4],
        }

    def search_profiles(self, group_id: int, query: str, top_k: int = 3) -> List[dict]:
        """按关键词检索群内画像（命中昵称/性格/关系/事件）"""
        words = self._tokenize(query)
        if not words:
            return []
        cur = self._conn.execute(
            "SELECT nickname, summary, relationship, key_events "
            "FROM person_profile WHERE group_id=?",
            (group_id,),
        )
        scored = []
        for nickname, summary, relationship, key_events in cur.fetchall():
            hay = f"{nickname} {summary} {relationship} {key_events}"
            score = sum(1 for w in words if w in hay)
            if score > 0:
                scored.append(
                    (
                        score,
                        {
                            "nickname": nickname or "",
                            "summary": summary or "",
                            "relationship": relationship or "",
                            "key_events": key_events or "",
                        },
                    )
                )
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:top_k]]

    # ── 群级事件 ──

    def add_group_event(self, group_id: int, title: str, summary: str):
        """新增群级事件，每群最多保留 30 条"""
        self._conn.execute(
            "INSERT INTO group_events(group_id, title, summary, happened_at) VALUES (?,?,?,?)",
            (group_id, title, summary, time.time()),
        )
        self._conn.execute(
            """
            DELETE FROM group_events WHERE id IN (
                SELECT id FROM group_events WHERE group_id=?
                ORDER BY id DESC LIMIT -1 OFFSET 30
            )
            """,
            (group_id,),
        )
        self._conn.commit()

    def search_group_events(self, group_id: int, query: str, top_k: int = 3) -> List[dict]:
        """按关键词检索群事件"""
        words = self._tokenize(query)
        if not words:
            return []
        cur = self._conn.execute(
            "SELECT title, summary, happened_at FROM group_events WHERE group_id=?",
            (group_id,),
        )
        scored = []
        for title, summary, happened_at in cur.fetchall():
            hay = f"{title} {summary}"
            score = sum(1 for w in words if w in hay)
            if score > 0:
                scored.append(
                    (
                        score,
                        {
                            "title": title or "",
                            "summary": summary or "",
                            "happened_at": happened_at,
                        },
                    )
                )
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:top_k]]

    def stats(self) -> dict:
        """返回记忆库统计（供 /status 与日志）"""
        try:
            cur = self._conn.execute("SELECT COUNT(*) FROM person_profile")
            profiles = cur.fetchone()[0]
            cur = self._conn.execute("SELECT COUNT(*) FROM group_events")
            events = cur.fetchone()[0]
            cur = self._conn.execute("SELECT COUNT(*) FROM person_msgs")
            pending = cur.fetchone()[0]
        except Exception:
            profiles = events = pending = 0
        return {"profiles": profiles, "events": events, "pending": pending}

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        words = set(jieba.cut_for_search(text))
        return [w.strip() for w in words if len(w.strip()) > 1]
