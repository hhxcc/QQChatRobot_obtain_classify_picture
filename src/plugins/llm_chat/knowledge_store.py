"""知识库检索模块 - 基于 FTS5 + YAML frontmatter 的双层检索

目录结构:
knowledge/
├── manifest.yaml         ← 全局配置
├── 主题目录/
│   └── 知识文件.txt      ← YAML frontmatter + Markdown 正文

检索流程:
1. 消息分词 → 精准匹配 frontmatter keywords (标签层)
2. 未命中或不足 Top-K → FTS5 模糊全文搜索 (兜底层)
3. 合并结果，按 priority + fts5 score 排序，返回 Top-K
"""

import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

import jieba
import yaml
from nonebot import logger


# ── 数据结构 ──

@dataclass
class KnowledgeChunk:
    """单个知识块"""
    file_path: str       # 源文件相对路径
    topic: str           # 所属主题
    title: str           # 标题
    content: str         # 正文
    keywords: List[str]  # 关键词列表
    priority: int = 5    # 优先级 1-10
    score: float = 0.0   # 搜索匹配分数


# ── YAML frontmatter 解析 ──

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> Tuple[dict, str]:
    """解析 YAML frontmatter，返回 (元数据, 正文)"""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    body = text[match.end():].strip()
    return meta, body


# ── 知识库存储 ──

class KnowledgeStore:
    """知识库存储与检索引擎"""

    def __init__(self, knowledge_dir: str = "knowledge"):
        self.knowledge_dir = Path(knowledge_dir).resolve()
        self._conn: Optional[sqlite3.Connection] = None
        self._chunks: Dict[int, KnowledgeChunk] = {}  # rowid → chunk

    # ── 索引构建 ──

    def build_index(self) -> bool:
        """扫描 knowledge/ 目录，解析文件，构建 FTS5 索引

        Returns:
            bool: 是否成功构建
        """
        if not self.knowledge_dir.exists():
            logger.error(f"知识库目录不存在: {self.knowledge_dir}")
            return False

        manifest = self._load_manifest()
        if manifest is None:
            return False

        topic_configs = manifest.get("topics", [])
        search_config = manifest.get("search", {})

        # 内存数据库，启动时重建
        self._conn = sqlite3.connect(":memory:")
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
            USING fts5(title, content, keywords, tokenize='unicode61')
        """)
        self._chunks.clear()

        # 扫描每个主题目录
        topic_priority = {t["dir"]: t.get("priority", 5) for t in topic_configs}
        total_files = 0
        total_chunks = 0

        for topic_cfg in topic_configs:
            topic_dir = self.knowledge_dir / topic_cfg["dir"]
            topic_name = topic_cfg.get("name", topic_cfg["dir"])
            if not topic_dir.exists():
                logger.warning(f"主题目录不存在，跳过: {topic_dir}")
                continue

            for file_path in topic_dir.glob("*"):
                if file_path.suffix not in (".txt", ".md"):
                    continue
                total_files += 1
                chunks = self._parse_file(file_path, topic_name, topic_priority)
                for chunk in chunks:
                    row_id = self._insert_chunk(chunk)
                    self._chunks[row_id] = chunk
                    total_chunks += 1

        logger.info(
            f"知识库索引构建完成: {total_files} 文件, "
            f"{total_chunks} 知识块, {self.knowledge_dir}"
        )
        return total_chunks > 0

    def _load_manifest(self) -> Optional[dict]:
        """加载 manifest.yaml"""
        manifest_path = self.knowledge_dir / "manifest.yaml"
        if not manifest_path.exists():
            logger.error(f"manifest 文件不存在: {manifest_path}")
            return None
        try:
            return yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"解析 manifest.yaml 失败: {e}")
            return None

    def _parse_file(
        self, file_path: Path, topic_name: str, topic_priority: Dict[str, int]
    ) -> List[KnowledgeChunk]:
        """解析单个知识文件为知识块列表"""
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"读取文件失败: {file_path}, {e}")
            return []

        meta, body = _parse_frontmatter(text)
        if not body:
            return []

        # 获取 frontmatter 字段
        title = meta.get("title", file_path.stem)
        keywords = meta.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",")]
        priority = meta.get("priority",
                           topic_priority.get(topic_name.split("/")[-1], 5))

        # 按 ## 标题分块（保留段落完整性）
        chunks = self._split_body(body, title, keywords, priority,
                                  file_path, topic_name)
        return chunks

    def _split_body(
        self, body: str, title: str, keywords: List[str], priority: int,
        file_path: Path, topic_name: str
    ) -> List[KnowledgeChunk]:
        """按 ## 标题将正文拆分为多个知识块"""
        sections = re.split(r"\n(?=##\s)", body)
        chunks = []
        rel_path = str(file_path.relative_to(self.knowledge_dir.parent)
                      if self.knowledge_dir.parent in file_path.parents
                      else file_path.name)

        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue
            # 提取子标题
            sub_match = re.match(r"##\s+(.+)", section)
            sub_title = sub_match.group(1).strip() if sub_match else title
            chunk_title = f"{title} › {sub_title}" if sub_title != title else title

            chunks.append(KnowledgeChunk(
                file_path=rel_path,
                topic=topic_name,
                title=chunk_title,
                content=section,
                keywords=keywords,
                priority=priority,
            ))
        return chunks

    def _insert_chunk(self, chunk: KnowledgeChunk) -> int:
        """将知识块插入 FTS5 索引，返回 rowid"""
        keywords_str = " ".join(chunk.keywords)
        cur = self._conn.execute(
            "INSERT INTO knowledge_fts(title, content, keywords) VALUES (?, ?, ?)",
            (chunk.title, chunk.content, keywords_str)
        )
        return cur.lastrowid

    # ── 检索 ──

    def search(self, query: str, top_k: int = 3) -> List[KnowledgeChunk]:
        """双层检索：关键词精准匹配 + FTS5 模糊搜索

        Args:
            query: 搜索查询（群聊消息文本）
            top_k: 最多返回块数

        Returns:
            按 priority + score 排序的知识块列表
        """
        if not self._conn or not self._chunks:
            return []

        # 分词 + 去重
        words = list(set(jieba.cut_for_search(query)))
        words = [w.strip() for w in words if len(w.strip()) > 1]

        if not words:
            return []

        results: Dict[int, float] = {}

        # ── Layer 1: 关键词精准匹配 ──
        for row_id, chunk in self._chunks.items():
            matched = sum(1 for kw in chunk.keywords if kw in words or kw in query)
            if matched > 0:
                results[row_id] = matched * 10.0  # 精准匹配权重高

        # ── Layer 2: FTS5 模糊全文搜索 ──
        fts_query = " OR ".join(f'"{w}"' for w in words[:10])
        try:
            cur = self._conn.execute(
                "SELECT rowid, rank FROM knowledge_fts WHERE knowledge_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (fts_query, top_k * 2)
            )
            for row_id, rank in cur.fetchall():
                # FTS5 rank 是负值，越小（越负）匹配度越高
                fts_score = abs(rank) if rank else 0
                results[row_id] = results.get(row_id, 0) + fts_score
        except sqlite3.OperationalError as e:
            logger.debug(f"FTS5 搜索语法错误（自动忽略）: {e}")

        # ── 合并排序 ──
        ranked = []
        for row_id, score in results.items():
            if row_id in self._chunks:
                chunk = self._chunks[row_id]
                chunk.score = score
                ranked.append(chunk)

        # 按 (priority * 100 + score) 降序
        ranked.sort(key=lambda c: (c.priority * 100 + c.score), reverse=True)
        return ranked[:top_k]

    # ── 状态 ──

    @property
    def is_ready(self) -> bool:
        return self._conn is not None and len(self._chunks) > 0

    def stats(self) -> dict:
        return {
            "total_files": len(set(c.file_path for c in self._chunks.values())),
            "total_chunks": len(self._chunks),
            "topics": list(set(c.topic for c in self._chunks.values())),
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
