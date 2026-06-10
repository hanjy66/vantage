"""plan 014 — 中文源（智谱）+ 面经工具的装配与解析测试（不打真实 API）。"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from open_deep_research.search_zh import (
    AUTHORITATIVE_DOMAINS,
    authoritative_search,
    search_interview_experience,
    zhipu_search,
)
from open_deep_research.utils import get_all_tools


def _names(tools):
    out = []
    for t in tools:
        if hasattr(t, "name"):
            out.append(t.name)
        elif isinstance(t, dict):
            out.append(t.get("name", "?"))
    return out


# ---------- 装配：按 key / 按 mode 非侵入挂载 ----------

@pytest.mark.asyncio
async def test_zhipu_tool_present_when_key_set():
    with patch.dict(os.environ, {"ZHIPUAI_API_KEY": "fake"}, clear=False):
        tools = await get_all_tools({"configurable": {"mode": "general"}})
    assert "web_search_zh" in _names(tools)


@pytest.mark.asyncio
async def test_zhipu_tool_absent_without_key():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ZHIPUAI_API_KEY", None)
        tools = await get_all_tools({"configurable": {"mode": "general"}})
    assert "web_search_zh" not in _names(tools)


@pytest.mark.asyncio
async def test_interview_tool_only_in_interview_mode():
    with patch.dict(os.environ, {"ZHIPUAI_API_KEY": "fake"}, clear=False):
        general = _names(await get_all_tools({"configurable": {"mode": "general"}}))
        interview = _names(await get_all_tools({"configurable": {"mode": "interview"}}))
    assert "search_interview_experience" not in general
    assert "search_interview_experience" in interview


# ---------- 智谱解析：mock HTTP + 跳过 summarize（无网络/无 LLM）----------

class _FakeResp:
    def __init__(self, data):
        self._data = data
        self.status = 200  # 429 退避重试逻辑会读 resp.status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    async def json(self):
        return self._data


class _FakeSession:
    def __init__(self, data):
        self._data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, *a, **k):
        return _FakeResp(self._data)


@pytest.mark.asyncio
async def test_zhipu_search_parses_link_and_content():
    fake = {
        "search_result": [
            {"title": "字节豆包", "link": "https://x.com/a", "content": "豆包是字节的AI助手"},
            {"title": "重复URL", "link": "https://x.com/a", "content": "应被去重"},
        ]
    }
    captured = {}

    async def fake_fmt(unique_results, config):
        captured["u"] = unique_results
        return "OK"

    with patch.dict(os.environ, {"ZHIPUAI_API_KEY": "fake"}, clear=False), \
        patch("open_deep_research.search_zh.aiohttp.ClientSession", lambda *a, **k: _FakeSession(fake)), \
        patch("open_deep_research.search_zh._summarize_and_format", fake_fmt):
        out = await zhipu_search.ainvoke(
            {"queries": ["字节豆包"], "config": {"configurable": {}}}
        )

    assert out == "OK"
    u = captured["u"]
    assert "https://x.com/a" in u
    assert u["https://x.com/a"]["content"] == "豆包是字节的AI助手"
    assert u["https://x.com/a"]["raw_content"] == ""  # 智谱无全文 → 跳过 LLM summarize
    assert len(u) == 1  # 同 URL 去重


# ---------- 守卫路径：缺 key 时优雅降级，不抛错 ----------

@pytest.mark.asyncio
async def test_zhipu_search_without_key_returns_hint():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ZHIPUAI_API_KEY", None)
        out = await zhipu_search.ainvoke({"queries": ["x"], "config": {"configurable": {}}})
    assert "ZHIPUAI_API_KEY" in out


@pytest.mark.asyncio
async def test_interview_search_without_tavily_key_returns_hint():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TAVILY_API_KEY", None)
        out = await search_interview_experience.ainvoke(
            {"queries": ["x"], "config": {"configurable": {}}}
        )
    assert "TAVILY_API_KEY" in out


# ---------- plan 016：权威源深度检索 ----------

@pytest.mark.asyncio
async def test_authoritative_tool_present_in_both_modes_with_tavily_key():
    with patch.dict(os.environ, {"TAVILY_API_KEY": "fake"}, clear=False):
        general = _names(await get_all_tools({"configurable": {"mode": "general"}}))
        interview = _names(await get_all_tools({"configurable": {"mode": "interview"}}))
    assert "authoritative_search" in general
    assert "authoritative_search" in interview


class _FakeTavily:
    """捕获 client.search 的入参，校验白名单/advanced 正确下传。"""

    def __init__(self, *a, **k):
        pass

    async def search(self, query, **kwargs):
        _FakeTavily.last = {"query": query, **kwargs}
        return {"results": [{"title": "T", "url": "https://arxiv.org/abs/1", "content": "c"}]}


@pytest.mark.asyncio
async def test_authoritative_search_passes_allowlist_and_advanced():
    async def fake_fmt(unique_results, config):
        return "OK"

    with patch.dict(os.environ, {"TAVILY_API_KEY": "fake"}, clear=False), \
        patch("open_deep_research.search_zh.AsyncTavilyClient", _FakeTavily), \
        patch("open_deep_research.search_zh._summarize_and_format", fake_fmt):
        out = await authoritative_search.ainvoke(
            {"queries": ["MoE expert routing"], "config": {"configurable": {}}}
        )

    assert out == "OK"
    assert _FakeTavily.last["include_domains"] == AUTHORITATIVE_DOMAINS
    assert _FakeTavily.last["search_depth"] == "advanced"


@pytest.mark.asyncio
async def test_authoritative_search_without_tavily_key_returns_hint():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TAVILY_API_KEY", None)
        out = await authoritative_search.ainvoke(
            {"queries": ["x"], "config": {"configurable": {}}}
        )
    assert "TAVILY_API_KEY" in out
