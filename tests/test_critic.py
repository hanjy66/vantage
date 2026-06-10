"""Unit tests for critic node — all LLM calls mocked."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import open_deep_research.critic as critic_module
from open_deep_research.critic import ConflictItem, CriticReport, critic_node


def test_critic_report_score_range():
    report = CriticReport(score=8, passed=True, criteria_breakdown={"a": 8})
    assert report.score == 8

    # 越界分不再抛异常，而是归一化 + 夹紧（防 0-100 打分触发 critic_failed）
    r2 = CriticReport(score=70, passed=True, criteria_breakdown={"a": 90})
    assert r2.score == 7 and r2.criteria_breakdown == {"a": 9}
    assert CriticReport(score=150, passed=True, criteria_breakdown={}).score == 10


def test_conflict_item_severity_enum():
    item = ConflictItem(
        claim_a="A", claim_a_source="[1]",
        claim_b="B", claim_b_source="[2]",
        severity="high",
    )
    assert item.severity == "high"

    with pytest.raises(Exception):
        ConflictItem(
            claim_a="A", claim_a_source="[1]",
            claim_b="B", claim_b_source="[2]",
            severity="critical",
        )


@pytest.mark.asyncio
async def test_critic_disabled_short_circuits():
    """enable_critic=False 时立即返回 END，不应触发 LLM 调用。"""

    fake_configurable = type("C", (), {"enable_critic": False, "enable_kg": False})()

    with patch("open_deep_research.critic.Configuration.from_runnable_config", return_value=fake_configurable), \
         patch.object(critic_module.critic_configurable_model, "with_structured_output") as wso:
        cmd = await critic_node({"final_report": "x"}, {})

    assert cmd.goto == "format_adapter"
    wso.assert_not_called()


@pytest.mark.asyncio
async def test_critic_empty_rubric_short_circuits():
    """mode 没有 critic_rubric.system_prompt 时跳过 critic。"""

    fake_configurable = type("C", (), {
        "enable_critic": True,
        "critic_model": "google_genai:gemini-2.5-flash",
        "critic_model_max_tokens": 4096,
        "enable_kg": False,
        "max_revisions": 1,
    })()

    from src.modes.schema import CriticRubric
    fake_mode = type("M", (), {"critic_rubric": CriticRubric(), "constitution_rules": ""})()

    with patch("open_deep_research.critic.Configuration.from_runnable_config", return_value=fake_configurable), \
         patch("open_deep_research.critic.resolve_mode", return_value=fake_mode), \
         patch.object(critic_module.critic_configurable_model, "with_structured_output") as wso:
        cmd = await critic_node({"final_report": "x"}, {})

    assert cmd.goto == "format_adapter"
    wso.assert_not_called()


@pytest.mark.asyncio
async def test_critic_llm_exception_returns_error_critique():
    """LLM 失败时 critique 字段含 error，主流程不被阻断。"""

    fake_configurable = type("C", (), {
        "enable_critic": True,
        "critic_model": "openai:deepseek-chat",
        "critic_model_max_tokens": 4096,
        "enable_kg": False,
        "max_revisions": 1,
    })()

    from src.modes.schema import CriticCriterion, CriticRubric
    fake_rubric = CriticRubric(
        pass_threshold=7,
        criteria=[CriticCriterion(id="x", label="X", description="d")],
        system_prompt="审计 {research_brief} {findings} {final_report} {date} {constitution_rules}",
    )
    fake_mode = type("M", (), {"critic_rubric": fake_rubric, "constitution_rules": ""})()

    failing_chain = MagicMock()
    failing_chain.ainvoke = AsyncMock(side_effect=RuntimeError("upstream API down"))

    chain_builder = MagicMock()
    chain_builder.with_structured_output.return_value.with_retry.return_value.with_config.return_value = failing_chain

    with patch("open_deep_research.critic.Configuration.from_runnable_config", return_value=fake_configurable), \
         patch("open_deep_research.critic.resolve_mode", return_value=fake_mode), \
         patch("open_deep_research.critic.get_api_key_for_model", return_value="fake-key"), \
         patch.object(critic_module, "critic_configurable_model", chain_builder):
        cmd = await critic_node(
            {"final_report": "report body", "research_brief": "brief", "notes": []},
            {},
        )

    assert cmd.goto == "format_adapter"
    assert "error" in cmd.update["critique"]
    assert cmd.update["critique"]["passed"] is False
