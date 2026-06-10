"""Plan 007 unit tests — Format Adapter 节点。"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

import pytest
from langgraph.graph import END
from langgraph.types import Command


def _fake_mode(templates=None, display_name="Test Mode", mode="general"):
    return type("M", (), {
        "output_templates": templates or {},
        "display_name": display_name,
        "mode": mode,
    })()


@pytest.mark.asyncio
async def test_empty_templates_passthrough(monkeypatch):
    """output_templates={} → formatted_report = final_report 原样。"""
    from open_deep_research.deep_researcher import format_adapter

    state = {
        "final_report": "原始报告内容",
        "mode_config": _fake_mode(templates={}),
        "critique": {"score": 8, "passed": True},
    }
    cmd = await format_adapter(state, {"configurable": {}})
    assert cmd.goto == "visualize"  # plan 009: format_adapter 现在 goto visualize，不直接 END
    assert cmd.update["formatted_report"] == "原始报告内容"


@pytest.mark.asyncio
async def test_research_failed_passthrough(monkeypatch):
    """research_failed=True → 哨兵报告原样输出，不套模板。"""
    from open_deep_research.deep_researcher import format_adapter

    state = {
        "final_report": "# 研究失败 — 无法生成报告",
        "research_failed": True,
        "mode_config": _fake_mode(templates={"header": "should_not_appear"}),
        "critique": {"score": 0, "passed": False},
    }
    cmd = await format_adapter(state, {"configurable": {}})
    assert cmd.update["formatted_report"] == "# 研究失败 — 无法生成报告"


@pytest.mark.asyncio
async def test_full_template_applied(monkeypatch):
    """完整 templates → header + TL;DR + body + footer 拼接。"""
    from open_deep_research.deep_researcher import format_adapter

    tmpl = {
        "header": "[HEADER score={score} date={date}]\n\n",
        "footer": "\n\n[FOOTER]",
        "tldr_position": "top",
        "tldr_min_score": 7,
        "tldr_template": "[TLDR score={score} brief={brief}]\n\n",
    }
    state = {
        "final_report": "BODY",
        "mode_config": _fake_mode(templates=tmpl),
        "critique": {"score": 9, "passed": True},
        "research_brief": "test brief content",
    }
    cmd = await format_adapter(state, {"configurable": {}})
    out = cmd.update["formatted_report"]
    assert "[HEADER score=9" in out
    assert "[TLDR score=9" in out
    assert "BODY" in out
    assert "[FOOTER]" in out
    # 顺序：header → tldr → body → footer
    assert out.index("[HEADER") < out.index("[TLDR") < out.index("BODY") < out.index("[FOOTER]")


@pytest.mark.asyncio
async def test_tldr_skipped_low_score(monkeypatch):
    """score < tldr_min_score → 不加 TL;DR。"""
    from open_deep_research.deep_researcher import format_adapter

    tmpl = {
        "header": "HEADER\n",
        "tldr_position": "top",
        "tldr_min_score": 7,
        "tldr_template": "[TLDR]",
    }
    state = {
        "final_report": "body",
        "mode_config": _fake_mode(templates=tmpl),
        "critique": {"score": 5, "passed": False},
    }
    cmd = await format_adapter(state, {"configurable": {}})
    assert "[TLDR]" not in cmd.update["formatted_report"]


@pytest.mark.asyncio
async def test_tldr_position_bottom(monkeypatch):
    """tldr_position=bottom → TL;DR 放正文后。"""
    from open_deep_research.deep_researcher import format_adapter

    tmpl = {
        "tldr_position": "bottom",
        "tldr_min_score": 0,
        "tldr_template": "[TLDR]",
    }
    state = {
        "final_report": "BODY",
        "mode_config": _fake_mode(templates=tmpl),
        "critique": {"score": 9, "passed": True},
    }
    cmd = await format_adapter(state, {"configurable": {}})
    out = cmd.update["formatted_report"]
    assert out.index("BODY") < out.index("[TLDR]")


@pytest.mark.asyncio
async def test_bad_template_placeholder_resilient(monkeypatch):
    """模板含未定义占位符不应抛异常，原样保留模板。"""
    from open_deep_research.deep_researcher import format_adapter

    tmpl = {"header": "{not_defined_field}\n"}
    state = {
        "final_report": "body",
        "mode_config": _fake_mode(templates=tmpl),
        "critique": {"score": 8, "passed": True},
    }
    cmd = await format_adapter(state, {"configurable": {}})
    out = cmd.update["formatted_report"]
    assert "{not_defined_field}" in out  # 模板原样保留
    assert "body" in out
