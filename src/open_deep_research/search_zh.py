"""中文搜索源（智谱）+ 面经定向检索 —— researcher 可自选的 tool。

设计：非侵入。这两个工具只通过 `utils.get_all_tools` 追加到 researcher 的工具列表，
让模型按 query 自行决定调用哪个搜索源；主图（deep_researcher 的节点/路由/状态机）不改。

- `zhipu_search`（工具名 web_search_zh）：智谱 web_search，中文/国内站点召回，有 ZHIPUAI_API_KEY 才挂。
- `search_interview_experience`：Tavily 锁定牛客/知乎的面经定向检索，仅面试模式挂。

两者输出契约与 `utils.tavily_search` 完全一致（同一段 SOURCE/URL/SUMMARY 格式），
下游 compress_research 处理一致。
"""

import asyncio
import os
from typing import Annotated, List

import aiohttp
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg, tool
from tavily import AsyncTavilyClient

from open_deep_research.configuration import Configuration
from open_deep_research.state import Summary
from open_deep_research.utils import (
    get_api_key_for_model,
    get_base_url_for_model,
    get_tavily_api_key,
    summarize_webpage,
)

ZHIPU_WEB_SEARCH_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"
INTERVIEW_DOMAINS = ["nowcoder.com", "zhihu.com"]

# 权威源白名单：精选一手来源，宁缺毋滥（Tavily 官方建议 include_domains 短而精）。
# 搜空时模型可回退普通 web_search。后续按实测搜空率再微调，不一次堆满。
AUTHORITATIVE_DOMAINS = [
    # 学术 / 论文（一手研究）
    "arxiv.org",
    "aclanthology.org",
    "openreview.net",
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "nature.com",
    "semanticscholar.org",
    # 一手代码 / 模型
    "github.com",
    "huggingface.co",
    # 前沿 AI 实验室官方研究 / 技术博客
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "ai.meta.com",
    "research.google",
    "developer.nvidia.com",
    # 中文深度技术
    "jiqizhixin.com",
]


def get_zhipu_api_key(config: RunnableConfig) -> str | None:
    """读取智谱 API key，与 get_tavily_api_key 同源策略（env 或 config.apiKeys）。"""
    should_get_from_config = os.getenv("GET_API_KEYS_FROM_CONFIG", "false")
    if should_get_from_config.lower() == "true":
        api_keys = (config or {}).get("configurable", {}).get("apiKeys", {}) or {}
        return api_keys.get("ZHIPUAI_API_KEY")
    return os.getenv("ZHIPUAI_API_KEY")


async def _summarize_and_format(unique_results: dict, config: RunnableConfig) -> str:
    """复刻 tavily_search 的 summarize + format（隔离实现，不改主搜索）。

    unique_results: {url: {"title", "content", "raw_content"(可空), "query"}}
    有 raw_content 才走 LLM summarize；否则直接用 content（如智谱只返回 snippet）。
    """
    configurable = Configuration.from_runnable_config(config)
    max_char_to_include = configurable.max_content_length

    model_api_key = get_api_key_for_model(configurable.summarization_model, config)
    _summ_kwargs: dict = dict(
        model=configurable.summarization_model,
        max_tokens=configurable.summarization_model_max_tokens,
        api_key=model_api_key,
        tags=["langsmith:nostream"],
    )
    _summ_base_url = get_base_url_for_model(configurable.summarization_model)
    if _summ_base_url:
        _summ_kwargs["base_url"] = _summ_base_url
    summarization_model = (
        init_chat_model(**_summ_kwargs)
        .with_structured_output(Summary, method="function_calling")
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
    )

    async def noop():
        return None

    summarization_tasks = [
        noop()
        if not result.get("raw_content")
        else summarize_webpage(summarization_model, result["raw_content"][:max_char_to_include])
        for result in unique_results.values()
    ]
    summaries = await asyncio.gather(*summarization_tasks)

    summarized_results = {
        url: {
            "title": result["title"],
            "content": result["content"] if summary is None else summary,
        }
        for url, result, summary in zip(
            unique_results.keys(), unique_results.values(), summaries
        )
    }

    if not summarized_results:
        return (
            "No valid search results found. "
            "Please try different search queries or use a different search API."
        )

    formatted_output = "Search results: \n\n"
    for i, (url, result) in enumerate(summarized_results.items()):
        formatted_output += f"\n\n--- SOURCE {i + 1}: {result['title']} ---\n"
        formatted_output += f"URL: {url}\n\n"
        formatted_output += f"SUMMARY:\n{result['content']}\n\n"
        formatted_output += "\n\n" + "-" * 80 + "\n"
    return formatted_output


ZHIPU_SEARCH_DESCRIPTION = (
    "中文网络搜索引擎（智谱）。当查询涉及中文内容、中国本土公司/产品，或国内站点"
    "（知乎、牛客、36氪、百度百科、政府与中文媒体站）时，优先用本工具，中文召回质量优于通用 web_search。"
    "Chinese web search; prefer this for Chinese-language queries about China-domestic "
    "companies, products, and websites. Input one or more search queries."
)


@tool("web_search_zh", description=ZHIPU_SEARCH_DESCRIPTION)
async def zhipu_search(
    queries: List[str],
    max_results: Annotated[int, InjectedToolArg] = 5,
    config: RunnableConfig = None,
) -> str:
    """智谱 web_search，返回与 web_search(Tavily) 相同格式的字符串。"""
    api_key = get_zhipu_api_key(config)
    if not api_key:
        return "中文搜索（智谱）不可用：未配置 ZHIPUAI_API_KEY。请改用 web_search。"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async def _one(session: aiohttp.ClientSession, q: str):
        """单 query，遇 429（智谱免费版 QPS 限流）退避重试。"""
        payload = {"search_engine": "search_std", "search_query": q}
        for attempt in range(3):
            async with session.post(
                ZHIPU_WEB_SEARCH_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 429 and attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return q, await resp.json()

    try:
        # 串行执行：智谱免费版 QPS 很低，并发多 query 会直接 429。逐个查 + query 间留间隔。
        results = []
        async with aiohttp.ClientSession() as session:
            for i, q in enumerate(queries):
                if i:
                    await asyncio.sleep(0.6)
                results.append(await _one(session, q))
    except Exception as e:  # noqa: BLE001 — 工具错误不应中断研究循环
        return f"中文搜索（智谱）出错: {e}。请改用 web_search。"

    unique_results: dict = {}
    for q, data in results:
        for item in (data.get("search_result") or [])[:max_results]:
            url = item.get("link") or item.get("url") or ""
            if url and url not in unique_results:
                unique_results[url] = {
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "raw_content": "",  # 智谱只返回 snippet，无全文 → 跳过 summarize
                    "query": q,
                }

    return await _summarize_and_format(unique_results, config)


INTERVIEW_SEARCH_DESCRIPTION = (
    "面试经验（面经）定向检索：仅在牛客网(nowcoder.com)与知乎(zhihu.com)中搜索真实面试经历、"
    "面试题、考点与流程。当需要候选人视角的真实面经、某公司/岗位的高频面试问题时使用本工具。"
    "Search interview experiences from nowcoder.com and zhihu.com. Input one or more queries."
)


@tool("search_interview_experience", description=INTERVIEW_SEARCH_DESCRIPTION)
async def search_interview_experience(
    queries: List[str],
    max_results: Annotated[int, InjectedToolArg] = 5,
    config: RunnableConfig = None,
) -> str:
    """牛客/知乎面经定向检索（Tavily include_domains），返回统一搜索结果格式。"""
    api_key = get_tavily_api_key(config)
    if not api_key:
        return "面经检索不可用：未配置 TAVILY_API_KEY。"

    client = AsyncTavilyClient(api_key=api_key)

    async def _one(q: str):
        return q, await client.search(
            f"{q} 面经 面试",
            max_results=max_results,
            include_raw_content=True,
            include_domains=INTERVIEW_DOMAINS,
            topic="general",
        )

    try:
        results = await asyncio.gather(*[_one(q) for q in queries])
    except Exception as e:  # noqa: BLE001 — 工具错误不应中断研究循环
        return f"面经检索出错: {e}。"

    unique_results: dict = {}
    for q, data in results:
        for item in data.get("results", []):
            url = item.get("url")
            if url and url not in unique_results:
                unique_results[url] = {**item, "query": q}

    return await _summarize_and_format(unique_results, config)


AUTHORITATIVE_SEARCH_DESCRIPTION = (
    "权威源深度检索：仅在一手权威来源中检索——学术论文(arxiv/ACL/OpenReview/IEEE/ACM/Nature)、"
    "开源代码与模型(github/huggingface)、前沿 AI 实验室官方研究与技术博客(OpenAI/Anthropic/DeepMind/Meta/Google/NVIDIA)、"
    "以及中文论文解读(机器之心)。采用 advanced 深度抓取。"
    "**当问题涉及深度技术原理、前沿/最新研究、需要一手官方文档/论文/技术报告佐证时，优先用本工具**；"
    "浅层事实、新闻、产品市场信息请用普通 web_search。Input one or more queries."
)


@tool("authoritative_search", description=AUTHORITATIVE_SEARCH_DESCRIPTION)
async def authoritative_search(
    queries: List[str],
    max_results: Annotated[int, InjectedToolArg] = 5,
    config: RunnableConfig = None,
) -> str:
    """权威源定向深度检索（Tavily include_domains 白名单 + advanced），返回统一搜索结果格式。"""
    api_key = get_tavily_api_key(config)
    if not api_key:
        return "权威源检索不可用：未配置 TAVILY_API_KEY。请改用 web_search。"

    client = AsyncTavilyClient(api_key=api_key)

    async def _one(q: str):
        return q, await client.search(
            q,
            max_results=max_results,
            include_raw_content=True,
            include_domains=AUTHORITATIVE_DOMAINS,
            search_depth="advanced",
            topic="general",
        )

    try:
        results = await asyncio.gather(*[_one(q) for q in queries])
    except Exception as e:  # noqa: BLE001 — 工具错误不应中断研究循环
        return f"权威源检索出错: {e}。请改用 web_search。"

    unique_results: dict = {}
    for q, data in results:
        for item in data.get("results", []):
            url = item.get("url")
            if url and url not in unique_results:
                unique_results[url] = {**item, "query": q}

    if not unique_results:
        return (
            "权威源白名单内未检索到结果（可能该主题在一手来源覆盖不足）。"
            "请改用普通 web_search 获取更广来源。"
        )
    return await _summarize_and_format(unique_results, config)
