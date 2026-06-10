"""Unit tests for critic revise loop — all LLM calls mocked."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import open_deep_research.critic as critic_module
from open_deep_research.critic import CriticReport, critic_node
from src.modes.schema import CriticCriterion, CriticRubric


def _build_fake_configurable(max_revisions: int = 1, enable_kg: bool = False):
    return type("C", (), {
        "enable_critic": True,
        "critic_model": "google_genai:gemini-2.5-flash",
        "critic_model_max_tokens": 4096,
        "max_revisions": max_revisions,
        "enable_kg": enable_kg,
        # plan 006 fields（默认关闭，不影响 revise loop 测试）
        "enable_escalation": False,
        "escalation_threshold": 3,
        "escalation_model": "anthropic:claude-3-5-sonnet-20241022",
    })()


def _build_fake_mode():
    rubric = CriticRubric(
        pass_threshold=8,
        criteria=[CriticCriterion(id="x", label="X", description="d")],
        system_prompt="审计 {research_brief} {findings} {final_report} {date} {constitution_rules}",
    )
    return type("M", (), {"critic_rubric": rubric, "mode": "interview", "constitution_rules": ""})()


def _patch_chain_with_report(report: CriticReport):
    """构造一个 critic LLM 调用链 mock，返回指定 report。"""
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=report)
    builder = MagicMock()
    builder.with_structured_output.return_value.with_retry.return_value.with_config.return_value = chain
    return builder


@pytest.mark.asyncio
async def test_passed_report_routes_to_end():
    """critic passed=true 时直接 END，不 revise。"""
    fake_report = CriticReport(score=9, passed=True, criteria_breakdown={"x": 9})

    with patch("open_deep_research.critic.Configuration.from_runnable_config",
               return_value=_build_fake_configurable(max_revisions=1)), \
         patch("open_deep_research.critic.resolve_mode", return_value=_build_fake_mode()), \
         patch("open_deep_research.critic.get_api_key_for_model", return_value="fake-key"), \
         patch.object(critic_module, "critic_configurable_model", _patch_chain_with_report(fake_report)):
        cmd = await critic_node(
            {"final_report": "report", "research_brief": "brief", "notes": [], "revision_count": 0},
            {},
        )

    assert cmd.goto == "format_adapter"
    assert cmd.update["critique"]["passed"] is True


@pytest.mark.asyncio
async def test_failed_report_routes_to_revise():
    """critic passed=false 且 revision_count<max_revisions 时回 final_report_generation。"""
    fake_report = CriticReport(score=4, passed=False, criteria_breakdown={"x": 4})

    with patch("open_deep_research.critic.Configuration.from_runnable_config",
               return_value=_build_fake_configurable(max_revisions=1)), \
         patch("open_deep_research.critic.resolve_mode", return_value=_build_fake_mode()), \
         patch("open_deep_research.critic.get_api_key_for_model", return_value="fake-key"), \
         patch.object(critic_module, "critic_configurable_model", _patch_chain_with_report(fake_report)):
        cmd = await critic_node(
            {"final_report": "report", "research_brief": "brief", "notes": [], "revision_count": 0},
            {},
        )

    assert cmd.goto == "final_report_generation"
    assert cmd.update["critique"]["passed"] is False


@pytest.mark.asyncio
async def test_failed_report_at_max_revisions_routes_to_end():
    """critic passed=false 且 revision_count>=max_revisions 时强制 END，不死循环。"""
    fake_report = CriticReport(score=4, passed=False, criteria_breakdown={"x": 4})

    with patch("open_deep_research.critic.Configuration.from_runnable_config",
               return_value=_build_fake_configurable(max_revisions=1)), \
         patch("open_deep_research.critic.resolve_mode", return_value=_build_fake_mode()), \
         patch("open_deep_research.critic.get_api_key_for_model", return_value="fake-key"), \
         patch.object(critic_module, "critic_configurable_model", _patch_chain_with_report(fake_report)):
        cmd = await critic_node(
            {"final_report": "report", "research_brief": "brief", "notes": [], "revision_count": 1},
            {},
        )

    assert cmd.goto == "format_adapter"
    assert cmd.update["critique"]["passed"] is False
