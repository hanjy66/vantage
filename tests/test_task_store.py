"""Plan 008 unit tests — SQLite 任务状态机。"""

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

import pytest

from open_deep_research.task_store import (
    TaskStatus,
    create_task,
    get_task,
    list_tasks,
    stats,
    update_status,
)


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


def test_create_and_get(tmp_db):
    tid = create_task("研究简报 X", user_id="u1", mode="general", db_path=tmp_db)
    row = get_task(tid, db_path=tmp_db)
    assert row is not None
    assert row["status"] == "created"
    assert row["research_brief"] == "研究简报 X"
    assert row["mode"] == "general"
    assert row["score"] is None
    assert row["completed_at"] is None


def test_status_transitions(tmp_db):
    tid = create_task("brief", db_path=tmp_db)
    update_status(tid, TaskStatus.PLANNING, db_path=tmp_db)
    assert get_task(tid, db_path=tmp_db)["status"] == "planning"

    update_status(tid, TaskStatus.RESEARCHING, db_path=tmp_db)
    update_status(tid, TaskStatus.SYNTHESIZING, db_path=tmp_db)
    update_status(tid, TaskStatus.REVIEWING, db_path=tmp_db)
    update_status(tid, TaskStatus.COMPLETED, score=8, db_path=tmp_db)
    row = get_task(tid, db_path=tmp_db)
    assert row["status"] == "completed"
    assert row["score"] == 8
    assert row["completed_at"] is not None


def test_failure_marks_research_failed(tmp_db):
    tid = create_task("brief", db_path=tmp_db)
    update_status(tid, TaskStatus.FAILED, research_failed=True, error="Tavily 限流", db_path=tmp_db)
    row = get_task(tid, db_path=tmp_db)
    assert row["status"] == "failed"
    assert row["research_failed"] == 1
    assert row["error"] == "Tavily 限流"
    assert row["completed_at"] is not None


def test_list_filters_by_user_and_status(tmp_db):
    t1 = create_task("a", user_id="u1", db_path=tmp_db)
    t2 = create_task("b", user_id="u1", db_path=tmp_db)
    t3 = create_task("c", user_id="u2", db_path=tmp_db)
    update_status(t1, TaskStatus.COMPLETED, score=9, db_path=tmp_db)

    u1_all = list_tasks(user_id="u1", db_path=tmp_db)
    assert len(u1_all) == 2
    assert {r["id"] for r in u1_all} == {t1, t2}

    u1_completed = list_tasks(user_id="u1", status=TaskStatus.COMPLETED, db_path=tmp_db)
    assert len(u1_completed) == 1
    assert u1_completed[0]["id"] == t1

    u2_all = list_tasks(user_id="u2", db_path=tmp_db)
    assert len(u2_all) == 1
    assert u2_all[0]["id"] == t3


def test_stats_aggregates_by_status(tmp_db):
    for _ in range(3):
        create_task("x", user_id="u1", db_path=tmp_db)
    tid = create_task("y", user_id="u1", db_path=tmp_db)
    update_status(tid, TaskStatus.COMPLETED, score=8, db_path=tmp_db)

    s = stats(user_id="u1", db_path=tmp_db)
    assert s["total"] == 4
    assert s["created"] == 3
    assert s["completed"] == 1
    assert s["failed"] == 0


def test_escalated_flag_persisted(tmp_db):
    tid = create_task("brief", db_path=tmp_db)
    update_status(tid, TaskStatus.COMPLETED, score=7, escalated=True, db_path=tmp_db)
    row = get_task(tid, db_path=tmp_db)
    assert row["escalated"] == 1
    assert row["score"] == 7
