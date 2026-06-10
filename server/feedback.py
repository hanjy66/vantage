"""用户打分回流（plan 010 Step 2b）。

用户对一份报告打分 → 写 feedback.jsonl（原始反馈日志）
                    → 自动追加成 eval query（feedback_queries.jsonl），构成人评×机评数据飞轮。
无 LLM。
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path("data/eval")
FEEDBACK_LOG = EVAL_DIR / "feedback.jsonl"
FEEDBACK_QUERIES = EVAL_DIR / "feedback_queries.jsonl"


def write_feedback(
    research_brief: str,
    user_score: int,
    report_preview: str = "",
    comment: str = "",
    mode: str = "general",
    run_id: str = "",
) -> dict:
    """落盘一条用户反馈，并将其 brief 自动纳入评测集。

    返回 {feedback_id, added_to_eval}。
    """
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    fid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    record = {
        "id": fid,
        "run_id": run_id or "",   # 前端每次 start() 生成的 UUID，与当轮研究一一对应
        "timestamp": now,
        "research_brief": research_brief,
        "user_score": user_score,
        "report_preview": report_preview[:1000],
        "comment": comment,
        "mode": mode,
    }
    with FEEDBACK_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 自动进评测集：用户打过分的 brief 成为可回放的 eval query
    added_to_eval = False
    if research_brief.strip():
        eval_query = {
            "id": f"fb-{fid[:8]}",
            "research_brief": research_brief,
            "mode": mode,
            "category": "user_feedback",
            "tags": ["user_flagged"],
            "min_score": 7,
            "user_score": user_score,  # 人评，与机评对照
            "user_comment": comment,   # 真实评论，供下一轮分析改进
        }
        with FEEDBACK_QUERIES.open("a", encoding="utf-8") as f:
            f.write(json.dumps(eval_query, ensure_ascii=False) + "\n")
        added_to_eval = True

    return {"feedback_id": fid, "added_to_eval": added_to_eval}
