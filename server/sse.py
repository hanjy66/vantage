"""SSE 事件序列化：把 LangGraph astream_events 映射成前端可消费的 {type, payload}。

事件协议（前端 lib/sse.ts 消费）：
  event: node     data: {"node","stage","phase":"start"|"end"}   —— 进度时间线点亮
  event: result   data: {critique, chart_htmls, final_report, revision_count, ...} —— 评分卡/图表
  event: tokens   data: {"input","output","total"}              —— 真实累计 token（成本面板）
  event: interrupt data: {"thread_id","draft_brief","instruction",...} —— HITL 暂停，等前端确认/编辑 brief
  event: error    data: {"message"}
  event: done     data: {}                                       —— 流结束

设计：只透传主图顶层节点，子图内部节点（supervisor/researcher）不外泄，保持时间线干净。
"""

import json
from typing import Any, AsyncIterator

# 主图顶层节点 → 时间线阶段标签（北极星：展示"如何控制/审计/修订/评估"）
NODE_STAGE: dict[str, str] = {
    "ingest_attachments": "读取输入",
    "clarify_with_user": "澄清意图",
    "write_research_brief": "规划",
    "confirm_research_brief": "确认计划",
    "research_supervisor": "检索研究",
    "final_report_generation": "综合报告",
    "critic": "跨模型审计",
    "format_adapter": "格式适配",
    "visualize": "数据可视化",
}

# result 事件要从节点输出里捞的状态字段
_RESULT_FIELDS = (
    "critique",
    "chart_htmls",
    "final_report",
    "research_brief",  # plan 019：供前端「下载存档」打包研究简报
    "revision_count",
    "research_failed",
    "research_failure_reason",
    "escalated",
    "escalation_model_used",
)


def sse_pack(event: str, data: Any) -> str:
    """打包成 SSE 线格式。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_result(output: Any) -> dict | None:
    """从节点输出里抽出前端关心的状态字段；没有则返回 None。

    节点可能返回 Command(update={...})（critic/write_research_brief 等）或普通 dict。
    Command 的状态写在 .update 里，需先解包；普通 dict 的 .update 是方法，isinstance 不会误伤。
    """
    update = getattr(output, "update", None)
    if isinstance(update, dict):
        output = update
    if not isinstance(output, dict):
        return None
    picked = {k: output[k] for k in _RESULT_FIELDS if k in output}
    return picked or None


def _usage_from_output(output: Any) -> dict | None:
    """从 on_chat_model_end 的输出里抽 usage_metadata（langchain AIMessage 标准字段）。"""
    usage = getattr(output, "usage_metadata", None)
    if isinstance(usage, dict) and usage.get("total_tokens"):
        return usage
    # 部分 provider 把 usage 放在 generations[0].message 上
    gens = getattr(output, "generations", None)
    if gens:
        try:
            msg = gens[0][0].message
            usage = getattr(msg, "usage_metadata", None)
            if isinstance(usage, dict) and usage.get("total_tokens"):
                return usage
        except (IndexError, AttributeError):
            pass
    return None


async def graph_event_stream(
    graph, graph_input: dict, config: dict
) -> AsyncIterator[str]:
    """消费 astream_events，产出 SSE 字符串流。"""
    seen_runs: set[str] = set()
    tokens = {"input": 0, "output": 0, "total": 0}
    try:
        async for ev in graph.astream_events(graph_input, config=config, version="v2"):
            etype = ev.get("event")
            name = ev.get("name", "")

            # 每次模型调用结束 → 累计真实 token，下发 Token 面板
            if etype == "on_chat_model_end":
                usage = _usage_from_output((ev.get("data") or {}).get("output"))
                if usage:
                    tokens["input"] += usage.get("input_tokens", 0)
                    tokens["output"] += usage.get("output_tokens", 0)
                    tokens["total"] += usage.get("total_tokens", 0)
                    yield sse_pack("tokens", dict(tokens))
                continue

            # 顶层节点 start/end → 时间线
            if name in NODE_STAGE and etype in ("on_chain_start", "on_chain_end"):
                run_id = ev.get("run_id", "")
                key = f"{run_id}:{etype}"
                if key in seen_runs:
                    continue
                seen_runs.add(key)
                phase = "start" if etype == "on_chain_start" else "end"
                yield sse_pack("node", {
                    "node": name,
                    "stage": NODE_STAGE[name],
                    "phase": phase,
                })

                # 节点结束时若带关键状态，发 result（评分卡/图表/报告）
                if etype == "on_chain_end":
                    output = (ev.get("data") or {}).get("output")
                    result = _extract_result(output)
                    if result:
                        yield sse_pack("result", result)

        # 流结束后检查是否停在 HITL 中断（confirm_research_brief 的 interrupt()）
        intr = await _pending_interrupt(graph, config)
        if intr is not None:
            tid = (config.get("configurable") or {}).get("thread_id", "")
            yield sse_pack("interrupt", {"thread_id": tid, **intr})

        yield sse_pack("done", {})
    except Exception as e:  # noqa: BLE001 — 流式层兜底，错误下发前端而非 500
        yield sse_pack("error", {"message": str(e)})
        yield sse_pack("done", {})


async def _pending_interrupt(graph, config: dict) -> dict | None:
    """图停在 interrupt() 时，从 checkpoint 取出中断 payload（draft_brief 等）。"""
    aget_state = getattr(graph, "aget_state", None)
    if aget_state is None:
        return None
    try:
        snapshot = await aget_state(config)
    except Exception:  # noqa: BLE001 — 无 checkpointer / 无状态时安静跳过
        return None
    for task in getattr(snapshot, "tasks", None) or []:
        for it in getattr(task, "interrupts", None) or []:
            val = getattr(it, "value", None)
            if isinstance(val, dict):
                return val
    return None
