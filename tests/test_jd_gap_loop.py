"""plan 011 JD 闭环单测 — 零 LLM 调用。

覆盖：
- P3 种子 + 召回（kg_store，纯本地）
- P1 JD PDF 文本抽取（mock extract_pdf_text）
- /jd-gap 空输入早返回（不触发 LLM）
"""

import asyncio
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))


def test_seed_and_recall(tmp_path, monkeypatch):
    """P3：写入历史研究后能被 recall 召回（飞轮地基）。"""
    import open_deep_research.kg_store as kg

    monkeypatch.setattr(kg, "KG_DIR", tmp_path)
    kg.save_research(
        research_brief="LLM 应用架构 多 agent 编排",
        notes=["多 agent 编排与上下文工程，supervisor/researcher 分层"],
        final_report="多 agent 编排与上下文工程",
        mode="general",
    )
    out = kg.recall_relevant("LLM 应用架构 多 agent 编排 上下文")
    assert out and "agent" in out


def test_jd_text_from_upload(monkeypatch):
    """P1：upload_id 的 PDF/图片附件被抽成 JD 文本（PDF 走文本层，零 LLM）。"""
    import server.app as app

    monkeypatch.setitem(
        app._PENDING_UPLOADS, "u1", [{"type": "pdf", "path": "/fake.pdf", "purpose": "auto"}]
    )
    # process_attachment 对 PDF 有文本层时直接返回，不调 LLM
    monkeypatch.setattr(
        "open_deep_research.multimodal.extract_pdf_text",
        lambda p: ("字节 AIPM JD：要求 LLM 应用架构、评测体系", True),
    )
    txt = asyncio.run(app._jd_text_from_upload("u1"))
    assert "AIPM JD" in txt
    assert "u1" not in app._PENDING_UPLOADS  # 一次性消费


def test_jd_gap_empty_returns_no_content_without_llm():
    """空 jd + 无 upload → 早返回，不调 LLM。"""
    import server.app as app

    res = asyncio.run(app.jd_gap(app.JdGapRequest(jd="", upload_id="")))
    assert res["items"] == []
    assert "未提供" in res["summary"]
