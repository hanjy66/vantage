"""plan 010 Step 2 单测 — SSE 事件映射（零 LLM，假事件流）。"""

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from server.sse import graph_event_stream, sse_pack


def _parse(sse_chunks: list[str]) -> list[tuple[str, dict]]:
    """把 SSE 字符串解析成 (event, data) 列表。"""
    out = []
    for chunk in sse_chunks:
        lines = chunk.strip().split("\n")
        ev = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        out.append((ev, data))
    return out


class _FakeGraph:
    """假图：astream_events 吐预设事件序列；可选模拟 HITL 中断快照。"""

    def __init__(self, events, interrupt_value=None):
        self._events = events
        self._interrupt_value = interrupt_value

    async def astream_events(self, *_, **__):
        for e in self._events:
            yield e

    async def aget_state(self, *_, **__):
        class _Intr:
            value = self._interrupt_value

        class _Task:
            interrupts = (_Intr(),) if self._interrupt_value is not None else ()

        class _Snap:
            tasks = (_Task(),)

        return _Snap()


async def _collect(graph, config=None) -> list[tuple[str, dict]]:
    chunks = [c async for c in graph_event_stream(graph, {}, config or {})]
    return _parse(chunks)


def test_sse_pack_format():
    s = sse_pack("node", {"a": 1})
    assert s == 'event: node\ndata: {"a": 1}\n\n'


def test_sse_pack_utf8_no_escape():
    s = sse_pack("node", {"stage": "审计"})
    assert "审计" in s  # ensure_ascii=False


@pytest.mark.asyncio
async def test_toplevel_node_start_end_mapped():
    events = [
        {"event": "on_chain_start", "name": "critic", "run_id": "r1", "data": {}},
        {"event": "on_chain_end", "name": "critic", "run_id": "r1",
         "data": {"output": {"critique": {"score": 8, "passed": True, "model_used": "gemini"}}}},
    ]
    parsed = await _collect(_FakeGraph(events))
    kinds = [e for e, _ in parsed]
    assert kinds == ["node", "result", "node", "done"] or kinds == ["node", "node", "result", "done"]
    # node start
    assert ("node", {"node": "critic", "stage": "跨模型审计", "phase": "start"}) in parsed
    # node end
    assert ("node", {"node": "critic", "stage": "跨模型审计", "phase": "end"}) in parsed
    # result 带 critique
    results = [d for e, d in parsed if e == "result"]
    assert results and results[0]["critique"]["score"] == 8


@pytest.mark.asyncio
async def test_subgraph_internal_nodes_filtered():
    """非顶层节点（子图内部）不外泄。"""
    events = [
        {"event": "on_chain_start", "name": "some_researcher_subnode", "run_id": "x", "data": {}},
        {"event": "on_chain_end", "name": "tool_call_xyz", "run_id": "y", "data": {"output": {}}},
    ]
    parsed = await _collect(_FakeGraph(events))
    assert parsed == [("done", {})]  # 只有结束信号


@pytest.mark.asyncio
async def test_run_dedup():
    """同一 run_id 同一 phase 不重复下发。"""
    events = [
        {"event": "on_chain_start", "name": "visualize", "run_id": "dup", "data": {}},
        {"event": "on_chain_start", "name": "visualize", "run_id": "dup", "data": {}},
    ]
    parsed = await _collect(_FakeGraph(events))
    node_events = [e for e, _ in parsed if e == "node"]
    assert len(node_events) == 1


@pytest.mark.asyncio
async def test_chart_htmls_in_result():
    events = [
        {"event": "on_chain_end", "name": "visualize", "run_id": "v1",
         "data": {"output": {"chart_htmls": ["<div>chart</div>"]}}},
    ]
    parsed = await _collect(_FakeGraph(events))
    results = [d for e, d in parsed if e == "result"]
    assert results and results[0]["chart_htmls"] == ["<div>chart</div>"]


@pytest.mark.asyncio
async def test_command_output_unwrapped():
    """节点返回 Command(update={...}) 时，critique 应从 .update 解包（修评分卡空白 bug）。"""
    class _Cmd:
        def __init__(self, update):
            self.update = update
            self.goto = "format_adapter"

    events = [
        {"event": "on_chain_end", "name": "critic", "run_id": "c1",
         "data": {"output": _Cmd({"critique": {"score": 9, "passed": True}})}},
    ]
    parsed = await _collect(_FakeGraph(events))
    results = [d for e, d in parsed if e == "result"]
    assert results and results[0]["critique"]["score"] == 9


@pytest.mark.asyncio
async def test_tokens_accumulated_from_usage_metadata():
    """on_chat_model_end 的 usage_metadata 应累计并下发 tokens 事件（真实成本面板）。"""
    class _Msg:
        usage_metadata = {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140}

    events = [
        {"event": "on_chat_model_end", "name": "x", "run_id": "m1", "data": {"output": _Msg()}},
        {"event": "on_chat_model_end", "name": "y", "run_id": "m2", "data": {"output": _Msg()}},
    ]
    parsed = await _collect(_FakeGraph(events))
    toks = [d for e, d in parsed if e == "tokens"]
    assert len(toks) == 2
    assert toks[-1] == {"input": 200, "output": 80, "total": 280}


@pytest.mark.asyncio
async def test_interrupt_event_emitted_on_hitl_pause():
    """图停在 confirm_research_brief 的 interrupt 时，应发 interrupt 事件带 draft_brief + thread_id。"""
    graph = _FakeGraph(
        events=[],
        interrupt_value={"pending_action": "confirm_brief", "draft_brief": "研究 X 的竞品格局"},
    )
    parsed = await _collect(graph, config={"configurable": {"thread_id": "t-123"}})
    intr = [d for e, d in parsed if e == "interrupt"]
    assert len(intr) == 1
    assert intr[0]["draft_brief"] == "研究 X 的竞品格局"
    assert intr[0]["thread_id"] == "t-123"


@pytest.mark.asyncio
async def test_error_event_on_exception():
    class _Boom:
        async def astream_events(self, *_, **__):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    parsed = await _collect(_Boom())
    kinds = [e for e, _ in parsed]
    assert kinds == ["error", "done"]
    assert "boom" in parsed[0][1]["message"]
