"""Graph state definitions and data structures for the Deep Research agent."""

import operator
from typing import Annotated, Optional

from langchain_core.messages import MessageLikeRepresentation
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field
from src.modes.schema import ModeConfig
from typing_extensions import TypedDict


###################
# Structured Outputs
###################
class ConductResearch(BaseModel):
    """Call this tool to conduct research on a specific topic."""
    research_topic: str = Field(
        description="The topic to research. Should be a single topic, and should be described in high detail (at least a paragraph).",
    )

class ResearchComplete(BaseModel):
    """Call this tool to indicate that the research is complete."""

class Summary(BaseModel):
    """Research summary with key findings."""
    
    summary: str
    key_excerpts: str

class ClarifyWithUser(BaseModel):
    """Model for user clarification requests."""
    
    need_clarification: bool = Field(
        description="Whether the user needs to be asked a clarifying question.",
    )
    question: str = Field(
        description="A question to ask the user to clarify the report scope",
    )
    verification: str = Field(
        description="Verify message that we will start research after the user has provided the necessary information.",
    )

class ResearchQuestion(BaseModel):
    """Research question and brief for guiding research."""
    
    research_brief: str = Field(
        description="A research question that will be used to guide the research.",
    )


###################
# State Definitions
###################

def override_reducer(current_value, new_value):
    """Reducer function that allows overriding values in state."""
    if isinstance(new_value, dict) and new_value.get("type") == "override":
        return new_value.get("value", new_value)
    else:
        return operator.add(current_value, new_value)
    
class AgentInputState(MessagesState):
    """InputState is only 'messages' plus optional file attachments."""
    # plan 009 Phase A: 多模态附件（前端上传，ingest_attachments 节点处理后清空）
    attachments: list[dict] = []

class AgentState(MessagesState):
    """Main agent state containing messages and research data."""
    
    supervisor_messages: Annotated[list[MessageLikeRepresentation], override_reducer]
    research_brief: Optional[str]
    mode_config: Optional[ModeConfig] = None
    raw_notes: Annotated[list[str], override_reducer] = []
    notes: Annotated[list[str], override_reducer] = []
    final_report: str
    # critic 冲突检测用：final_report_generation 清空 notes 前存一份只读快照，
    # 让 critic 能基于多源原始发现找跨源冲突（notes 清空设计不变）
    audit_findings: str = ""
    critique: Optional[dict] = None
    revision_count: int = 0
    research_failed: bool = False
    research_failure_reason: str = ""
    # plan 006: HITL + Escalation
    pending_user_action: str = ""        # "" | "confirm_brief"
    escalated: bool = False              # 每个 task 最多 escalate 1 次
    escalation_model_used: str = ""      # 记录 escalation 实际用的模型
    # plan 007: Format Adapter
    formatted_report: str = ""           # 套模板后的最终交付版本（保留 final_report 原文便于调试）
    # plan 009 Phase A: 多模态输入
    attachments: list[dict] = []         # 上传附件列表，ingest_attachments 节点消费
    ingested_context: str = ""           # 附件提取的纯文本（调试 + 前端展示用）
    # plan 009 Phase B: 数据可视化
    chart_htmls: list[str] = []          # Plotly 图表 HTML 字符串列表（自包含，可直接嵌入前端）

class SupervisorState(TypedDict):
    """State for the supervisor that manages research tasks."""
    
    supervisor_messages: Annotated[list[MessageLikeRepresentation], override_reducer]
    research_brief: str
    notes: Annotated[list[str], override_reducer] = []
    research_iterations: int = 0
    raw_notes: Annotated[list[str], override_reducer] = []

class ResearcherState(TypedDict):
    """State for individual researchers conducting research."""
    
    researcher_messages: Annotated[list[MessageLikeRepresentation], operator.add]
    tool_call_iterations: int = 0
    research_topic: str
    compressed_research: str
    raw_notes: Annotated[list[str], override_reducer] = []

class ResearcherOutputState(BaseModel):
    """Output state from individual researchers."""
    
    compressed_research: str
    raw_notes: Annotated[list[str], override_reducer] = []
