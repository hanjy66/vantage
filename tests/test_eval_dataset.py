"""Smoke tests for the eval dataset — no LLM calls, no network."""

import json
from pathlib import Path

QUERIES_PATH = Path(__file__).resolve().parents[1] / "data" / "eval" / "queries.jsonl"

REQUIRED_FIELDS = {"id", "research_brief", "mode", "category", "tags", "min_score"}
VALID_MODES = {"general", "interview"}


def load_queries():
    with open(QUERIES_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_dataset_exists():
    assert QUERIES_PATH.exists(), f"eval dataset not found: {QUERIES_PATH}"


def test_dataset_size():
    queries = load_queries()
    assert len(queries) >= 20, f"需要至少 20 条，当前 {len(queries)} 条"


def test_all_required_fields():
    queries = load_queries()
    for q in queries:
        missing = REQUIRED_FIELDS - q.keys()
        assert not missing, f"{q.get('id', '?')} 缺字段: {missing}"


def test_unique_ids():
    queries = load_queries()
    ids = [q["id"] for q in queries]
    assert len(ids) == len(set(ids)), "存在重复 id"


def test_valid_modes():
    queries = load_queries()
    for q in queries:
        assert q["mode"] in VALID_MODES, f"{q['id']}: 无效 mode={q['mode']}"


def test_research_brief_not_empty():
    queries = load_queries()
    for q in queries:
        assert len(q["research_brief"].strip()) >= 20, f"{q['id']}: research_brief 过短"


def test_min_score_range():
    queries = load_queries()
    for q in queries:
        assert 0 <= q["min_score"] <= 10, f"{q['id']}: min_score 超出范围"
