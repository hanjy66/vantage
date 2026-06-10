import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.modes.loader import load_mode
from src.modes.router import resolve_mode


def test_load_general_mode():
    cfg = load_mode("general")
    assert cfg.mode == "general"
    assert len(cfg.prompts.lead_researcher) > 50


def test_load_interview_mode():
    cfg = load_mode("interview")
    assert cfg.mode == "interview"
    assert "面试" in cfg.prompts.clarify_with_user


def test_interview_final_report_has_mermaid_instruction():
    """plan 014-A：面试 final_report 必须要求输出 mermaid 架构图，且 format 不被花括号破坏。"""
    cfg = load_mode("interview")
    fr = cfg.prompts.final_report
    assert "mermaid" in fr
    # 占位符齐全时 format 不应抛 KeyError（mermaid 示例不能引入裸花括号）
    rendered = fr.format(
        research_brief="x",
        messages="y",
        date="z",
        findings="f",
        source_allowlist="a",
        revision_context="r",
        interview_links="L",  # plan 017：面经链接占位
    )
    assert "mermaid" in rendered


def test_load_nonexistent_mode_raises():
    with pytest.raises(FileNotFoundError):
        load_mode("nonexistent_mode_xyz")


def test_resolve_mode_default():
    cfg = resolve_mode({"configurable": {}})
    assert cfg.mode == "general"


def test_resolve_mode_explicit():
    cfg = resolve_mode({"configurable": {"mode": "interview"}})
    assert cfg.mode == "interview"
