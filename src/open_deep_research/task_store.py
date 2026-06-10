"""Plan 008: 任务业务状态机（SQLite 持久化）。

LangGraph checkpointer 是技术状态（断点续跑）；本模块是业务状态：
created → planning → researching → synthesizing → reviewing → completed / failed

每条用户研究任务在 data/tasks.db 有一行，UI 可列出任务历史 + 进度条。
设计依据：PRD §5 + 路线图欠账（原 plan 004 任务状态机部分）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "tasks.db"
_DB_LOCK = threading.Lock()  # 简单串行写入，单进程足够


class TaskStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"             # write_research_brief 阶段
    AWAITING_USER = "awaiting_user"   # plan 006 HITL 暂停
    RESEARCHING = "researching"        # supervisor 子图运行中
    SYNTHESIZING = "synthesizing"      # final_report_generation
    REVIEWING = "reviewing"            # critic
    COMPLETED = "completed"
    FAILED = "failed"


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL DEFAULT 'local',
    mode            TEXT NOT NULL DEFAULT 'general',
    research_brief  TEXT,
    status          TEXT NOT NULL,
    score           INTEGER,
    research_failed INTEGER NOT NULL DEFAULT 0,
    escalated       INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    metadata        TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    completed_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect(db_path: Path = _DEFAULT_DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _init_db(db_path: Path = _DEFAULT_DB_PATH) -> None:
    with _DB_LOCK, _connect(db_path) as conn:
        conn.executescript(_CREATE_SQL)


def create_task(
    research_brief: str,
    user_id: str = "local",
    mode: str = "general",
    metadata: Optional[dict] = None,
    db_path: Path = _DEFAULT_DB_PATH,
) -> str:
    """创建一条新任务，返回 task_id。"""
    _init_db(db_path)
    task_id = str(uuid.uuid4())
    now = _now_iso()
    with _DB_LOCK, _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO tasks (id, user_id, mode, research_brief, status, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id, user_id, mode, research_brief,
                TaskStatus.CREATED.value,
                json.dumps(metadata or {}, ensure_ascii=False),
                now, now,
            ),
        )
    return task_id


def update_status(
    task_id: str,
    status: TaskStatus,
    *,
    score: Optional[int] = None,
    research_failed: Optional[bool] = None,
    escalated: Optional[bool] = None,
    error: Optional[str] = None,
    db_path: Path = _DEFAULT_DB_PATH,
) -> None:
    """更新任务状态。仅传非 None 字段被更新。"""
    _init_db(db_path)
    now = _now_iso()
    completed_at = now if status in (TaskStatus.COMPLETED, TaskStatus.FAILED) else None

    fields = ["status = ?", "updated_at = ?"]
    values: list = [status.value, now]
    if score is not None:
        fields.append("score = ?"); values.append(score)
    if research_failed is not None:
        fields.append("research_failed = ?"); values.append(1 if research_failed else 0)
    if escalated is not None:
        fields.append("escalated = ?"); values.append(1 if escalated else 0)
    if error is not None:
        fields.append("error = ?"); values.append(error)
    if completed_at:
        fields.append("completed_at = ?"); values.append(completed_at)
    values.append(task_id)

    with _DB_LOCK, _connect(db_path) as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)


def get_task(task_id: str, db_path: Path = _DEFAULT_DB_PATH) -> Optional[dict]:
    _init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def list_tasks(
    user_id: str = "local",
    status: Optional[TaskStatus] = None,
    limit: int = 50,
    db_path: Path = _DEFAULT_DB_PATH,
) -> list[dict]:
    """按 user_id（可选 status）拉任务列表，最新优先。"""
    _init_db(db_path)
    sql = "SELECT * FROM tasks WHERE user_id = ?"
    params: list = [user_id]
    if status is not None:
        sql += " AND status = ?"
        params.append(status.value)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def stats(user_id: str = "local", db_path: Path = _DEFAULT_DB_PATH) -> dict:
    """按状态聚合统计（UI dashboard 用）。"""
    _init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM tasks WHERE user_id = ? GROUP BY status",
            (user_id,),
        ).fetchall()
    out = {s.value: 0 for s in TaskStatus}
    for r in rows:
        out[r["status"]] = r["n"]
    out["total"] = sum(out.values())
    return out
