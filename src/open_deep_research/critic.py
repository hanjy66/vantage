"""Critic node — cross-model quality audit + conflict detection + revise routing."""

from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command
from pydantic import BaseModel, Field, field_validator

from open_deep_research.configuration import Configuration
from open_deep_research.kg_store import save_research
from open_deep_research.state import AgentState
from open_deep_research.utils import get_api_key_for_model, get_base_url_for_model, get_today_str
from src.modes.router import resolve_mode


class ConflictItem(BaseModel):
    claim_a: str
    claim_a_source: str
    claim_b: str
    claim_b_source: str
    severity: Literal["high", "medium", "low"]


def _norm_score(v) -> int:
    """把模型可能返回的 0-100 分归一到 0-10 并夹紧，避免越界触发校验失败。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    if f > 10:
        f = f / 10 if f <= 100 else 10
    return max(0, min(10, round(f)))


class CriticReport(BaseModel):
    score: int = Field(ge=0, le=10)
    passed: bool = False
    criteria_breakdown: dict[str, int] = Field(default_factory=dict)
    conflicts: list[ConflictItem] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    model_used: str = ""

    @field_validator("score", mode="before")
    @classmethod
    def _v_score(cls, v):
        return _norm_score(v)

    @field_validator("criteria_breakdown", mode="before")
    @classmethod
    def _v_breakdown(cls, v):
        # 模型有时按 0-100 给维度分；统一归一 + 夹紧，跳过非数值，避免整体校验失败
        if not isinstance(v, dict):
            return {}
        return {str(k): _norm_score(val) for k, val in v.items() if _is_num(val)}


def _is_num(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


# 显式字段列表，不用 "any"：决策 023 同款 leak —— "any" 会把 LangGraph 内部字段
# （thread_id/__pregel_*）透传给模型 SDK，openai 客户端（Kimi/DeepSeek）直接拒绝。
critic_configurable_model = init_chat_model(
    configurable_fields=("model", "max_tokens", "api_key", "base_url", "thinking_budget"),
)


def _save_kg_if_enabled(
    state: AgentState,
    config: RunnableConfig,
    configurable: Configuration,
    chart_htmls: list[str] | None = None,
) -> None:
    """KG 写入兜底：在 visualize 终点调用一次，失败不阻断。

    chart_htmls 显式传入本轮新渲染的图表——不能读 state.get("chart_htmls")，因为
    visualize 调用本函数时图表还在 Command(update=...) 里、尚未合并进 state。
    critique 此时已从 critic 的 Command 合并进 state，直接读即可。
    """
    if not configurable.enable_kg:
        return
    try:
        mode_config = state.get("mode_config") or resolve_mode(config)
        save_research(
            research_brief=state.get("research_brief", ""),
            notes=state.get("notes", []) or [],
            final_report=str(state.get("final_report", "")),
            mode=mode_config.mode,
            critique=state.get("critique"),
            chart_htmls=chart_htmls if chart_htmls is not None else (state.get("chart_htmls") or []),
            revision_count=state.get("revision_count", 0),
            research_topic=_first_user_text(state.get("messages") or []),
        )
    except Exception:
        pass


def _first_user_text(messages: list) -> str:
    """取首条用户消息的纯文本 = 用户原始研究主题（多模态时只抽 text 段）。"""
    for m in messages:
        role = getattr(m, "type", None) or (m.get("role") if isinstance(m, dict) else None)
        if role not in ("human", "user"):
            continue
        content = getattr(m, "content", None)
        if content is None and isinstance(m, dict):
            content = m.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            return " ".join(t for t in parts if t).strip()
        return ""
    return ""


async def finalize_research(
    state: AgentState,
    config: RunnableConfig,
    configurable: Configuration,
    chart_htmls: list[str] | None = None,
) -> None:
    """研究收尾：写 KG +（可选）导出 Obsidian 知识库。两者失败均不阻断。

    由 visualize 节点（图的真正终点）调用——此时 critique 与图表都已就绪。
    chart_htmls 显式传入本轮渲染结果（state 里尚未合并）。
    """
    _save_kg_if_enabled(state, config, configurable, chart_htmls=chart_htmls)
    if getattr(configurable, "enable_obsidian_export", False):
        try:
            from open_deep_research.obsidian_export import export_to_vault
            mode_config = state.get("mode_config") or resolve_mode(config)
            await export_to_vault(state, configurable, config, mode_config.mode)
        except Exception:
            pass


async def critic_node(
    state: AgentState, config: RunnableConfig
) -> Command[Literal["final_report_generation", "format_adapter"]]:
    """Audit the final report with a different model than the writer.

    路由：
    - critic 禁用 / rubric 缺失 / LLM 失败 → 终止（KG 保存最终版本后 END）
    - passed=true → 终止
    - passed=false 且 revision_count < max_revisions → 回 final_report_generation
    - passed=false 且 revision_count >= max_revisions → 终止（max 兜底）
    """
    configurable = Configuration.from_runnable_config(config)

    # plan 005: 研究失败时直接 END，跳过 critic 评分（避免污染 bad-case 列表 + 省一次 LLM 调用）
    if state.get("research_failed"):
        return Command(
            goto="format_adapter",
            update={
                "critique": {
                    "score": 0,
                    "passed": False,
                    "criteria_breakdown": {},
                    "conflicts": [],
                    "improvement_suggestions": [],
                    "model_used": "skipped:research_failed",
                    "error": f"research_failed: {state.get('research_failure_reason', '')}",
                }
            },
        )

    if not configurable.enable_critic:
        # 收尾（写 KG / Obsidian）统一在 visualize 终点做，critic 只负责路由
        return Command(goto="format_adapter")

    mode_config = state.get("mode_config") or resolve_mode(config)
    rubric = mode_config.critic_rubric

    if not rubric.system_prompt:
        return Command(goto="format_adapter")

    # 冲突检测优先用 audit_findings（final_report 清空 notes 前存的多源原始快照）；
    # 缺失时退回 notes，再缺则提示仅审终稿自洽性
    notes = state.get("notes", []) or []
    audit_findings = state.get("audit_findings") or ""
    if audit_findings:
        findings = audit_findings
    elif notes:
        findings = "\n\n".join(notes)
    else:
        findings = "（注意：notes 已清空，请仅基于 final_report 自洽性评分）"

    prompt = rubric.system_prompt.format(
        date=get_today_str(),
        research_brief=state.get("research_brief", ""),
        findings=findings,
        final_report=state.get("final_report", ""),
        constitution_rules=mode_config.constitution_rules,
    )

    model_config = {
        "model": configurable.critic_model,
        "max_tokens": configurable.critic_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.critic_model, config),
    }
    if configurable.critic_model.startswith("google_genai:"):
        model_config["thinking_budget"] = 0
    _critic_base_url = get_base_url_for_model(configurable.critic_model)
    if _critic_base_url:
        model_config["base_url"] = _critic_base_url

    critic_model = (
        critic_configurable_model
        .with_structured_output(CriticReport, method="function_calling")
        .with_retry(stop_after_attempt=3)  # 抗瞬时连接错误 + 结构化偶发失败
        .with_config(model_config)
    )

    try:
        report = await critic_model.ainvoke([HumanMessage(content=prompt)])
        report.model_used = configurable.critic_model
        report.passed = report.score >= rubric.pass_threshold
    except Exception as e:
        # critic 失败时不阻断主流程：写错误评分卡进 state，收尾在 visualize 终点做
        import traceback
        print(f"[critic_failed] {configurable.critic_model}: {e!r}", flush=True)
        traceback.print_exc()
        return Command(
            goto="format_adapter",
            update={
                "critique": {
                    "score": 0,
                    "passed": False,
                    "criteria_breakdown": {},
                    "conflicts": [],
                    "improvement_suggestions": [],
                    "model_used": configurable.critic_model,
                    "error": f"critic_failed: {e}",
                }
            },
        )

    # 路由决策
    revision_count = state.get("revision_count", 0)
    already_escalated = bool(state.get("escalated"))
    # plan 006: escalation 优先级高于 revise — 极低分直接换强模型重写
    should_escalate = (
        configurable.enable_escalation
        and not already_escalated
        and report.score <= configurable.escalation_threshold
    )
    if should_escalate:
        return Command(
            goto="final_report_generation",
            update={
                "critique": report.model_dump(),
                "escalated": True,
                # 不自增 revision_count：escalation 与 revise 正交
            },
        )

    # strict_audit：首轮无论分数都强制修订一次（演示修订前→后对比）
    force_revise = getattr(configurable, "strict_audit", False) and revision_count == 0
    should_revise = (force_revise or not report.passed) and (revision_count < configurable.max_revisions)

    if should_revise:
        return Command(
            goto="final_report_generation",
            update={
                "critique": report.model_dump(),
                "revision_count": revision_count + 1,
            },
        )

    # 终止分支：评分卡进 state，收尾（写 KG + Obsidian）在 visualize 终点统一做
    return Command(
        goto="format_adapter",
        update={"critique": report.model_dump()},
    )
