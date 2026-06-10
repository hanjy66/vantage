"""Plan 005 unit tests — research failure gate."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from open_deep_research.deep_researcher import (
    _build_research_failure_report,
    _detect_research_failure,
)


def test_detect_research_failure_notes_too_short():
    failed, reason = _detect_research_failure(
        notes=["short"], min_chars=200, error_ratio_threshold=0.5
    )
    assert failed is True
    assert "notes_too_short" in reason


def test_detect_research_failure_all_errors():
    notes = [
        "Error synthesizing research report: Maximum retries exceeded",
        "Tavily API error: rate limit hit",
        "Error: FAILED_PRECONDITION on call",
    ] * 5  # 15 lines all error-marked, > 200 chars
    failed, reason = _detect_research_failure(
        notes, min_chars=200, error_ratio_threshold=0.5
    )
    assert failed is True
    assert "error_ratio" in reason


def test_detect_research_failure_healthy_notes():
    notes = [
        "Anthropic Claude 3.5 Sonnet 在 2024 年 6 月发布，支持 200K 上下文窗口。",
        "OpenAI GPT-4o 在 2024 年 5 月发布，多模态能力显著提升。",
        "两家公司在 2024 年都加快了模型迭代节奏。",
    ] * 3
    failed, reason = _detect_research_failure(
        notes, min_chars=200, error_ratio_threshold=0.5
    )
    assert failed is False
    assert reason == ""


def test_detect_research_failure_empty_notes():
    failed, reason = _detect_research_failure(
        notes=[], min_chars=200, error_ratio_threshold=0.5
    )
    assert failed is True
    assert "notes_too_short" in reason


def test_detect_research_failure_partial_errors_below_threshold():
    """30% 错误率，不触发哨兵。"""
    notes = [
        "Anthropic Claude 3.5 Sonnet 发布于 2024 年 6 月。",
        "OpenAI GPT-4o 模型在 2024 年 5 月发布，多模态能力提升显著。",
        "两家公司在 2024 年都加快了模型迭代节奏，竞争白热化。",
        "Error synthesizing research report: timeout",  # 1/4 = 25%
    ] * 3
    failed, _ = _detect_research_failure(
        notes, min_chars=200, error_ratio_threshold=0.5
    )
    assert failed is False


def test_build_research_failure_report_contains_brief_and_reason():
    report = _build_research_failure_report(
        research_brief="对比 Claude 和 GPT-4", reason="error_ratio=10/12=0.83", notes_len=350
    )
    assert "研究失败" in report
    assert "对比 Claude 和 GPT-4" in report
    assert "error_ratio=10/12=0.83" in report
    assert "未调用任何 LLM" in report


# ============ plan 008 追查：gate 与 revise loop 的交互 ============

import pytest


@pytest.mark.asyncio
async def test_gate_skipped_on_revise_reentry(monkeypatch):
    """revise/escalation 重入（critique 已存在）时，即使 notes 为空也不触发 gate。

    复现 round2 q007/q024 被误杀的 bug：首次 pass 清空 notes 后，revise 重入
    时 notes=[] 会被 gate 误判 notes_too_short。修复后 critique 非空即跳过 gate。
    """
    from open_deep_research import deep_researcher

    # mock 掉 writer 模型调用，避免真打 API
    class FakeWriter:
        def with_config(self, _):
            return self

        async def ainvoke(self, _):
            from langchain_core.messages import AIMessage
            return AIMessage(content="revised report body")

    monkeypatch.setattr(deep_researcher, "final_report_configurable_model", FakeWriter())

    class _Mode:
        mode = "general"
        class prompts:
            final_report = "{research_brief}{messages}{findings}{date}{revision_context}"

    # revise 重入：critique 已存在 + notes 为空（已被首次 pass 清空）
    state = {
        "notes": [],                       # 清空状态
        "critique": {"score": 4, "passed": False, "conflicts": [], "improvement_suggestions": []},
        "research_brief": "test",
        "messages": [],
        "mode_config": _Mode(),
        "revision_count": 1,
    }
    config = {"configurable": {}}

    result = await deep_researcher.final_report_generation(state, config)
    # 不应被 gate 误杀
    assert not result.get("research_failed"), "revise 重入被 gate 误判 research_failed！"
    assert result.get("final_report") == "revised report body"


@pytest.mark.asyncio
async def test_gate_still_fires_on_first_pass_empty_notes(monkeypatch):
    """首次 pass（critique=None）notes 为空仍正常触发 gate。"""
    from open_deep_research import deep_researcher

    class _Mode:
        mode = "general"
        class prompts:
            final_report = "{research_brief}{messages}{findings}{date}{revision_context}"

    state = {
        "notes": [],
        "critique": None,                  # 首次 pass
        "research_brief": "test",
        "messages": [],
        "mode_config": _Mode(),
    }
    config = {"configurable": {}}

    result = await deep_researcher.final_report_generation(state, config)
    assert result.get("research_failed") is True
    assert "notes_too_short" in result.get("research_failure_reason", "")
