"""Plan 006 unit tests — HITL planner confirm + Escalation routing."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END
from langgraph.types import Command

from open_deep_research.configuration import Configuration
from open_deep_research.critic import critic_node


# ============ HITL: confirm_research_brief ============

@pytest.mark.asyncio
async def test_hitl_disabled_passthrough(monkeypatch):
    """enable_hitl_planner_confirm=False → 直通 research_supervisor，不 interrupt。"""
    from open_deep_research.deep_researcher import confirm_research_brief

    state = {"research_brief": "test brief"}
    config = {"configurable": {"enable_hitl_planner_confirm": False}}

    cmd = await confirm_research_brief(state, config)
    assert isinstance(cmd, Command)
    assert cmd.goto == "research_supervisor"


@pytest.mark.asyncio
async def test_hitl_enabled_interrupt_and_approve(monkeypatch):
    """enable_hitl=True 时 interrupt() 应被调用；模拟用户 approve。"""
    from open_deep_research import deep_researcher

    captured_payload = {}

    def fake_interrupt(payload):
        captured_payload.update(payload)
        return {"action": "approve"}  # 模拟用户 resume payload

    monkeypatch.setattr("langgraph.types.interrupt", fake_interrupt)

    state = {"research_brief": "test brief", "supervisor_messages": []}
    config = {"configurable": {"enable_hitl_planner_confirm": True}}

    cmd = await deep_researcher.confirm_research_brief(state, config)
    assert captured_payload["pending_action"] == "confirm_brief"
    assert captured_payload["draft_brief"] == "test brief"
    assert cmd.goto == "research_supervisor"
    assert cmd.update.get("pending_user_action") == ""


@pytest.mark.asyncio
async def test_hitl_enabled_edit_rebuilds_brief(monkeypatch):
    """模拟用户 edit brief，确认 supervisor_messages 被重建。"""
    from open_deep_research import deep_researcher

    new_brief = "重写后的研究简报：聚焦 2024 Q4"

    def fake_interrupt(payload):
        return {"action": "edit", "final_brief": new_brief}

    monkeypatch.setattr("langgraph.types.interrupt", fake_interrupt)

    state = {
        "research_brief": "原 brief",
        "supervisor_messages": [
            SystemMessage(content="sys"),
            HumanMessage(content="原 brief"),
        ],
    }
    config = {"configurable": {"enable_hitl_planner_confirm": True}}

    cmd = await deep_researcher.confirm_research_brief(state, config)
    assert cmd.goto == "research_supervisor"
    assert cmd.update["research_brief"] == new_brief
    rebuilt_msgs = cmd.update["supervisor_messages"]["value"]
    assert isinstance(rebuilt_msgs[0], SystemMessage)
    assert rebuilt_msgs[1].content == new_brief


# ============ Escalation routing in critic_node ============

class _FakeRubric:
    system_prompt = "test {date} {research_brief} {findings} {final_report} {constitution_rules}"
    pass_threshold = 7


class _FakeModeConfig:
    mode = "general"
    critic_rubric = _FakeRubric()
    constitution_rules = ""


def _make_config(**kwargs) -> dict:
    """构造 critic_node 测试 config，所有 plan 006 字段都默认开启。"""
    base = {
        "enable_critic": True,
        "enable_escalation": True,
        "escalation_threshold": 3,
        "escalation_model": "anthropic:claude-3-5-sonnet-20241022",
        "max_revisions": 1,
        "enable_kg": False,
        "critic_model": "google_genai:gemini-2.5-flash",
    }
    base.update(kwargs)
    return {"configurable": base}


@pytest.mark.asyncio
async def test_escalation_triggered_on_low_score(monkeypatch):
    """score ≤ threshold 且未 escalated → goto final_report_generation with escalated=True"""
    fake_report = type("R", (), {
        "score": 2, "passed": False,
        "model_dump": lambda self: {"score": 2, "passed": False},
    })()

    async def fake_invoke(*a, **kw):
        return fake_report

    class FakeModel:
        def with_structured_output(self, _, **kwargs): return self
        def with_retry(self, **_): return self
        def with_config(self, _): return self
        async def ainvoke(self, _): return fake_report

    monkeypatch.setattr("open_deep_research.critic.critic_configurable_model", FakeModel())
    monkeypatch.setattr("open_deep_research.critic.resolve_mode", lambda _c: _FakeModeConfig())

    state = {"research_brief": "x", "final_report": "y", "mode_config": _FakeModeConfig(), "escalated": False}
    cmd = await critic_node(state, _make_config())

    assert cmd.goto == "final_report_generation"
    assert cmd.update["escalated"] is True
    # escalation 不自增 revision_count
    assert "revision_count" not in cmd.update


@pytest.mark.asyncio
async def test_no_second_escalation(monkeypatch):
    """already_escalated=True → 不再 escalate；走正常 revise 或 END。"""
    fake_report = type("R", (), {
        "score": 2, "passed": False,
        "model_dump": lambda self: {"score": 2, "passed": False},
    })()
    class FakeModel:
        def with_structured_output(self, _, **kwargs): return self
        def with_retry(self, **_): return self
        def with_config(self, _): return self
        async def ainvoke(self, _): return fake_report
    monkeypatch.setattr("open_deep_research.critic.critic_configurable_model", FakeModel())
    monkeypatch.setattr("open_deep_research.critic.resolve_mode", lambda _c: _FakeModeConfig())

    state = {
        "research_brief": "x", "final_report": "y",
        "mode_config": _FakeModeConfig(),
        "escalated": True,           # 已 escalate 过
        "revision_count": 1,         # 已 revise 过，达 max
    }
    cmd = await critic_node(state, _make_config())
    # 不再 escalate，且 revise 也满 → END
    assert cmd.goto == "format_adapter"


@pytest.mark.asyncio
async def test_escalation_disabled_via_config(monkeypatch):
    """enable_escalation=False → 即使低分也不 escalate。"""
    fake_report = type("R", (), {
        "score": 1, "passed": False,
        "model_dump": lambda self: {"score": 1, "passed": False},
    })()
    class FakeModel:
        def with_structured_output(self, _, **kwargs): return self
        def with_retry(self, **_): return self
        def with_config(self, _): return self
        async def ainvoke(self, _): return fake_report
    monkeypatch.setattr("open_deep_research.critic.critic_configurable_model", FakeModel())
    monkeypatch.setattr("open_deep_research.critic.resolve_mode", lambda _c: _FakeModeConfig())

    state = {"research_brief": "x", "final_report": "y", "mode_config": _FakeModeConfig(), "escalated": False, "revision_count": 0}
    cmd = await critic_node(state, _make_config(enable_escalation=False))

    # 走 revise 路径而非 escalation
    assert cmd.goto == "final_report_generation"
    assert "escalated" not in cmd.update
    assert cmd.update.get("revision_count") == 1
