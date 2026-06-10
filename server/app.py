"""ADRP Research Control Room — FastAPI 入口（plan 010 Step 2）。

职责：把 LangGraph 包成 SSE 流给前端；REST 入口（JD gap / 打分回流）见 step 2b。
核心 graph 零改动，仅在此 import + 调用。

本地启动（PowerShell）：
    uv run uvicorn server.app:app --reload --port 8000
冒烟：
    curl.exe -N "http://localhost:8000/stream?q=test"
"""

import io
import tempfile
import uuid
import zipfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

_ROOT = Path(__file__).resolve().parents[1]
# override=True：强制 .env 覆盖 shell 里可能残留的空/旧 key
load_dotenv(_ROOT / ".env", override=True)

# 延迟到 import 后再建 graph，避免模块加载即触发模型初始化
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from open_deep_research.deep_researcher import deep_researcher_builder  # noqa: E402

from server.sse import graph_event_stream  # noqa: E402
from server.jd_gap import analyze_coverage_gap  # noqa: E402
from server.feedback import write_feedback  # noqa: E402

# 单进程内复用一个带 checkpointer 的编译图（HITL resume 后续需要 checkpointer）
_checkpointer = MemorySaver()
_graph = deep_researcher_builder.compile(checkpointer=_checkpointer)

app = FastAPI(title="ADRP Research Control Room API")

# 前端 Next.js 本地 + Vercel 预览跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """存活探针。"""
    return {"status": "ok"}


# thread_id → config，供 HITL /resume 用同一份 configurable 续跑（单进程内存，demo 足够）
_PENDING_CONFIGS: dict[str, dict] = {}

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # 关 nginx/代理缓冲，保证逐条下发
}


# upload_id → attachment dicts（{type,path,purpose}），供 /stream 载入多模态附件
_PENDING_UPLOADS: dict[str, list[dict]] = {}
_UPLOAD_DIR = Path(tempfile.gettempdir()) / "adrp_uploads"


@app.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    """plan 009 Phase A：接收 JD PDF / 竞品截图，落临时盘，返回 upload_id 供 /stream 引用。"""
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = str(uuid.uuid4())
    attachments: list[dict] = []
    saved: list[dict] = []
    for f in files:
        name = f.filename or "file"
        ext = Path(name).suffix.lower()
        atype = "pdf" if ext == ".pdf" else "image"
        dest = _UPLOAD_DIR / f"{upload_id}_{name}"
        dest.write_bytes(await f.read())
        attachments.append({"type": atype, "path": str(dest), "purpose": "auto"})
        saved.append({"name": name, "type": atype})
    _PENDING_UPLOADS[upload_id] = attachments
    return {"upload_id": upload_id, "files": saved}


@app.get("/stream")
async def stream(
    q: str = Query(..., description="研究查询 / brief"),
    mode: str = Query("general", description="general | interview"),
    enable_visualization: bool = Query(False, description="plan 009 Phase B 图表"),
    max_revisions: int = Query(1, ge=0, le=3),
    hitl: bool = Query(False, description="开启 brief 确认人机协作（plan 006 interrupt）"),
    upload_id: str = Query("", description="/upload 返回的附件批次 id（plan 009 Phase A）"),
    strict_audit: bool = Query(False, description="严格审计：强制触发一次 revise 演示修订对比"),
    enable_kg: bool = Query(False, description="把本次研究写回 KG（plan 011 定向补缺口用）"),
    enable_obsidian_export: bool = Query(False, description="研究完导出 Obsidian 知识库 vault（plan 015-C）"),
):
    """启动一次研究并以 SSE 流式返回进度/评分/图表。"""
    thread_id = str(uuid.uuid4())
    attachments = _PENDING_UPLOADS.pop(upload_id, []) if upload_id else []
    config = {
        "configurable": {
            "thread_id": thread_id,
            "mode": mode,
            "enable_critic": True,
            "enable_kg": enable_kg,        # 默认 false 不污染；定向补缺口时 true 回写
            "max_revisions": max_revisions,
            "allow_clarification": False,  # headline 三件不走 clarify interrupt
            "enable_visualization": enable_visualization,
            "enable_hitl_planner_confirm": hitl,
            "enable_multimodal_input": bool(attachments),
            "strict_audit": strict_audit,
            "enable_obsidian_export": enable_obsidian_export,
        },
        "run_name": f"control-room:{mode}",
    }
    if hitl:
        _PENDING_CONFIGS[thread_id] = config
    graph_input: dict = {"messages": [{"role": "user", "content": q}]}
    if attachments:
        graph_input["attachments"] = attachments

    return StreamingResponse(
        graph_event_stream(_graph, graph_input, config),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@app.get("/resume")
async def resume(
    thread_id: str = Query(..., description="/stream 中断时返回的 thread_id"),
    action: str = Query("approve", description="approve | edit"),
    final_brief: str = Query("", description="action=edit 时的最终 brief"),
):
    """HITL：用户确认/编辑 brief 后，从 confirm_research_brief 的 interrupt 处续跑。"""
    from langgraph.types import Command

    config = _PENDING_CONFIGS.pop(thread_id, None) or {
        "configurable": {"thread_id": thread_id}
    }
    payload: dict = {"action": action}
    if action == "edit" and final_brief.strip():
        payload["final_brief"] = final_brief
    resume_input = Command(resume=payload)

    return StreamingResponse(
        graph_event_stream(_graph, resume_input, config),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ─── REST: JD gap 分析（plan 010 Step 2b）────────────────────────────────────

class JdGapRequest(BaseModel):
    query: str = ""  # plan 018：研究主题或 JD（统一入口）
    jd: str = ""  # 向后兼容：旧前端传 jd
    mode: str = "general"
    upload_id: str = ""  # 传 JD/主题 的 PDF/截图 → 抽文本


async def _jd_text_from_upload(upload_id: str) -> str:
    """plan 011 P1：从 upload 批次抽 JD 文本——PDF 走文本层，截图走 vision。"""
    atts = _PENDING_UPLOADS.pop(upload_id, [])
    if not atts:
        return ""
    from open_deep_research.multimodal import process_attachment
    from open_deep_research.deep_researcher import configurable_model
    from open_deep_research.configuration import Configuration
    from open_deep_research.utils import get_api_key_for_model, get_base_url_for_model

    conf = Configuration()
    vm = conf.vision_model
    mcfg = {"model": vm, "max_tokens": conf.research_model_max_tokens, "api_key": get_api_key_for_model(vm, {})}
    bu = get_base_url_for_model(vm)
    if bu:
        mcfg["base_url"] = bu

    parts: list[str] = []
    for att in atts:
        txt = await process_attachment(att, configurable_model, mcfg)
        if txt and not txt.startswith("[附件解析失败"):
            parts.append(txt)
    return "\n\n".join(parts)


@app.post("/jd-gap")
async def jd_gap(req: JdGapRequest):
    """查重：当前研究主题/JD ⇄ 过去研究（防重复跑）+ 能力对标。plan 018 升级，向后兼容旧 jd 字段。"""
    query = (req.query or req.jd or "").strip()
    if req.upload_id:
        att_text = await _jd_text_from_upload(req.upload_id)
        query = (query + "\n\n" + att_text).strip() if query else att_text
    if not query.strip():
        return {"recommendation": "proceed", "summary": "未提供研究主题/JD 内容（文本或附件）。",
                "overlaps": [], "skill_gaps": [], "items": []}
    config = {"configurable": {"mode": req.mode}}
    # 兜底：任何异常（LLM 余额不足/超时/限流等）都返回可读错误，绝不抛裸 500——
    # 否则 FastAPI 的 500 缺 CORS 头会被浏览器拦成 "Failed to fetch"，看不出真正原因。
    try:
        result = await analyze_coverage_gap(query, config)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "Insufficient Balance" in msg or "402" in msg:
            hint = "模型账户余额不足（DeepSeek 402），请充值后重试"
        elif "429" in msg or "Too Many Requests" in msg:
            hint = "模型限流（429），稍后重试"
        elif "timeout" in msg.lower():
            hint = "分析超时，请重试或缩短输入"
        else:
            hint = f"分析服务出错：{msg[:140]}"
        return {"recommendation": "proceed", "summary": f"GAP 分析失败 — {hint}",
                "overlaps": [], "skill_gaps": [], "items": []}
    out = result.model_dump()
    out["items"] = out["skill_gaps"]  # 向后兼容：旧前端读 items
    return out


# ─── REST: 历史研究回看 / 下载（plan 018 点1）─────────────────────────────────

@app.get("/kg")
async def kg_list():
    """历史研究库：列出全部已存研究的摘要（plan 022 整页网格用）。裸异常返可读错误防 CORS 拦。"""
    try:
        from open_deep_research.kg_store import list_records
        return {"records": list_records()}
    except Exception as e:  # noqa: BLE001
        return {"records": [], "error": str(e)[:140]}


@app.get("/kg/{record_id}")
async def kg_record(record_id: str):
    """回看一条历史研究（只读）：返回 brief + 报告 + 评分卡 + 图表，供前端原样回看。"""
    from open_deep_research.kg_store import get_record
    rec = get_record(record_id)
    if rec is None:
        return Response(status_code=404, content="record not found")
    return {
        "id": rec.get("id", ""),
        "date": (rec.get("timestamp", "") or "")[:10],
        "mode": rec.get("mode", ""),
        "research_topic": rec.get("research_topic", ""),
        "research_brief": rec.get("research_brief", ""),
        "final_report": rec.get("final_report", ""),
        "critique": rec.get("critique"),
        "chart_htmls": rec.get("chart_htmls", []),
        "revision_count": rec.get("revision_count", 0),
    }


@app.get("/kg/{record_id}/download")
async def kg_record_download(record_id: str):
    """下载历史研究为 markdown 文件（brief + 报告）。"""
    from open_deep_research.kg_store import get_record
    rec = get_record(record_id)
    if rec is None:
        return Response(status_code=404, content="record not found")
    date = (rec.get("timestamp", "") or "")[:10]
    md = (
        f"# 历史研究存档\n\n"
        f"- 日期：{date}\n- 模式：{rec.get('mode', '')}\n\n"
        f"## 研究简报\n\n{rec.get('research_brief', '')}\n\n"
        f"## 报告\n\n{rec.get('final_report', '')}\n"
    )
    filename = f"research-{record_id[:8]}.md"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── REST: 用户打分回流（plan 010 Step 2b）───────────────────────────────────

class FeedbackRequest(BaseModel):
    research_brief: str
    user_score: int  # 0-10 人评
    report_preview: str = ""
    comment: str = ""
    mode: str = "general"
    run_id: str = ""  # 前端每次 start() 生成的 UUID，精确锚定当轮研究


@app.post("/feedback")
async def feedback(req: FeedbackRequest):
    """落盘用户评分并自动纳入评测集（人评×机评飞轮）。"""
    return write_feedback(
        research_brief=req.research_brief,
        user_score=req.user_score,
        report_preview=req.report_preview,
        comment=req.comment,
        mode=req.mode,
        run_id=req.run_id,
    )


@app.get("/export-vault")
async def export_vault():
    """把累积的 Obsidian 知识库 vault 打包成 zip 下载（plan 015-C）。"""
    from open_deep_research.obsidian_export import get_vault_dir

    vault = get_vault_dir()
    if not vault.exists() or not any(vault.rglob("*.md")):
        return Response(
            status_code=404,
            content="知识库为空：请先开启『导出 Obsidian 知识库』开关并跑一次研究。",
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in vault.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(vault.parent))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="adrp-obsidian-vault.zip"'},
    )
