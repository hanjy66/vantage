"""GAP 分析：当前研究主题 / JD ⇄ 过去研究「查重」+ 能力对标（plan 018，原 plan 010 升级）。

核心用途从"JD 能力对标"升级为"**查重防重复跑**"：给定一个研究主题或 JD，先结构化召回重叠的
历史研究（带 id 可回看），按相关度规则给出 skip/incremental/proceed 建议；有命中时再用一次 LLM
产出能力对标 + 摘要。设计=「LLM 提议、代码裁决」：overlaps（含 id/相关度）全由代码从召回结果构造
（不让 LLM 复述 id，避免编号错乱），LLM 只产能力对标与散文，recommendation 由 LLM 提议+规则兜底。
"""

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from open_deep_research.configuration import Configuration
from open_deep_research.deep_researcher import configurable_model
from open_deep_research.kg_store import recall_relevant, recall_relevant_records
from open_deep_research.utils import get_api_key_for_model

# 查重阈值（语义余弦）：极高→几乎确定重复(skip)；中→相关可增量(incremental)
_SKIP_COS = 0.72
_PARTIAL_COS = 0.55
# 2gram 回退路径的命中 gram 数阈值（无 embedding 时）
_SKIP_GRAM = 12
_PARTIAL_GRAM = 8


class GapItem(BaseModel):
    """单条能力对标结果。"""

    skill: str = Field(description="JD/主题要求的关键能力项")
    status: Literal["covered", "partial", "gap"] = Field(
        description="覆盖程度：covered 已覆盖 / partial 部分 / gap 缺口"
    )
    note: str = Field(description="简短依据，引用研究组合中的证据或说明缺口")


class OverlapRef(BaseModel):
    """命中的一条过去研究（带 id 供前端回看）。"""

    record_id: str
    title: str
    date: str
    overlap: Literal["high", "medium", "low"]
    note: str


class CoverageResult(BaseModel):
    """GAP 查重 + 能力对标结果。"""

    recommendation: Literal["skip", "incremental", "proceed"] = Field(
        description="skip 已充分覆盖建议跳过 / incremental 部分覆盖建议增量 / proceed 无覆盖放心跑"
    )
    summary: str = Field(description="一句话：与过去研究的重叠程度 + 建议")
    overlaps: list[OverlapRef] = Field(default_factory=list, description="命中的过去研究（带 id）")
    skill_gaps: list[GapItem] = Field(default_factory=list, description="能力对标 5-8 条")


class _LlmGap(BaseModel):
    """LLM 只产这三项；overlaps/recommendation 兜底由代码裁决。"""

    summary: str = Field(description="一句话总体判断：与过去研究的重叠程度 + 是否值得重跑")
    recommendation: Literal["skip", "incremental", "proceed"]
    skill_gaps: list[GapItem] = Field(description="5-8 条最重要的能力对标")


_SYSTEM = """你是职业发展 + 研究规划分析专家。给定一个「研究主题或 JD」和候选人的历史研究组合，做两件事：

1. 查重判断 recommendation：
   - skip（建议跳过）：历史研究已充分覆盖该主题，重跑是浪费
   - incremental（建议增量）：有相关但不全，只需补差异部分
   - proceed（放心跑）：历史组合基本没覆盖
2. 能力对标 skill_gaps：逐条提取该主题/JD 的关键能力要求，判断候选人覆盖度
   - covered（已覆盖）：组合中有明确证据 / partial（部分）：有相关但不充分 / gap（缺口）：无相关内容

【严格规则】
1. 只依据提供的「研究组合」判断，不臆造候选人未展示的能力
2. 每条 note 给简短依据：covered/partial 引用组合中的证据，gap 说明缺什么
3. skill_gaps 提取 5-8 条最重要的能力项，优先权重高的硬要求
4. summary 一句话给出总体匹配/重叠判断"""

_HUMAN = """# 研究主题 / JD
{query}

# 候选人历史研究组合（深度研究记录摘录）
{portfolio}

请按规则输出查重建议 + 能力对标。"""


def _overlap_level(score: float, matched_by: str) -> str:
    """把召回分数映射成重叠等级（代码裁决，不交给 LLM）。"""
    if matched_by == "semantic":
        if score >= _SKIP_COS:
            return "high"
        if score >= _PARTIAL_COS:
            return "medium"
        return "low"
    # 2gram 回退：score 是命中 gram 数
    if score >= _SKIP_GRAM:
        return "high"
    if score >= _PARTIAL_GRAM:
        return "medium"
    return "low"


async def analyze_coverage_gap(query: str, config: dict) -> CoverageResult:
    """查重 + 能力对标。无命中→规则短路 proceed（零 LLM）；有命中→一次 LLM 出对标，recommendation 规则兜底。"""
    hits = recall_relevant_records(query, top_k=5)

    # overlaps 全由代码从召回结果构造（含 id），不让 LLM 复述 id（避免编号错乱）。
    overlaps = [
        OverlapRef(
            record_id=h["id"],
            title=h["title"],
            date=h["date"],
            overlap=_overlap_level(h["score"], h["matched_by"]),
            note=f"{'语义' if h['matched_by'] == 'semantic' else '字面'}相关度 {h['score']:.2f}",
        )
        for h in hits
    ]

    # 规则短路：无任何重叠 → 放心跑，省掉 LLM 调用。
    if not hits:
        return CoverageResult(
            recommendation="proceed",
            summary="未找到与此主题重叠的历史研究，可放心开跑。",
            overlaps=[],
            skill_gaps=[],
        )

    configurable = Configuration.from_runnable_config(config)
    portfolio = recall_relevant(query, top_k=5, max_chars_per_record=2000) or "（暂无相关历史研究记录）"
    model_config = {
        "model": configurable.research_model,
        "max_tokens": 4096,
        "api_key": get_api_key_for_model(configurable.research_model, config),
        "tags": ["langsmith:nostream"],
    }
    model = (
        configurable_model
        .with_structured_output(_LlmGap, method="function_calling")
        .with_retry(stop_after_attempt=2)
        .with_config(model_config)
    )
    llm: _LlmGap = await model.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=_HUMAN.format(query=query[:6000], portfolio=portfolio[:8000])),
    ])

    # recommendation 规则兜底：语义极高分→强制 skip（防 LLM 低估重复）。
    top_sem = max((h["score"] for h in hits if h["matched_by"] == "semantic"), default=0.0)
    recommendation = llm.recommendation
    if top_sem >= _SKIP_COS:
        recommendation = "skip"

    return CoverageResult(
        recommendation=recommendation,
        summary=llm.summary,
        overlaps=overlaps,
        skill_gaps=llm.skill_gaps,
    )
