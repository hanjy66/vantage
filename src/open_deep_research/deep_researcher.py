"""Main LangGraph implementation for the Deep Research agent."""

import asyncio
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    filter_messages,
    get_buffer_string,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from src.modes.router import resolve_mode

from open_deep_research.configuration import (
    Configuration,
)
from open_deep_research.critic import critic_node, finalize_research
from open_deep_research.kg_store import recall_relevant
from open_deep_research.multimodal import process_attachment
from open_deep_research.visualize import (
    ChartExtractionResult,
    GATE_AND_EXTRACT_HUMAN,
    GATE_AND_EXTRACT_SYSTEM,
    validate_spec,
    render_chart,
    render_critique_fallback_chart,
)
from open_deep_research.arch_diagram import ARCH_PLACEHOLDER, build_arch_mermaid, inject_arch_diagram
from open_deep_research.prompts import (
    compress_research_simple_human_message,
    compress_research_system_prompt,
    research_system_prompt,
)
from open_deep_research.state import (
    AgentInputState,
    AgentState,
    ClarifyWithUser,
    ConductResearch,
    ResearchComplete,
    ResearcherOutputState,
    ResearcherState,
    ResearchQuestion,
    SupervisorState,
)
from open_deep_research.utils import (
    anthropic_websearch_called,
    get_all_tools,
    get_api_key_for_model,
    get_base_url_for_model,
    get_model_token_limit,
    get_notes_from_tool_calls,
    get_today_str,
    is_token_limit_exceeded,
    openai_websearch_called,
    remove_up_to_last_ai_message,
    think_tool,
)

def _model_cfg(model_name: str, max_tokens: int, api_key, **extra) -> dict:
    """Build a with_config dict, auto-injecting base_url for proxy-backed models."""
    cfg: dict = {"model": model_name, "max_tokens": max_tokens, "api_key": api_key, **extra}
    base_url = get_base_url_for_model(model_name)
    if base_url:
        cfg["base_url"] = base_url
    return cfg


# Initialize a configurable model that we will use throughout the agent
configurable_model = init_chat_model(
    configurable_fields=("model", "max_tokens", "api_key", "base_url"),
)

# Separate model for final_report: explicit field list including thinking_budget
# (决策 016 修复 gemini-flash 截断依赖透传 thinking_budget；决策 023 修复 'any' 把
# LangGraph 内部字段 thread_id/__pregel_* 泄漏给 DeepSeek 客户端导致 TypeError)
final_report_configurable_model = init_chat_model(
    configurable_fields=("model", "max_tokens", "api_key", "thinking_budget", "base_url"),
)

async def ingest_attachments(
    state: AgentState, config: RunnableConfig
) -> Command[Literal["clarify_with_user"]]:
    """plan 009 Phase A: 多模态输入预处理节点（context firewall）。

    无附件或 enable_multimodal_input=False → 直接 passthrough。
    有附件 → 并发处理（PDF 文本/扫描件 vision + 图片 vision）→ 拼成 ingested_context
    → 追加一条 HumanMessage，下游节点通过 get_buffer_string 自动获取，零下游改动。
    """
    configurable = Configuration.from_runnable_config(config)
    attachments = list(state.get("attachments") or [])

    if not attachments or not configurable.enable_multimodal_input:
        return Command(goto="clarify_with_user")

    # 超出图片上限时截断（PDF 不计入图片数）
    pdfs = [a for a in attachments if a.get("type") == "pdf"]
    images = [a for a in attachments if a.get("type") != "pdf"]
    if len(images) > configurable.max_attachment_images:
        images = images[: configurable.max_attachment_images]
    attachments = pdfs + images

    vision_model_config = {
        "model": configurable.vision_model,
        "max_tokens": configurable.research_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.vision_model, config),
    }
    _vision_base_url = get_base_url_for_model(configurable.vision_model)
    if _vision_base_url:
        vision_model_config["base_url"] = _vision_base_url

    # 并发处理所有附件
    results = await asyncio.gather(
        *[process_attachment(att, configurable_model, vision_model_config) for att in attachments]
    )

    valid = [r for r in results if r and not r.startswith("[附件解析失败")]
    if not valid:
        return Command(goto="clarify_with_user", update={"ingested_context": ""})

    ingested_context = "\n\n---\n\n".join(valid)
    context_msg = HumanMessage(
        content=(
            "[用户上传资料摘要 — 请将以下内容作为研究背景与补充信息]\n\n"
            + ingested_context
        )
    )
    return Command(
        goto="clarify_with_user",
        update={
            "ingested_context": ingested_context,
            "messages": [context_msg],
        },
    )


async def clarify_with_user(state: AgentState, config: RunnableConfig) -> Command[Literal["write_research_brief", "__end__"]]:
    """Analyze user messages and ask clarifying questions if the research scope is unclear.
    
    This function determines whether the user's request needs clarification before proceeding
    with research. If clarification is disabled or not needed, it proceeds directly to research.
    
    Args:
        state: Current agent state containing user messages
        config: Runtime configuration with model settings and preferences
        
    Returns:
        Command to either end with a clarifying question or proceed to research brief
    """
    # Step 1: Resolve mode and check if clarification is enabled in configuration
    mode_config = resolve_mode(config)
    configurable = Configuration.from_runnable_config(config)
    if not configurable.allow_clarification:
        # Skip clarification step and proceed directly to research
        return Command(
            goto="write_research_brief",
            update={"mode_config": mode_config},
        )
    
    # Step 2: Prepare the model for structured clarification analysis
    messages = state["messages"]
    model_config = _model_cfg(
        configurable.research_model,
        configurable.research_model_max_tokens,
        get_api_key_for_model(configurable.research_model, config),
        tags=["langsmith:nostream"],
    )
    
    # Configure model with structured output and retry logic
    clarification_model = (
        configurable_model
        .with_structured_output(ClarifyWithUser, method="function_calling")
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        .with_config(model_config)
    )
    
    # Step 3: Analyze whether clarification is needed
    prompt_content = mode_config.prompts.clarify_with_user.format(
        messages=get_buffer_string(messages), 
        date=get_today_str()
    )
    response = await clarification_model.ainvoke([HumanMessage(content=prompt_content)])
    
    # Step 4: Route based on clarification analysis
    if response.need_clarification:
        # End with clarifying question for user
        return Command(
            goto=END, 
            update={
                "messages": [AIMessage(content=response.question)],
                "mode_config": mode_config,
            }
        )
    else:
        # Proceed to research with verification message
        return Command(
            goto="write_research_brief", 
            update={
                "messages": [AIMessage(content=response.verification)],
                "mode_config": mode_config,
            }
        )


async def write_research_brief(state: AgentState, config: RunnableConfig) -> Command[Literal["confirm_research_brief"]]:
    """Transform user messages into a structured research brief and initialize supervisor.
    
    This function analyzes the user's messages and generates a focused research brief
    that will guide the research supervisor. It also sets up the initial supervisor
    context with appropriate prompts and instructions.
    
    Args:
        state: Current agent state containing user messages
        config: Runtime configuration with model settings
        
    Returns:
        Command to proceed to research supervisor with initialized context
    """
    # Step 1: Set up the research model for structured output
    configurable = Configuration.from_runnable_config(config)
    mode_config = state.get("mode_config") or resolve_mode(config)
    research_model_config = _model_cfg(
        configurable.research_model,
        configurable.research_model_max_tokens,
        get_api_key_for_model(configurable.research_model, config),
        tags=["langsmith:nostream"],
    )

    # Configure model for structured research question generation
    research_model = (
        configurable_model
        .with_structured_output(ResearchQuestion, method="function_calling")
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        .with_config(research_model_config)
    )
    
    # Step 2: Generate structured research brief from user messages
    prompt_content = mode_config.prompts.transform_messages_into_research_topic.format(
        messages=get_buffer_string(state.get("messages", [])),
        date=get_today_str()
    )
    response = await research_model.ainvoke([HumanMessage(content=prompt_content)])
    
    # Step 3: Recall relevant past research for supervisor context
    kg_context = ""
    if configurable.enable_kg:
        recalled = await asyncio.to_thread(recall_relevant, response.research_brief)
        if recalled:
            kg_context = (
                "\n\n<past_research>\n"
                "以下是与本次研究主题相关的历史研究内容，可作为参考，避免重复研究已知内容：\n\n"
                f"{recalled}\n"
                "</past_research>"
            )

    # Step 4: Initialize supervisor with research brief and instructions
    supervisor_system_prompt = mode_config.prompts.lead_researcher.format(
        date=get_today_str(),
        max_concurrent_research_units=configurable.max_concurrent_research_units,
        max_researcher_iterations=configurable.max_researcher_iterations,
        kg_context=kg_context
    )
    
    return Command(
        goto="confirm_research_brief",
        update={
            "research_brief": response.research_brief,
            "mode_config": mode_config,
            "supervisor_messages": {
                "type": "override",
                "value": [
                    SystemMessage(content=supervisor_system_prompt),
                    HumanMessage(content=response.research_brief)
                ]
            }
        }
    )


async def confirm_research_brief(
    state: AgentState, config: RunnableConfig
) -> Command[Literal["research_supervisor"]]:
    """plan 006: HITL planner 确认节点。

    enable_hitl_planner_confirm=False（默认） → 直通 research_supervisor
    enable_hitl_planner_confirm=True → interrupt() 暂停，等用户审查/编辑 brief
      用户 resume payload 格式：
        {"action": "approve"}             → 用现有 brief 继续
        {"action": "edit", "final_brief": "..."}  → 用 edit 后的 brief 重建 supervisor_messages
    """
    configurable = Configuration.from_runnable_config(config)
    if not configurable.enable_hitl_planner_confirm:
        return Command(goto="research_supervisor")

    # interrupt 仅在启用 checkpointer 时生效（LangGraph Studio 自动启用）
    from langgraph.types import interrupt

    user_payload = interrupt({
        "pending_action": "confirm_brief",
        "draft_brief": state.get("research_brief", ""),
        "instruction": "请审查研究简报。返回 {\"action\":\"approve\"} 直接开跑，"
                       "或 {\"action\":\"edit\",\"final_brief\":\"...\"} 修改后开跑。",
    })

    action = (user_payload or {}).get("action", "approve")
    if action == "edit" and (user_payload or {}).get("final_brief"):
        new_brief = user_payload["final_brief"]
        # 重建 supervisor_messages（保留 system_prompt 不变，换 HumanMessage 内容）
        old_msgs = state.get("supervisor_messages", [])
        system_msg = next((m for m in old_msgs if isinstance(m, SystemMessage)), None)
        rebuilt = [system_msg, HumanMessage(content=new_brief)] if system_msg else [HumanMessage(content=new_brief)]
        return Command(
            goto="research_supervisor",
            update={
                "research_brief": new_brief,
                "supervisor_messages": {"type": "override", "value": rebuilt},
                "pending_user_action": "",
            },
        )

    # approve：直通
    return Command(
        goto="research_supervisor",
        update={"pending_user_action": ""},
    )


async def supervisor(state: SupervisorState, config: RunnableConfig) -> Command[Literal["supervisor_tools"]]:
    """Lead research supervisor that plans research strategy and delegates to researchers.
    
    The supervisor analyzes the research brief and decides how to break down the research
    into manageable tasks. It can use think_tool for strategic planning, ConductResearch
    to delegate tasks to sub-researchers, or ResearchComplete when satisfied with findings.
    
    Args:
        state: Current supervisor state with messages and research context
        config: Runtime configuration with model settings
        
    Returns:
        Command to proceed to supervisor_tools for tool execution
    """
    # Step 1: Configure the supervisor model with available tools
    configurable = Configuration.from_runnable_config(config)
    research_model_config = _model_cfg(
        configurable.research_model,
        configurable.research_model_max_tokens,
        get_api_key_for_model(configurable.research_model, config),
        tags=["langsmith:nostream"],
    )

    # Available tools: research delegation, completion signaling, and strategic thinking
    lead_researcher_tools = [ConductResearch, ResearchComplete, think_tool]
    
    # Configure model with tools, retry logic, and model settings
    research_model = (
        configurable_model
        .bind_tools(lead_researcher_tools)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        .with_config(research_model_config)
    )
    
    # Step 2: Generate supervisor response based on current context
    supervisor_messages = state.get("supervisor_messages", [])
    response = await research_model.ainvoke(supervisor_messages)
    
    # Step 3: Update state and proceed to tool execution
    return Command(
        goto="supervisor_tools",
        update={
            "supervisor_messages": [response],
            "research_iterations": state.get("research_iterations", 0) + 1
        }
    )

async def supervisor_tools(state: SupervisorState, config: RunnableConfig) -> Command[Literal["supervisor", "__end__"]]:
    """Execute tools called by the supervisor, including research delegation and strategic thinking.
    
    This function handles three types of supervisor tool calls:
    1. think_tool - Strategic reflection that continues the conversation
    2. ConductResearch - Delegates research tasks to sub-researchers
    3. ResearchComplete - Signals completion of research phase
    
    Args:
        state: Current supervisor state with messages and iteration count
        config: Runtime configuration with research limits and model settings
        
    Returns:
        Command to either continue supervision loop or end research phase
    """
    # Step 1: Extract current state and check exit conditions
    configurable = Configuration.from_runnable_config(config)
    supervisor_messages = state.get("supervisor_messages", [])
    research_iterations = state.get("research_iterations", 0)
    most_recent_message = supervisor_messages[-1]
    
    # Define exit criteria for research phase
    exceeded_allowed_iterations = research_iterations > configurable.max_researcher_iterations
    no_tool_calls = not most_recent_message.tool_calls
    research_complete_tool_call = any(
        tool_call["name"] == "ResearchComplete" 
        for tool_call in most_recent_message.tool_calls
    )
    
    # Exit if any termination condition is met
    if exceeded_allowed_iterations or no_tool_calls or research_complete_tool_call:
        return Command(
            goto=END,
            update={
                "notes": get_notes_from_tool_calls(supervisor_messages),
                "research_brief": state.get("research_brief", "")
            }
        )
    
    # Step 2: Process all tool calls together (both think_tool and ConductResearch)
    all_tool_messages = []
    update_payload = {"supervisor_messages": []}
    
    # Handle think_tool calls (strategic reflection)
    think_tool_calls = [
        tool_call for tool_call in most_recent_message.tool_calls 
        if tool_call["name"] == "think_tool"
    ]
    
    for tool_call in think_tool_calls:
        reflection_content = tool_call["args"]["reflection"]
        all_tool_messages.append(ToolMessage(
            content=f"Reflection recorded: {reflection_content}",
            name="think_tool",
            tool_call_id=tool_call["id"]
        ))
    
    # Handle ConductResearch calls (research delegation)
    conduct_research_calls = [
        tool_call for tool_call in most_recent_message.tool_calls 
        if tool_call["name"] == "ConductResearch"
    ]
    
    if conduct_research_calls:
        tool_results: list = []  # 预置：异常路径也能据此抢救已完成研究的 raw_notes
        try:
            # Limit concurrent research units to prevent resource exhaustion
            allowed_conduct_research_calls = conduct_research_calls[:configurable.max_concurrent_research_units]
            overflow_conduct_research_calls = conduct_research_calls[configurable.max_concurrent_research_units:]

            # Execute research tasks in parallel
            research_tasks = [
                researcher_subgraph.ainvoke({
                    "researcher_messages": [
                        HumanMessage(content=tool_call["args"]["research_topic"])
                    ],
                    "research_topic": tool_call["args"]["research_topic"]
                }, config)
                for tool_call in allowed_conduct_research_calls
            ]

            # return_exceptions=True：单个 researcher 报错（如 deepseek 400 / token 超限）不再
            # 把整批 gather 炸掉，避免连累其它已成功 researcher 的 raw_notes（来源 URL）被丢弃。
            tool_results = await asyncio.gather(*research_tasks, return_exceptions=True)

            # Create tool messages with research results（失败的 observation 是 Exception，降级为错误说明）
            for observation, tool_call in zip(tool_results, allowed_conduct_research_calls):
                content = (
                    observation.get("compressed_research", "Error synthesizing research report: Maximum retries exceeded")
                    if isinstance(observation, dict)
                    else f"Error synthesizing research report: {observation}"
                )
                all_tool_messages.append(ToolMessage(
                    content=content,
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"]
                ))

            # Handle overflow research calls with error messages
            for overflow_call in overflow_conduct_research_calls:
                all_tool_messages.append(ToolMessage(
                    content=f"Error: Did not run this research as you have already exceeded the maximum number of concurrent research units. Please try again with {configurable.max_concurrent_research_units} or fewer research units.",
                    name="ConductResearch",
                    tool_call_id=overflow_call["id"]
                ))

            # Aggregate raw notes from all research results（只取成功的 dict observation）
            raw_notes_concat = "\n".join([
                "\n".join(observation.get("raw_notes", []))
                for observation in tool_results
                if isinstance(observation, dict)
            ])

            if raw_notes_concat:
                update_payload["raw_notes"] = [raw_notes_concat]

        except Exception as e:
            # Handle research execution errors
            if is_token_limit_exceeded(e, configurable.research_model) or True:
                # Token limit exceeded or other error - end research phase
                salvage = {
                    "notes": get_notes_from_tool_calls(supervisor_messages),
                    "research_brief": state.get("research_brief", ""),
                }
                # 关键修复：异常也要保住已完成研究的 raw_notes（来源 URL 只在这里），
                # 否则报告来源白名单为空 → 来源链接全丢（badcase：通用研究来源没链接）。
                _rn = "\n".join(
                    "\n".join(o.get("raw_notes", []))
                    for o in tool_results if isinstance(o, dict)
                )
                if _rn:
                    salvage["raw_notes"] = [_rn]
                return Command(goto=END, update=salvage)
    
    # Step 3: Return command with all tool results
    update_payload["supervisor_messages"] = all_tool_messages
    return Command(
        goto="supervisor",
        update=update_payload
    ) 

# Supervisor Subgraph Construction
# Creates the supervisor workflow that manages research delegation and coordination
supervisor_builder = StateGraph(SupervisorState, config_schema=Configuration)

# Add supervisor nodes for research management
supervisor_builder.add_node("supervisor", supervisor)           # Main supervisor logic
supervisor_builder.add_node("supervisor_tools", supervisor_tools)  # Tool execution handler

# Define supervisor workflow edges
supervisor_builder.add_edge(START, "supervisor")  # Entry point to supervisor

# Compile supervisor subgraph for use in main workflow
supervisor_subgraph = supervisor_builder.compile()

async def researcher(state: ResearcherState, config: RunnableConfig) -> Command[Literal["researcher_tools"]]:
    """Individual researcher that conducts focused research on specific topics.
    
    This researcher is given a specific research topic by the supervisor and uses
    available tools (search, think_tool, MCP tools) to gather comprehensive information.
    It can use think_tool for strategic planning between searches.
    
    Args:
        state: Current researcher state with messages and topic context
        config: Runtime configuration with model settings and tool availability
        
    Returns:
        Command to proceed to researcher_tools for tool execution
    """
    # Step 1: Load configuration and validate tool availability
    configurable = Configuration.from_runnable_config(config)
    researcher_messages = state.get("researcher_messages", [])
    
    # Get all available research tools (search, MCP, think_tool)
    tools = await get_all_tools(config)
    if len(tools) == 0:
        raise ValueError(
            "No tools found to conduct research: Please configure either your "
            "search API or add MCP tools to your configuration."
        )
    
    # Step 2: Configure the researcher model with tools
    research_model_config = _model_cfg(
        configurable.research_model,
        configurable.research_model_max_tokens,
        get_api_key_for_model(configurable.research_model, config),
        tags=["langsmith:nostream"],
    )

    # Prepare system prompt with MCP context if available
    researcher_prompt = research_system_prompt.format(
        mcp_prompt=configurable.mcp_prompt or "", 
        date=get_today_str()
    )
    
    # Configure model with tools, retry logic, and settings
    research_model = (
        configurable_model
        .bind_tools(tools)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        .with_config(research_model_config)
    )
    
    # Step 3: Generate researcher response with system context
    messages = [SystemMessage(content=researcher_prompt)] + researcher_messages
    response = await research_model.ainvoke(messages)
    
    # Step 4: Update state and proceed to tool execution
    return Command(
        goto="researcher_tools",
        update={
            "researcher_messages": [response],
            "tool_call_iterations": state.get("tool_call_iterations", 0) + 1
        }
    )

# Tool Execution Helper Function
async def execute_tool_safely(tool, args, config):
    """Safely execute a tool with error handling."""
    try:
        return await tool.ainvoke(args, config)
    except Exception as e:
        return f"Error executing tool: {str(e)}"


async def researcher_tools(state: ResearcherState, config: RunnableConfig) -> Command[Literal["researcher", "compress_research"]]:
    """Execute tools called by the researcher, including search tools and strategic thinking.
    
    This function handles various types of researcher tool calls:
    1. think_tool - Strategic reflection that continues the research conversation
    2. Search tools (tavily_search, web_search) - Information gathering
    3. MCP tools - External tool integrations
    4. ResearchComplete - Signals completion of individual research task
    
    Args:
        state: Current researcher state with messages and iteration count
        config: Runtime configuration with research limits and tool settings
        
    Returns:
        Command to either continue research loop or proceed to compression
    """
    # Step 1: Extract current state and check early exit conditions
    configurable = Configuration.from_runnable_config(config)
    researcher_messages = state.get("researcher_messages", [])
    most_recent_message = researcher_messages[-1]
    
    # Early exit if no tool calls were made (including native web search)
    has_tool_calls = bool(most_recent_message.tool_calls)
    has_native_search = (
        openai_websearch_called(most_recent_message) or 
        anthropic_websearch_called(most_recent_message)
    )
    
    if not has_tool_calls and not has_native_search:
        return Command(goto="compress_research")
    
    # Step 2: Handle other tool calls (search, MCP tools, etc.)
    tools = await get_all_tools(config)
    tools_by_name = {
        tool.name if hasattr(tool, "name") else tool.get("name", "web_search"): tool 
        for tool in tools
    }
    
    # Execute all tool calls in parallel
    tool_calls = most_recent_message.tool_calls
    tool_execution_tasks = [
        execute_tool_safely(tools_by_name[tool_call["name"]], tool_call["args"], config) 
        for tool_call in tool_calls
    ]
    observations = await asyncio.gather(*tool_execution_tasks)
    
    # Create tool messages from execution results
    tool_outputs = [
        ToolMessage(
            content=observation,
            name=tool_call["name"],
            tool_call_id=tool_call["id"]
        ) 
        for observation, tool_call in zip(observations, tool_calls)
    ]
    
    # Step 3: Check late exit conditions (after processing tools)
    exceeded_iterations = state.get("tool_call_iterations", 0) >= configurable.max_react_tool_calls
    research_complete_called = any(
        tool_call["name"] == "ResearchComplete" 
        for tool_call in most_recent_message.tool_calls
    )
    
    if exceeded_iterations or research_complete_called:
        # End research and proceed to compression
        return Command(
            goto="compress_research",
            update={"researcher_messages": tool_outputs}
        )
    
    # Continue research loop with tool results
    return Command(
        goto="researcher",
        update={"researcher_messages": tool_outputs}
    )

async def compress_research(state: ResearcherState, config: RunnableConfig):
    """Compress and synthesize research findings into a concise, structured summary.
    
    This function takes all the research findings, tool outputs, and AI messages from
    a researcher's work and distills them into a clean, comprehensive summary while
    preserving all important information and findings.
    
    Args:
        state: Current researcher state with accumulated research messages
        config: Runtime configuration with compression model settings
        
    Returns:
        Dictionary containing compressed research summary and raw notes
    """
    # Step 1: Configure the compression model
    configurable = Configuration.from_runnable_config(config)
    _compression_base_url = get_base_url_for_model(configurable.compression_model)
    _compression_cfg: dict = {
        "model": configurable.compression_model,
        "max_tokens": configurable.compression_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.compression_model, config),
        "tags": ["langsmith:nostream"],
    }
    if _compression_base_url:
        _compression_cfg["base_url"] = _compression_base_url
    synthesizer_model = configurable_model.with_config(_compression_cfg)
    
    # Step 2: Prepare messages for compression
    researcher_messages = state.get("researcher_messages", [])
    
    # Add instruction to switch from research mode to compression mode
    researcher_messages.append(HumanMessage(content=compress_research_simple_human_message))
    
    # Step 3: Attempt compression with retry logic for token limit issues
    synthesis_attempts = 0
    max_attempts = 3
    
    while synthesis_attempts < max_attempts:
        try:
            # Create system prompt focused on compression task
            compression_prompt = compress_research_system_prompt.format(date=get_today_str())
            messages = [SystemMessage(content=compression_prompt)] + researcher_messages
            
            # Execute compression
            response = await synthesizer_model.ainvoke(messages)
            
            # Extract raw notes from all tool and AI messages
            raw_notes_content = "\n".join([
                str(message.content) 
                for message in filter_messages(researcher_messages, include_types=["tool", "ai"])
            ])
            
            # Return successful compression result
            return {
                "compressed_research": str(response.content),
                "raw_notes": [raw_notes_content]
            }
            
        except Exception as e:
            synthesis_attempts += 1
            
            # Handle token limit exceeded by removing older messages
            if is_token_limit_exceeded(e, configurable.research_model):
                researcher_messages = remove_up_to_last_ai_message(researcher_messages)
                continue
            
            # For other errors, continue retrying
            continue
    
    # Step 4: Return error result if all attempts failed
    raw_notes_content = "\n".join([
        str(message.content) 
        for message in filter_messages(researcher_messages, include_types=["tool", "ai"])
    ])
    
    return {
        "compressed_research": "Error synthesizing research report: Maximum retries exceeded",
        "raw_notes": [raw_notes_content]
    }

# Researcher Subgraph Construction
# Creates individual researcher workflow for conducting focused research on specific topics
researcher_builder = StateGraph(
    ResearcherState, 
    output=ResearcherOutputState, 
    config_schema=Configuration
)

# Add researcher nodes for research execution and compression
researcher_builder.add_node("researcher", researcher)                 # Main researcher logic
researcher_builder.add_node("researcher_tools", researcher_tools)     # Tool execution handler
researcher_builder.add_node("compress_research", compress_research)   # Research compression

# Define researcher workflow edges
researcher_builder.add_edge(START, "researcher")           # Entry point to researcher
researcher_builder.add_edge("compress_research", END)      # Exit point after compression

# Compile researcher subgraph for parallel execution by supervisor
researcher_subgraph = researcher_builder.compile()

def _detect_research_failure(
    notes: list[str], min_chars: int, error_ratio_threshold: float
) -> tuple[bool, str]:
    """plan 005: 检测 research 阶段是否整体失败（Tavily 限流 / API 报错 / notes 全空）。

    返回 (failed, reason)。reason 是诊断字符串，写入 state.research_failure_reason。
    """
    text = "\n".join(notes or [])
    stripped_len = len(text.strip())
    if stripped_len < min_chars:
        return True, f"notes_too_short:{stripped_len}<{min_chars}"

    error_markers = (
        "Error synthesizing",
        "Maximum retries",
        "FAILED_PRECONDITION",
        "Tavily",
        "API key",
        "rate limit",
    )
    non_empty_lines = [ln for ln in text.splitlines() if ln.strip()]
    if not non_empty_lines:
        return True, "no_non_empty_lines"
    error_lines = sum(1 for ln in non_empty_lines if any(m in ln for m in error_markers))
    ratio = error_lines / len(non_empty_lines)
    if ratio > error_ratio_threshold:
        return True, f"error_ratio={error_lines}/{len(non_empty_lines)}={ratio:.2f}"
    return False, ""


def _build_research_failure_report(research_brief: str, reason: str, notes_len: int) -> str:
    """plan 005: 哨兵报告模板，不调 writer。"""
    return (
        "# 研究失败 — 无法生成报告\n\n"
        f"**研究简报**：{research_brief}\n\n"
        f"**失败原因**：{reason}\n\n"
        "**诊断信息**：\n"
        f"- notes 总字符数：{notes_len}\n"
        f"- 失败标志：{reason}\n\n"
        "**建议**：检查搜索 API（Tavily 等）状态、网络与配额后重试。"
        "本报告由系统自动生成，未调用任何 LLM。"
    )


def _extract_source_allowlist(findings: str, exclude_hosts: tuple[str, ...] = ()) -> str:
    """从研究发现里抽出真实检索到的 URL，构成"来源白名单"约束写报告（防编造链接）。

    findings 内 Tavily 结果格式为 "--- SOURCE n: {title} ---\\nURL: {url}"，
    DuckDuckGo 为 "SOURCE: {url}"。这里抽所有 http(s) URL，去重保序，附最近的标题。

    exclude_hosts：要排除的域名（面试模式下排除牛客/知乎面经域名——它们走 interview_links
    单独通道注入「面经原文链接」章节；若再混进数据来源白名单，会挤占引用编号、把真正的数据来源
    挤出前 50 名，导致正文 [n] 引用与末尾「来源」列表对不上）。
    """
    items = _collect_sources(findings, exclude_hosts)
    if not items:
        return "（本次研究未检索到任何带 URL 的来源——请勿在报告中编造任何链接，如实说明缺一手来源）"
    return "\n".join(
        f"[{i}] {title + ' — ' if title else ''}{url}"
        for i, (url, title) in enumerate(items, 1)
    )


def _collect_sources(text: str, exclude_hosts: tuple[str, ...] = ()) -> list[tuple[str, str]]:
    """从工具输出抽 (url, title) 列表，去重保序，上限 50。白名单与末尾「来源」共用此函数，
    保证两者同序同号——正文 [n] 引用因此能与「来源」列表精确对齐。"""
    import re

    def _excluded(u: str) -> bool:
        return any(h in u for h in exclude_hosts)

    seen: dict[str, str] = {}  # url -> title
    for m in re.finditer(r"---\s*SOURCE\s*\d+:\s*(.+?)\s*---\s*\n\s*URL:\s*(\S+)", text):
        title, url = m.group(1).strip(), m.group(2).strip()
        if not _excluded(url):
            seen.setdefault(url, title)
    for url in re.findall(r"https?://[^\s\)\]\}<>\"']+", text):
        url = url.rstrip(".,;")
        if not _excluded(url):
            seen.setdefault(url, "")
    return list(seen.items())[:50]


def _build_sources_section(text: str, exclude_hosts: tuple[str, ...] = ()) -> str:
    """程序化生成「## 来源」markdown 区块（可点击链接），与白名单同序同号。

    由系统在 LLM 写完正文后追加——避免弱模型在输出 token 上限下把「来源」写到一半被截断，
    也避免编号错乱（正文 [n] 直接对应此列表的 [n]）。
    """
    items = _collect_sources(text, exclude_hosts)
    if not items:
        return ""
    lines = ["## 来源", ""]
    for i, (url, title) in enumerate(items, 1):
        lines.append(f"[{i}] [{title or url}]({url})")
    return "\n".join(lines)


# 面经域名：与 search_zh.INTERVIEW_DOMAINS 保持一致。
_INTERVIEW_LINK_HOSTS = ("nowcoder.com", "zhihu.com")


def _extract_interview_links(raw_notes_text: str) -> str:
    """从原始工具输出里旁路抽取所有面经链接（牛客/知乎），逐字全保留、去重保序。

    面经原文链接是 AI_PM 模式最高优先级产出，不能被 compress/summarize 丢掉，
    故从 raw_notes（压缩前，含 "URL:" 行）单独抽，注入报告「面经原文链接」板块。
    上限 30 条（保序取前 30，避免几十上百条链接淹没报告）；报告侧再按主题相关度二次筛选。
    """
    import re

    seen: dict[str, str] = {}  # url -> title
    for m in re.finditer(r"---\s*SOURCE\s*\d+:\s*(.+?)\s*---\s*\n\s*URL:\s*(\S+)", raw_notes_text):
        title, url = m.group(1).strip(), m.group(2).strip()
        if any(h in url for h in _INTERVIEW_LINK_HOSTS):
            seen.setdefault(url, title)
    # 兜底：抽裸 URL 里命中面经域名的
    for url in re.findall(r"https?://[^\s\)\]\}<>\"']+", raw_notes_text):
        url = url.rstrip(".,;")
        if any(h in url for h in _INTERVIEW_LINK_HOSTS):
            seen.setdefault(url, "")

    if not seen:
        return "（本轮未检索到面经链接——请在报告中如实说明，不要编造面经来源）"

    lines = []
    for i, (url, title) in enumerate(list(seen.items())[:30], 1):
        # markdown 可点击列表项；无标题则裸 URL（gfm 自动链接）。
        lines.append(f"- [面经{i}] [{title}]({url})" if title else f"- [面经{i}] {url}")
    return "\n".join(lines)


async def final_report_generation(state: AgentState, config: RunnableConfig):
    """Generate the final comprehensive research report with retry logic for token limits.

    This function takes all collected research findings and synthesizes them into a
    well-structured, comprehensive final report using the configured report generation model.

    Args:
        state: Agent state containing research findings and context
        config: Runtime configuration with model settings and API keys

    Returns:
        Dictionary containing the final report and cleared state
    """
    # Step 1: Extract research findings and prepare state cleanup
    notes = state.get("notes", [])
    cleared_state = {"notes": {"type": "override", "value": []}}
    findings = "\n".join(notes)
    # B 方案：抽真实检索 URL 作来源白名单，约束 writer 只能引用真链接（防编造）。
    # 用 raw_notes（压缩前原始工具输出，含 Tavily "URL:" 行）——compress 会把 URL 丢掉，
    # 所以不能用 findings（压缩后 notes）抽，否则白名单为空。
    raw_notes = state.get("raw_notes", []) or []
    _raw_text = "\n".join(raw_notes) if raw_notes else findings
    # 面经模式下，面经域名走 interview_links 单独通道，从数据来源白名单里排除，避免挤乱引用编号。
    _is_interview = (state.get("mode_config") or resolve_mode(config)).mode == "interview"
    _exclude = _INTERVIEW_LINK_HOSTS if _is_interview else ()
    source_allowlist = _extract_source_allowlist(_raw_text, exclude_hosts=_exclude)
    # 面经链接旁路：只 AI_PM 模板引用 {interview_links}，其它模板忽略此 kwarg。
    interview_links = _extract_interview_links(_raw_text)

    # plan 005: 研究失败检测 — 若整体失败，写哨兵报告并标记 research_failed，
    # critic 节点会因此短路 END，跳过评分 + revise。
    #
    # 重要（plan 008 追查修复）：gate 只在首次进入时跑。
    # revise / escalation 重入时 critique 已存在，且 notes 已被首次 pass 的
    # cleared_state 清空——此时再跑 gate 会误判 notes_too_short，把本应 revise
    # 的报告错误降级为 research_failed（round2 q007/q024 实测被误杀）。
    is_first_pass = state.get("critique") is None
    configurable_for_gate = Configuration.from_runnable_config(config)
    failed, reason = (False, "")
    if is_first_pass:
        failed, reason = _detect_research_failure(
            notes,
            configurable_for_gate.research_failure_min_notes_chars,
            configurable_for_gate.research_failure_error_ratio,
        )
    if failed:
        return {
            "final_report": _build_research_failure_report(
                state.get("research_brief", ""), reason, len("\n".join(notes or []))
            ),
            "messages": [AIMessage(content=f"Research failed: {reason}")],
            "research_failed": True,
            "research_failure_reason": reason,
            **cleared_state,
        }
    
    # Step 2: Configure the final report generation model
    configurable = Configuration.from_runnable_config(config)
    mode_config = state.get("mode_config") or resolve_mode(config)
    # Use final_report_configurable_model (configurable_fields='any') so that
    # extra kwargs like thinking_budget are actually forwarded to the model.
    # Note: 'tags' is NOT included here — it would be treated as a model
    # constructor kwarg by configurable_fields='any' and cause an error.
    # plan 006: escalation 模式时切到 escalation_model（更强模型救严重低分）
    is_escalated = bool(state.get("escalated"))
    if is_escalated:
        writer_model_name = configurable.escalation_model
    else:
        writer_model_name = configurable.final_report_model
    writer_model_config = {
        "model": writer_model_name,
        "max_tokens": configurable.final_report_model_max_tokens,
        "api_key": get_api_key_for_model(writer_model_name, config),
    }
    # Disable thinking for Google Gemini models: thinking tokens share the output budget,
    # causing truncation. With thinking_budget=0, flash gets full 65536 output tokens.
    if writer_model_name.startswith("google_genai:"):
        writer_model_config["thinking_budget"] = 0
    _writer_base_url = get_base_url_for_model(writer_model_name)
    if _writer_base_url:
        writer_model_config["base_url"] = _writer_base_url
    
    # Step 3: Attempt report generation with token limit retry logic
    max_retries = 3
    current_retry = 0
    findings_token_limit = None
    
    # Step 2.5: Build revision_context from previous critique (if revising)
    critique = state.get("critique")
    revision_context = ""
    if critique and not critique.get("error"):
        conflicts_str = "\n".join([
            f"- {c.get('claim_a','')} (来源 {c.get('claim_a_source','')}) vs "
            f"{c.get('claim_b','')} (来源 {c.get('claim_b_source','')}) [{c.get('severity','')}]"
            for c in critique.get("conflicts", [])
        ])
        suggestions_str = "\n".join([
            f"- {s}" for s in critique.get("improvement_suggestions", [])[:10]
        ])
        revision_context = (
            "\n\n<previous_critique>\n"
            f"你上一次生成的报告被评分为 {critique.get('score', 0)}/10（未通过 pass_threshold）。"
            "请基于以下反馈整体重写报告（不是逐条修订，保留原报告全局结构）：\n\n"
            f"**检测到的数据冲突**：\n{conflicts_str or '（无）'}\n\n"
            f"**改进建议（最多 10 条）**：\n{suggestions_str or '（无）'}\n"
            "</previous_critique>"
        )

    while current_retry <= max_retries:
        try:
            # Create comprehensive prompt with all research context
            final_report_prompt = mode_config.prompts.final_report.format(
                research_brief=state.get("research_brief", ""),
                messages=get_buffer_string(state.get("messages", [])),
                findings=findings,
                date=get_today_str(),
                revision_context=revision_context,
                source_allowlist=source_allowlist,
                interview_links=interview_links,
            )

            # Generate the final report
            final_report = await final_report_configurable_model.with_config(writer_model_config).ainvoke([
                HumanMessage(content=final_report_prompt)
            ])

            # KG 写入已移到 visualize 终点（图的真正终点，此时评分卡+图表都就绪），避免 revise 时重复写入

            # 面试模式：章节六（面经链接）+「来源」改由系统程序化追加。
            # 这两段是确定性数据（已抽取），让弱模型在输出 token 上限下逐字重写既浪费 token 又易被截断，
            # 还会编号错乱。故：先剥掉 LLM 可能自行写出的这两段尾部，再用程序化版本追加（保证齐全、可点、对号）。
            # 「来源」段（及面试模式的章节六/架构图）改由系统程序化处理。
            # 根因：研究量大时报告会撑到 deepseek ~8K 输出上限被截断，末尾的来源/链接被丢
            # （BC-07 通用模式版）。来源用白名单程序化追加 → 无论正文怎么截断，来源永远齐全、可点、对号。
            content = final_report.content
            # plan 020：技术架构图——LLM 只写 [[ARCH_DIAGRAM]] 占位符 + 散文，这里抽 ArchSpec →
            # 代码确定性生成 mermaid → 替换占位符（内联原位，永不语法挂）。两个模式通用、按占位符 opt-in：
            # interview 必写占位符（必出图），general 视主题可选写（涉及产品/系统架构才画），无占位符不调 LLM。
            if ARCH_PLACEHOLDER in content:
                try:
                    _arch_model = configurable_model.with_config(_model_cfg(
                        configurable.chart_model,
                        2048,
                        get_api_key_for_model(configurable.chart_model, config),
                        tags=["langsmith:nostream"],
                    ))
                    _mermaid = await build_arch_mermaid(content, _arch_model)
                except Exception:  # noqa: BLE001
                    _mermaid = ""
                content = inject_arch_diagram(content, _mermaid)

            # 剥掉 LLM 自写的「来源」/「章节六」尾部，改用程序化版本追加（两个模式都做）。
            _markers = ["## 来源", "##来源"]
            if _is_interview:
                _markers += ["### 六", "六、面经原文链接"]
            _cut = len(content)
            for _marker in _markers:
                _i = content.find(_marker)
                if _i != -1:
                    _cut = min(_cut, _i)
            content = content[:_cut].rstrip()

            _tail = []
            if _is_interview and interview_links and "未检索到面经链接" not in interview_links:
                _tail.append("### 六、面经原文链接（自行查阅）\n\n" + interview_links)
            _sources = _build_sources_section(_raw_text, exclude_hosts=_exclude)
            if _sources:
                _tail.append(_sources)
            if _tail:
                content = content + "\n\n" + "\n\n".join(_tail) + "\n"
            final_report.content = content

            # Return successful report generation
            return {
                "final_report": final_report.content,
                "messages": [final_report],
                "escalation_model_used": writer_model_name if is_escalated else state.get("escalation_model_used", ""),
                # 清空 notes 前存只读快照供 critic 找冲突；首轮 findings 非空才更新，
                # revise 重入时 notes 已空、findings="" 不覆盖首轮快照
                **({"audit_findings": findings} if findings else {}),
                **cleared_state
            }
            
        except Exception as e:
            # Handle token limit exceeded errors with progressive truncation
            if is_token_limit_exceeded(e, configurable.final_report_model):
                current_retry += 1
                
                if current_retry == 1:
                    # First retry: determine initial truncation limit
                    model_token_limit = get_model_token_limit(configurable.final_report_model)
                    if not model_token_limit:
                        return {
                            "final_report": f"Error generating final report: Token limit exceeded, however, we could not determine the model's maximum context length. Please update the model map in deep_researcher/utils.py with this information. {e}",
                            "messages": [AIMessage(content="Report generation failed due to token limits")],
                            "revision_count": state.get("revision_count", 0) + 1,
                            **cleared_state
                        }
                    # Use 4x token limit as character approximation for truncation
                    findings_token_limit = model_token_limit * 4
                else:
                    # Subsequent retries: reduce by 10% each time
                    findings_token_limit = int(findings_token_limit * 0.9)
                
                # Truncate findings and retry
                findings = findings[:findings_token_limit]
                continue
            else:
                # Non-token-limit error: return error immediately
                return {
                    "final_report": f"Error generating final report: {e}",
                    "messages": [AIMessage(content="Report generation failed due to an error")],
                    "revision_count": state.get("revision_count", 0) + 1,
                    **cleared_state
                }
    
    # Step 4: Return failure result if all retries exhausted
    return {
        "final_report": "Error generating final report: Maximum retries exceeded",
        "messages": [AIMessage(content="Report generation failed after maximum retries")],
        "revision_count": state.get("revision_count", 0) + 1,
        **cleared_state
    }

async def format_adapter(state: AgentState, config: RunnableConfig) -> Command[Literal["visualize"]]:
    """plan 007: 按 mode.output_templates 给 final_report 套模板。

    模板字段（mode yaml output_templates）：
      header: str  | 模板，支持占位 {date} / {mode_display_name} / {score}
      footer: str
      tldr_position: "top" | "bottom" | "none"
      tldr_template: str | TL;DR 段模板，占位 {score} / {passed} / {brief}

    研究失败时（state.research_failed=True）→ passthrough（不污染哨兵报告）。
    output_templates 全空时 → passthrough（formatted_report = final_report）。
    """
    final_report = state.get("final_report", "") or ""
    if state.get("research_failed") or not final_report:
        return Command(goto="visualize", update={"formatted_report": final_report})

    mode_config = state.get("mode_config") or resolve_mode(config)
    templates = getattr(mode_config, "output_templates", {}) or {}

    if not templates:
        return Command(goto="visualize", update={"formatted_report": final_report})

    critique = state.get("critique") or {}
    score = critique.get("score", 0)
    passed = critique.get("passed", False)
    placeholders = {
        "date": get_today_str(),
        "mode_display_name": getattr(mode_config, "display_name", mode_config.mode),
        "score": score,
        "passed": "通过" if passed else "未通过",
        "brief": state.get("research_brief", "")[:200],
    }

    def _fmt(t: str) -> str:
        try:
            return t.format(**placeholders)
        except Exception:
            return t  # 占位符缺失不阻断

    header = _fmt(templates.get("header", ""))
    footer = _fmt(templates.get("footer", ""))
    tldr_pos = templates.get("tldr_position", "none")
    tldr_min = int(templates.get("tldr_min_score", 0))
    tldr = ""
    if tldr_pos in ("top", "bottom") and score >= tldr_min:
        tldr_template = templates.get("tldr_template", "**TL;DR** — 评分 {score}/10（{passed}）。\n\n")
        tldr = _fmt(tldr_template)

    parts = [header]
    if tldr_pos == "top":
        parts.append(tldr)
    parts.append(final_report)
    if tldr_pos == "bottom":
        parts.append("\n\n" + tldr)
    parts.append(footer)
    formatted = "".join(p for p in parts if p)

    return Command(goto="visualize", update={"formatted_report": formatted})


async def visualize(
    state: AgentState, config: RunnableConfig
) -> Command[Literal["__end__"]]:
    """plan 009 Phase B: 数据可视化节点（五阶段保真流水线）。

    enable_visualization=False（默认）→ passthrough，eval batch 零影响。
    enabled → gate → 结构化抽取 → 程序化校验 → Plotly 渲染 → 存 chart_htmls。
    """
    configurable = Configuration.from_runnable_config(config)

    async def _persist_and_end(htmls: list[str]) -> Command:
        # 图的真正终点：研究成功就在此统一写 KG（含本轮图表）+ 导出 Obsidian。
        # chart_htmls 显式传入——此刻图表还在本 Command 的 update 里、尚未合并进 state。
        await finalize_research(state, config, configurable, chart_htmls=htmls)
        return Command(goto=END, update={"chart_htmls": htmls})

    if not configurable.enable_visualization:
        # 可视化关闭：研究仍成功，照样落库（评分卡已在 state），只是没有图表
        return await _persist_and_end([])

    report = state.get("final_report", "") or ""
    if not report or state.get("research_failed"):
        # 研究失败/空报告：不落库（与原行为一致）
        return Command(goto=END, update={"chart_htmls": []})

    async def _finalize(htmls: list[str]) -> Command:
        # plan 012：保证非空——无内容图时用 critic 五维评分兜底（真实元数据，非伪造）
        if not htmls:
            crit = state.get("critique") or {}
            fb = render_critique_fallback_chart(crit.get("criteria_breakdown") or {})
            if fb:
                htmls = [fb]
        return await _persist_and_end(htmls)

    # 抽取模型配置
    chart_model_config = _model_cfg(
        configurable.chart_model,
        4096,
        get_api_key_for_model(configurable.chart_model, config),
        tags=["langsmith:nostream"],
    )

    # Stage 1-2: Gate + 结构化抽取（单次 LLM 调用）
    try:
        extract_model = (
            configurable_model
            .with_structured_output(ChartExtractionResult, method="function_calling")
            .with_retry(stop_after_attempt=2)
            .with_config(chart_model_config)
        )
        from langchain_core.messages import SystemMessage as SM
        # 取前 14000 字：plan 017 后报告变长（6 章节 + 面经清单），竞品矩阵与关键数据速查
        # （最佳可对比数据所在）在前两章，8000 会被截断到看不全，故放宽到 14000。chart_model 为 128k 上下文够用。
        extraction: ChartExtractionResult = await extract_model.ainvoke([
            SM(content=GATE_AND_EXTRACT_SYSTEM),
            HumanMessage(content=GATE_AND_EXTRACT_HUMAN.format(report=report[:14000])),
        ])
    except Exception:
        return await _finalize([])

    # Stage 1 Gate: 无可视化数据 → 兜底元数据图
    # extraction 可能为 None：function_calling 模式下模型未调工具时返回 None 而非抛异常
    if extraction is None or not extraction.has_chartable_data or not extraction.specs:
        return await _finalize([])

    # Stage 3: 程序化校验 + Stage 4-5: 渲染
    chart_htmls: list[str] = []
    for spec in extraction.specs[: configurable.max_charts]:
        validated = validate_spec(spec, report)
        if validated is None:
            continue
        try:
            html = render_chart(validated)
            if html:
                chart_htmls.append(html)
        except Exception:
            continue  # 单图渲染失败不中断

    return await _finalize(chart_htmls)


# Main Deep Researcher Graph Construction
# Creates the complete deep research workflow from user input to final report
deep_researcher_builder = StateGraph(
    AgentState,
    input=AgentInputState,
    config_schema=Configuration
)

# Add main workflow nodes for the complete research process
deep_researcher_builder.add_node("ingest_attachments", ingest_attachments)          # plan 009: 多模态输入预处理
deep_researcher_builder.add_node("clarify_with_user", clarify_with_user)           # User clarification phase
deep_researcher_builder.add_node("write_research_brief", write_research_brief)     # Research planning phase
deep_researcher_builder.add_node("research_supervisor", supervisor_subgraph)       # Research execution phase
deep_researcher_builder.add_node("confirm_research_brief", confirm_research_brief)  # plan 006: HITL planner confirm
deep_researcher_builder.add_node("final_report_generation", final_report_generation)  # Report generation phase
deep_researcher_builder.add_node("critic", critic_node)                            # Cross-model audit phase
deep_researcher_builder.add_node("format_adapter", format_adapter)                  # plan 007: Format Adapter
deep_researcher_builder.add_node("visualize", visualize)                            # plan 009: 数据可视化

# Define main workflow edges for sequential execution
deep_researcher_builder.add_edge(START, "ingest_attachments")                      # Entry: 多模态预处理 → clarify
deep_researcher_builder.add_edge("research_supervisor", "final_report_generation") # Research to report
deep_researcher_builder.add_edge("final_report_generation", "critic")              # Report to critic
# critic 用 Command(goto=...) 路由到 final_report_generation（revise/escalate）或 format_adapter（终止）
# format_adapter 用 Command(goto="visualize")
# visualize 用 Command(goto=END) 终止

# Compile the complete deep researcher workflow
deep_researcher = deep_researcher_builder.compile()
