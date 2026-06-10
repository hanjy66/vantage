"""Configuration management for the Open Deep Research system."""

import os
from enum import Enum
from typing import Any, List, Optional

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field


class SearchAPI(Enum):
    """Enumeration of available search API providers."""
    
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    TAVILY = "tavily"
    DUCKDUCKGO = "duckduckgo"
    NONE = "none"

class MCPConfig(BaseModel):
    """Configuration for Model Context Protocol (MCP) servers."""
    
    url: Optional[str] = Field(
        default=None,
        optional=True,
    )
    """The URL of the MCP server"""
    tools: Optional[List[str]] = Field(
        default=None,
        optional=True,
    )
    """The tools to make available to the LLM"""
    auth_required: Optional[bool] = Field(
        default=False,
        optional=True,
    )
    """Whether the MCP server requires authentication"""

class Configuration(BaseModel):
    """Main configuration class for the Deep Research agent."""

    # Mode selector — routes prompts via src/modes/{mode}.yaml
    mode: str = Field(
        default="general",
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "general",
                "description": "研究模式：general 通用，interview 面试备战",
                "options": [
                    {"label": "General (通用)", "value": "general"},
                    {"label": "Interview (AI PM 面试)", "value": "interview"},
                ],
            }
        },
    )

    # General Configuration
    max_structured_output_retries: int = Field(
        default=3,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 3,
                "min": 1,
                "max": 10,
                "description": "Maximum number of retries for structured output calls from models"
            }
        }
    )
    allow_clarification: bool = Field(
        default=True,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": True,
                "description": "Whether to allow the researcher to ask the user clarifying questions before starting research"
            }
        }
    )
    enable_kg: bool = Field(
        default=True,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": True,
                "description": "是否启用知识图谱跨会话记忆（历史研究自动召回）"
            }
        }
    )
    enable_critic: bool = Field(
        default=True,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": True,
                "description": "是否启用 Critic 节点对最终报告做跨模型质量审计"
            }
        }
    )
    enable_obsidian_export: bool = Field(
        default=False,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": False,
                "description": "研究完成后抽取实体+关系，导出为可导入 Obsidian 的知识库 vault（带 [[双链]] 图谱）"
            }
        }
    )
    critic_model: str = Field(
        default="openai:moonshot-v1-128k",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "openai:moonshot-v1-128k",
                "description": "Critic 用的模型，必须与 final_report_model 不同源以构成跨模型校验（DeepSeek 写 · Kimi 审）。用 moonshot-v1（无 thinking），与 method=function_calling 的强制 tool_choice 兼容；kimi-k2.x 的 thinking 与强制 tool_choice 互斥"
            }
        }
    )
    critic_model_max_tokens: int = Field(
        default=4096,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 4096,
                "description": "Critic 模型最大输出 token（结构化输出短，4096 足够）"
            }
        }
    )
    max_revisions: int = Field(
        default=1,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 1,
                "min": 0,
                "max": 3,
                "step": 1,
                "description": "Critic 不通过时最大 revise 轮数。0 表示禁用 revise，行为等同 plan 003"
            }
        }
    )
    strict_audit: bool = Field(
        default=False,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": False,
                "description": "严格审计：critic 首轮无论分数都强制触发一次 revise，用于演示「修订前→后」对比"
            }
        }
    )
    research_failure_min_notes_chars: int = Field(
        default=200,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 200,
                "description": "notes 总字符数低于此阈值视为研究失败（plan 005 哨兵阈值）"
            }
        }
    )
    research_failure_error_ratio: float = Field(
        default=0.5,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 0.5,
                "description": "notes 中错误标记行占比超过此阈值视为研究失败（plan 005）"
            }
        }
    )
    enable_hitl_planner_confirm: bool = Field(
        default=False,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": False,
                "description": "plan 006: 是否在 write_research_brief 后暂停让用户确认/修改 brief（eval batch 必须 False）"
            }
        }
    )
    enable_escalation: bool = Field(
        default=False,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": False,
                "description": "plan 006: critic 极低分时是否自动切更强模型重写 final_report"
            }
        }
    )
    escalation_model: str = Field(
        default="openai:deepseek-reasoner",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "openai:deepseek-reasoner",
                "description": "plan 006: escalation 触发时切到的模型（DeepSeek-R1 推理模型，比 deepseek-chat 更强）"
            }
        }
    )
    escalation_threshold: int = Field(
        default=3,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 3,
                "min": 0,
                "max": 10,
                "step": 1,
                "description": "plan 006: critic 评分 ≤ 此阈值触发 escalation（默认 3）"
            }
        }
    )
    # plan 009 Phase A: 多模态输入
    enable_multimodal_input: bool = Field(
        default=True,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": True,
                "description": "plan 009: 是否启用多模态输入（PDF/图片/截图）。无附件时自动 passthrough，eval batch 零影响"
            }
        }
    )
    vision_model: str = Field(
        default="openai:moonshot-v1-128k-vision-preview",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "openai:moonshot-v1-128k-vision-preview",
                "description": "plan 009: 图片/扫描件 vision 分析用的模型（Moonshot 视觉，支持图片输入）"
            }
        }
    )
    max_attachment_images: int = Field(
        default=5,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 5,
                "min": 1,
                "max": 20,
                "description": "plan 009: 单次请求最多处理的图片数量上限（控制 vision token 成本）"
            }
        }
    )
    # plan 009 Phase B: 数据可视化
    enable_visualization: bool = Field(
        default=False,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": False,
                "description": "plan 009: 是否启用报告数据可视化（Plotly 图表）。eval batch 默认关闭"
            }
        }
    )
    max_charts: int = Field(
        default=3,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 3,
                "min": 1,
                "max": 5,
                "step": 1,
                "description": "plan 009: 每份报告最多生成图表数量"
            }
        }
    )
    chart_model: str = Field(
        default="openai:moonshot-v1-128k",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "openai:moonshot-v1-128k",
                "description": "plan 009: 图表数据抽取用的模型（嵌套结构化输出 specs→data_points；deepseek 对该 schema 常不调工具返回 None，moonshot-v1-128k 实测稳定）"
            }
        }
    )
    max_concurrent_research_units: int = Field(
        default=5,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 5,
                "min": 1,
                "max": 20,
                "step": 1,
                "description": "Maximum number of research units to run concurrently. This will allow the researcher to use multiple sub-agents to conduct research. Note: with more concurrency, you may run into rate limits."
            }
        }
    )
    # Research Configuration
    search_api: SearchAPI = Field(
        default=SearchAPI.TAVILY,
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": "tavily",
                "description": "Search API to use for research. NOTE: Make sure your Researcher Model supports the selected search API.",
                "options": [
                    {"label": "Tavily", "value": SearchAPI.TAVILY.value},
                    {"label": "OpenAI Native Web Search", "value": SearchAPI.OPENAI.value},
                    {"label": "Anthropic Native Web Search", "value": SearchAPI.ANTHROPIC.value},
                    {"label": "None", "value": SearchAPI.NONE.value}
                ]
            }
        }
    )
    max_researcher_iterations: int = Field(
        default=6,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 6,
                "min": 1,
                "max": 10,
                "step": 1,
                "description": "Maximum number of research iterations for the Research Supervisor. This is the number of times the Research Supervisor will reflect on the research and ask follow-up questions."
            }
        }
    )
    max_react_tool_calls: int = Field(
        default=10,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 10,
                "min": 1,
                "max": 30,
                "step": 1,
                "description": "Maximum number of tool calling iterations to make in a single researcher step."
            }
        }
    )
    # Model Configuration
    summarization_model: str = Field(
        default="openai:deepseek-chat",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "openai:gpt-4.1-mini",
                "description": "Model for summarizing research results from Tavily search results"
            }
        }
    )
    summarization_model_max_tokens: int = Field(
        default=8192,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 8192,
                "description": "Maximum output tokens for summarization model"
            }
        }
    )
    max_content_length: int = Field(
        default=50000,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 50000,
                "min": 1000,
                "max": 200000,
                "description": "Maximum character length for webpage content before summarization"
            }
        }
    )
    research_model: str = Field(
        default="openai:deepseek-chat",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "openai:gpt-4.1",
                "description": "Model for conducting research. NOTE: Make sure your Researcher Model supports the selected search API."
            }
        }
    )
    research_model_max_tokens: int = Field(
        default=10000,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 10000,
                "description": "Maximum output tokens for research model"
            }
        }
    )
    compression_model: str = Field(
        default="openai:deepseek-chat",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "openai:deepseek-chat",
                "description": "Model for compressing research findings from sub-agents. NOTE: Make sure your Compression Model supports the selected search API."
            }
        }
    )
    compression_model_max_tokens: int = Field(
        default=8192,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 8192,
                "description": "Maximum output tokens for compression model"
            }
        }
    )
    final_report_model: str = Field(
        default="openai:deepseek-chat",
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "openai:deepseek-chat",
                "description": "Model for writing the final report from all research findings"
            }
        }
    )
    final_report_model_max_tokens: int = Field(
        default=16000,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 16000,
                "description": "Maximum output tokens for final report model"
            }
        }
    )
    # MCP server configuration
    mcp_config: Optional[MCPConfig] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "mcp",
                "description": "MCP server configuration"
            }
        }
    )
    mcp_prompt: Optional[str] = Field(
        default=None,
        optional=True,
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "description": "Any additional instructions to pass along to the Agent regarding the MCP tools that are available to it."
            }
        }
    )


    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = config.get("configurable", {}) if config else {}
        field_names = list(cls.model_fields.keys())
        values: dict[str, Any] = {
            field_name: os.environ.get(field_name.upper(), configurable.get(field_name))
            for field_name in field_names
        }
        return cls(**{k: v for k, v in values.items() if v is not None})

    class Config:
        """Pydantic configuration."""
        
        arbitrary_types_allowed = True
