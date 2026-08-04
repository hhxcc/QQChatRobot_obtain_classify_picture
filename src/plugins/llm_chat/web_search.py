"""联网搜索模块 - 免费搜索引擎封装 + Function Calling 工具

引擎: bing(必应, cn.bing.com 中文最友好) | duckduckgo | baidu(百度)

设计:
- 每个引擎暴露一个独立 Function 工具（web_search_bing / web_search_duckduckgo /
  web_search_baidu），模型可在某个引擎没搜到时转向其他引擎。
- 全部免费，靠 HTML 抓取；解析失败时返回空结果（模型会如实说"查不到"）。
"""

import asyncio
import json
import re
import time
import urllib.parse
from typing import List, Optional

import httpx
from nonebot import logger

# 支持的引擎
SUPPORTED_ENGINES = {
    "bing": "必应",
    "duckduckgo": "DuckDuckGo",
    "baidu": "百度",
}


def build_search_tools(enabled: bool = True) -> List[dict]:
    """构建 Function Calling 工具定义（每个引擎一个函数）"""
    if not enabled:
        return []
    tools = []
    for name, label in SUPPORTED_ENGINES.items():
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": f"web_search_{name}",
                    "description": (
                        f"使用{label}在互联网上搜索百科、资料、新闻或最新信息，"
                        "返回若干条网页标题与摘要。当你不确定答案、知识库没有相关内容、"
                        "或需要核实最新信息时使用。若某个引擎没搜到，可改用其他搜索函数。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "要搜索的关键词或问题（中文优先）",
                            }
                        },
                        "required": ["query"],
                    },
                },
            }
        )
    return tools


class WebSearcher:
    """免费搜索引擎封装（带内存缓存，同类问题短时间不重复搜）"""

    def __init__(
        self,
        engine: str = "bing",
        result_count: int = 5,
        timeout: float = 8.0,
        cache_ttl: int = 300,
    ):
        self.engine = engine if engine in SUPPORTED_ENGINES else "bing"
        self.result_count = max(1, min(10, result_count))
        self.timeout = timeout
        self.cache_ttl = max(0, cache_ttl)
        # {(engine, query): (时间戳, results)}
        self._cache: dict = {}
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            follow_redirects=True,
        )

    async def search(self, query: str, engine: Optional[str] = None) -> List[dict]:
        """执行搜索，返回 [{title, url, snippet}, ...]；失败/风控返回空列表。

        - 命中缓存直接返回（TTL 内）
        - 引擎偶发反爬会返回空结果，自动重试一次再放弃
        - 记录耗时日志，便于定位慢在哪一步
        """
        engine = engine or self.engine
        if engine not in SUPPORTED_ENGINES:
            return []

        # ── 缓存命中 ──
        cache_key = (engine, query)
        now = time.monotonic()
        hit = self._cache.get(cache_key)
        if hit and now - hit[0] < self.cache_ttl:
            logger.info(f"[搜索] 缓存命中 | {engine} | q={query[:40]}")
            return hit[1]

        # ── 实际搜索 ──
        for attempt in range(2):
            try:
                t0 = time.monotonic()
                if engine == "bing":
                    results = await self._search_bing(query)
                elif engine == "duckduckgo":
                    results = await self._search_duckduckgo(query)
                elif engine == "baidu":
                    results = await self._search_baidu(query)
                else:
                    return []
                logger.info(
                    f"[搜索] {engine} 耗时{time.monotonic() - t0:.1f}s "
                    f"命中{len(results)}条 | q={query[:40]}"
                )
                if results:
                    self._cache[cache_key] = (time.monotonic(), results)
                    return results
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"[搜索] {engine} 失败: {e}")
        return []

    # ── 必应（cn.bing.com）──

    async def _search_bing(self, query: str) -> List[dict]:
        resp = await self._client.get(
            "https://cn.bing.com/search", params={"q": query}
        )
        resp.raise_for_status()
        html = resp.text
        results = []
        for li in re.findall(
            r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>.*?</li>', html, re.S
        ):
            m = re.search(
                r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', li, re.S
            )
            if not m:
                continue
            url, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            snip_m = re.search(r"<p[^>]*>(.*?)</p>", li, re.S)
            snippet = re.sub(r"<[^>]+>", "", snip_m.group(1)).strip() if snip_m else ""
            if title:
                results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= self.result_count:
                break
        return results

    # ── DuckDuckGo（html 端点）──

    async def _search_duckduckgo(self, query: str) -> List[dict]:
        resp = await self._client.post(
            "https://html.duckduckgo.com/html/", data={"q": query}
        )
        resp.raise_for_status()
        html = resp.text
        results = []
        for a in re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S
        ):
            url, title = a[0], re.sub(r"<[^>]+>", "", a[1]).strip()
            m = re.search(r"uddg=([^&]+)", url)
            if m:
                try:
                    url = urllib.parse.unquote(m.group(1))
                except Exception:
                    pass
            if title:
                results.append({"title": title, "url": url, "snippet": ""})
            if len(results) >= self.result_count:
                break
        return results

    # ── 百度 ──

    async def _search_baidu(self, query: str) -> List[dict]:
        resp = await self._client.get(
            "https://www.baidu.com/s", params={"wd": query}
        )
        resp.raise_for_status()
        html = resp.text
        results = []
        for div in re.findall(r'<div[^>]*class="result[^"]*".*?</div>', html, re.S):
            m = re.search(
                r'<h3[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', div, re.S
            )
            if not m:
                continue
            url, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            snip_m = re.search(
                r'<span class="content-right_8Zs40">(.*?)</span>', div, re.S
            ) or re.search(r'<div class="c-abstract[^"]*">(.*?)</div>', div, re.S)
            snippet = re.sub(r"<[^>]+>", "", snip_m.group(1)).strip() if snip_m else ""
            if title:
                results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= self.result_count:
                break
        return results

    # ── 结果格式化 ──

    @staticmethod
    def format_results(results: List[dict]) -> str:
        """把搜索结果格式化为可注入上下文的文本"""
        if not results:
            return "未找到相关搜索结果。"
        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            url = r.get("url", "")
            snippet = r.get("snippet", "")
            line = f"{i}. {title}"
            if snippet:
                line += f"\n   {snippet[:200]}"
            if url:
                line += f"\n   {url}"
            lines.append(line)
        return "\n".join(lines)

    async def close(self):
        try:
            await self._client.aclose()
        except Exception:
            pass


async def execute_search_tool(
    searcher: Optional[WebSearcher], name: str, args_json: str
) -> str:
    """Function 工具执行器：按函数名路由到对应引擎"""
    if searcher is None:
        return "联网搜索未启用。"
    engine = name.replace("web_search_", "")
    if engine not in SUPPORTED_ENGINES:
        return f"未知搜索函数: {name}"
    try:
        args = json.loads(args_json or "{}")
    except Exception:
        args = {}
    query = str(args.get("query") or "").strip()
    if not query:
        return "缺少查询关键词，请提供 query 参数。"
    logger.info(f"[搜索] tool={name} query={query[:50]}")
    results = await searcher.search(query, engine=engine)
    return searcher.format_results(results)
