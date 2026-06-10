"""Unit tests for KG active recall store."""

import json

import open_deep_research.kg_store as kg_module


def test_save_creates_json_file(tmp_path, monkeypatch):
    monkeypatch.setattr(kg_module, "KG_DIR", tmp_path / "kg")

    record_id = kg_module.save_research(
        "Perplexity AI search research",
        ["note 1"],
        "final report",
        mode="interview",
    )

    files = list(kg_module.KG_DIR.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["id"] == record_id
    assert data["mode"] == "interview"
    assert data["research_brief"] == "Perplexity AI search research"


def test_recall_returns_empty_when_no_history(tmp_path, monkeypatch):
    monkeypatch.setattr(kg_module, "KG_DIR", tmp_path / "kg")

    result = kg_module.recall_relevant("AI search")

    assert result == ""


def test_recall_finds_relevant_record(tmp_path, monkeypatch):
    monkeypatch.setattr(kg_module, "KG_DIR", tmp_path / "kg")
    kg_module.save_research(
        "Perplexity AI search research",
        ["note"],
        "Perplexity has answer engine positioning.",
        mode="interview",
    )

    result = kg_module.recall_relevant("AI search Perplexity comparison")

    assert "Perplexity" in result
    assert "<past_research>" not in result


def test_recall_returns_empty_for_unrelated_query(tmp_path, monkeypatch):
    monkeypatch.setattr(kg_module, "KG_DIR", tmp_path / "kg")
    kg_module.save_research(
        "Perplexity AI search research",
        ["note"],
        "final report",
    )

    result = kg_module.recall_relevant("DeFi wallet risk")

    assert result == ""


def test_recall_limits_to_top_k(tmp_path, monkeypatch):
    monkeypatch.setattr(kg_module, "KG_DIR", tmp_path / "kg")
    for i in range(5):
        kg_module.save_research(f"AI search research {i}", [f"note {i}"], f"report {i}")

    result = kg_module.recall_relevant("AI search research", top_k=2)

    assert result.count("---") == 1


# ---------- plan 015-B：语义召回（mock embed，hermetic）----------

def _fake_embed_factory(vectors: dict):
    """按文本前缀返回固定向量；未知文本返回正交向量（不相关）。"""
    def _fake(text, timeout=30):
        for key, vec in vectors.items():
            if key in text:
                return vec
        return [0.0, 0.0, 1.0]  # 与下列 2D 平面向量正交 → cosine 0
    return _fake


def test_semantic_recall_hits_synonym_that_2gram_misses(tmp_path, monkeypatch):
    """语义召回能命中"用词不同但语义相近"——2-gram 字符重叠抓不到的 case。"""
    monkeypatch.setattr(kg_module, "KG_DIR", tmp_path / "kg")
    # 历史 brief 用英文，新 query 用中文 → 2-gram 字符几乎零重叠
    vectors = {
        "ByteDance Doubao strategy": [1.0, 0.0, 0.0],
        "字节跳动豆包战略": [0.96, 0.28, 0.0],  # 与上者高余弦
    }
    monkeypatch.setattr(kg_module, "embed", _fake_embed_factory(vectors))

    kg_module.save_research("ByteDance Doubao strategy", ["n"], "Doubao is ByteDance's AI app.")
    result = kg_module.recall_relevant("字节跳动豆包战略")

    assert "Doubao" in result  # 语义召回命中（2-gram 会漏）


def test_semantic_recall_skips_unrelated(tmp_path, monkeypatch):
    """语义不相关（正交向量）应被阈值挡掉，返回空。"""
    monkeypatch.setattr(kg_module, "KG_DIR", tmp_path / "kg")
    vectors = {"ByteDance Doubao": [1.0, 0.0, 0.0]}
    monkeypatch.setattr(kg_module, "embed", _fake_embed_factory(vectors))

    kg_module.save_research("ByteDance Doubao", ["n"], "report")
    result = kg_module.recall_relevant("完全无关的加密钱包风险")  # 命中正交向量

    assert result == ""
