"""plan 018 — GAP 查重重定义 + 结构化召回 + 回看接口（最小 LLM）。"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))


# ─── kg_store：结构化召回 + by-id 读取 ─────────────────────────────────────────

def test_recall_relevant_records_carries_id_and_score(tmp_path, monkeypatch):
    import open_deep_research.kg_store as kg

    monkeypatch.setattr(kg, "KG_DIR", tmp_path)
    rid = kg.save_research(
        research_brief="豆包 vs Kimi 竞品对比 商业化",
        notes=["豆包字节，Kimi 月之暗面"],
        final_report="对比报告",
        mode="interview",
    )
    hits = kg.recall_relevant_records("豆包 Kimi 竞品 商业化 对比")
    assert hits and hits[0]["id"] == rid
    assert "score" in hits[0] and hits[0]["matched_by"] in ("semantic", "2gram")
    assert hits[0]["date"] and hits[0]["mode"] == "interview"


def test_get_record_hit_miss_and_traversal(tmp_path, monkeypatch):
    import open_deep_research.kg_store as kg

    monkeypatch.setattr(kg, "KG_DIR", tmp_path)
    rid = kg.save_research("主题", ["n"], "报告正文", mode="general")
    assert kg.get_record(rid)["final_report"] == "报告正文"
    assert kg.get_record("does-not-exist") is None
    # 防路径穿越
    assert kg.get_record("../secret") is None
    assert kg.get_record("a/b") is None


# ─── analyze_coverage_gap：规则短路 + recommendation 兜底 ──────────────────────

def test_coverage_overlap_level_thresholds():
    from server.jd_gap import _overlap_level

    assert _overlap_level(0.8, "semantic") == "high"
    assert _overlap_level(0.6, "semantic") == "medium"
    assert _overlap_level(0.3, "semantic") == "low"
    assert _overlap_level(15, "2gram") == "high"
    assert _overlap_level(9, "2gram") == "medium"
    assert _overlap_level(3, "2gram") == "low"


def test_coverage_no_hits_short_circuits_without_llm(monkeypatch):
    """无召回命中 → proceed + 空，且不调 LLM。"""
    import server.jd_gap as jg

    monkeypatch.setattr(jg, "recall_relevant_records", lambda q, top_k=5: [])
    # 若误调 LLM 会因 configurable_model 真初始化而暴露——这里断言不会走到
    res = asyncio.run(jg.analyze_coverage_gap("全新主题", {"configurable": {"mode": "general"}}))
    assert res.recommendation == "proceed"
    assert res.overlaps == [] and res.skill_gaps == []


class _FakeModel:
    """链式 no-op，ainvoke 返回固定 _LlmGap（模拟 LLM 提议 proceed）。"""

    def with_structured_output(self, *a, **k):
        return self

    def with_retry(self, *a, **k):
        return self

    def with_config(self, *a, **k):
        return self

    async def ainvoke(self, _msgs):
        from server.jd_gap import GapItem, _LlmGap
        return _LlmGap(
            recommendation="proceed",  # 故意低估，看代码是否兜底成 skip
            summary="LLM 认为可 proceed",
            skill_gaps=[GapItem(skill="LLM 架构", status="covered", note="历史已覆盖")],
        )


def test_coverage_high_semantic_overrides_to_skip(monkeypatch):
    """语义高分命中 → 代码兜底强制 skip（即便 LLM 提议 proceed），并保留能力对标。"""
    import server.jd_gap as jg

    monkeypatch.setattr(jg, "recall_relevant_records", lambda q, top_k=5: [
        {"id": "r1", "title": "豆包 vs Kimi", "date": "2026-06-02", "mode": "interview",
         "score": 0.81, "matched_by": "semantic"},
    ])
    monkeypatch.setattr(jg, "recall_relevant", lambda *a, **k: "历史研究组合文本")
    monkeypatch.setattr(jg, "get_api_key_for_model", lambda *a, **k: "fake")
    monkeypatch.setattr(jg, "configurable_model", _FakeModel())

    res = asyncio.run(jg.analyze_coverage_gap("豆包 Kimi 对比", {"configurable": {"mode": "general"}}))
    assert res.recommendation == "skip"  # 规则兜底覆盖了 LLM 的 proceed
    assert res.overlaps[0].record_id == "r1" and res.overlaps[0].overlap == "high"
    assert res.skill_gaps and res.skill_gaps[0].status == "covered"  # 通用模式也产能力对标


# ─── 回看端点 ─────────────────────────────────────────────────────────────────

def test_kg_record_endpoint_hit_and_404(tmp_path, monkeypatch):
    import open_deep_research.kg_store as kg
    import server.app as app

    monkeypatch.setattr(kg, "KG_DIR", tmp_path)
    rid = kg.save_research("回看主题", ["n"], "## 报告\n正文内容", mode="general")
    ok = asyncio.run(app.kg_record(rid))
    assert ok["final_report"] == "## 报告\n正文内容" and ok["id"] == rid
    miss = asyncio.run(app.kg_record("nope"))
    assert getattr(miss, "status_code", None) == 404


def test_jd_gap_endpoint_never_raises_returns_readable_error(monkeypatch):
    """LLM 抛异常（如余额不足）时，端点返回可读错误而非裸 500——避免前端 "Failed to fetch"。"""
    import server.app as app

    async def _boom(query, config):
        raise RuntimeError("Error code: 402 - Insufficient Balance")

    monkeypatch.setattr(app, "analyze_coverage_gap", _boom)
    res = asyncio.run(app.jd_gap(app.JdGapRequest(query="对比 A 和 B", mode="interview")))
    assert "GAP 分析失败" in res["summary"]
    assert "余额不足" in res["summary"]
    assert res["overlaps"] == [] and res["items"] == []


def test_kg_download_returns_markdown_file(tmp_path, monkeypatch):
    import open_deep_research.kg_store as kg
    import server.app as app

    monkeypatch.setattr(kg, "KG_DIR", tmp_path)
    rid = kg.save_research("下载主题", ["n"], "报告正文 abc", mode="general")
    resp = asyncio.run(app.kg_record_download(rid))
    body = resp.body.decode("utf-8") if isinstance(resp.body, bytes) else resp.body
    assert "报告正文 abc" in body and "## 研究简报" in body
    assert "attachment" in resp.headers.get("content-disposition", "")
