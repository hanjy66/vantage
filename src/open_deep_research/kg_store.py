"""Local JSON store for lightweight KG active recall.

召回策略（plan 015-B）：优先**语义召回**（智谱 embedding-3 + 余弦相似度），
失败（无 key / embedding 异常 / 历史记录无 embedding）则回退到原 **2-gram 字符重叠**。
存储仍是 `data/kg/*.json` 单文件，每条 record 内嵌 `embedding` 字段——单用户本地规模
（<1000 条）暴力余弦 <50ms，无需引入向量数据库依赖。
"""

import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from open_deep_research.embeddings import embed

KG_DIR = Path(os.getenv("KG_DIR", "data/kg"))

# 语义召回阈值：余弦 >= 此值才认为相关（embedding-3 经验值，可经 env 覆盖后实测调参）
MIN_SEMANTIC_SCORE = float(os.getenv("KG_MIN_SEMANTIC_SCORE", "0.45"))


def save_research(
    research_brief: str,
    notes: list[str],
    final_report: str,
    mode: str = "general",
    critique: dict | None = None,
    chart_htmls: list[str] | None = None,
    revision_count: int = 0,
    research_topic: str = "",
) -> str:
    """Save one completed research run as a local JSON record（内嵌 embedding，失败则省略）。

    plan 022：额外存 research_topic（用户原始输入）+ critique（质量评分卡）+ chart_htmls（图表），
    让历史研究库可原样回看：原始主题 + 系统简报 + 报告 + 评分卡 + 数据可视化。
    老 record 无这些字段，前端按缺省渲染。
    """
    KG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "research_topic": research_topic,
        "research_brief": research_brief,
        "notes": notes,
        "final_report": final_report,
        "revision_count": revision_count,
    }
    if critique is not None:
        record["critique"] = critique
    if chart_htmls:
        record["chart_htmls"] = chart_htmls
    # 语义召回用 embedding：brief + 报告摘要拼接后向量化；失败不阻断（不写该字段）
    embeddable = f"{research_brief}\n\n{(final_report or '')[:2000]}"
    vector = embed(embeddable)
    if vector is not None:
        record["embedding"] = vector

    path = KG_DIR / f"{record['id']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record["id"]


def _ngrams(text: str, n: int = 2) -> set[str]:
    """字符级 n-gram，支持中英文混合文本（中文无空格场景下空格分词失效）。"""
    cleaned = "".join(text.lower().split())
    if len(cleaned) < n:
        return set()
    return {cleaned[i:i + n] for i in range(len(cleaned) - n + 1)}


# 2-gram 回退召回阈值：score >= MIN_SCORE 才认为相关，避免高频字符的偶然重叠
MIN_RECALL_SCORE = 5


def _cosine(a: list[float], b: list[float]) -> float:
    """纯 Python 余弦相似度（无 numpy 依赖；2048 维 × 数百条够快）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _load_records() -> list[dict]:
    """按修改时间倒序加载全部 KG 记录。"""
    records: list[dict] = []
    for path in sorted(KG_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return records


def _recall_semantic(query: str, records: list[dict], top_k: int) -> list[tuple[float, dict]] | None:
    """语义召回；query embedding 失败或无任何带 embedding 的历史记录 → 返回 None（交回退）。"""
    q_emb = embed(query)
    if q_emb is None:
        return None
    has_any_embedding = False
    scored: list[tuple[float, dict]] = []
    for record in records:
        emb = record.get("embedding")
        if not emb:
            continue
        has_any_embedding = True
        score = _cosine(q_emb, emb)
        if score >= MIN_SEMANTIC_SCORE:
            scored.append((score, record))
    if not has_any_embedding:
        return None  # 历史全是旧记录（无 embedding）→ 回退 2-gram
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def _recall_2gram(query: str, records: list[dict], top_k: int) -> list[tuple[int, dict]]:
    """原 2-gram 字符重叠召回（回退路径）。"""
    query_grams = _ngrams(query)
    if not query_grams:
        return []
    scored: list[tuple[int, dict]] = []
    for record in records:
        brief_grams = _ngrams(record.get("research_brief", ""))
        score = len(query_grams & brief_grams)
        if score >= MIN_RECALL_SCORE:
            scored.append((score, record))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def _format(scored: list[tuple], max_chars_per_record: int) -> str:
    parts = []
    for _, record in scored:
        date_str = record.get("timestamp", "")[:10]
        brief_preview = record.get("research_brief", "")[:200]
        report_preview = record.get("final_report", "")[:max_chars_per_record]
        parts.append(
            f"[{date_str} / {record.get('mode', '')}] Past research brief: {brief_preview}\n"
            f"Final report excerpt: {report_preview}"
        )
    return "\n\n---\n\n".join(parts)


def recall_relevant(
    query: str,
    top_k: int = 3,
    max_chars_per_record: int = 1500,
) -> str:
    """召回相关历史研究：优先语义（embedding 余弦），回退 2-gram 字符重叠。"""
    if not KG_DIR.exists():
        return ""
    records = _load_records()
    if not records:
        return ""

    scored = _recall_semantic(query, records, top_k)
    if scored is None:
        scored = _recall_2gram(query, records, top_k)
    if not scored:
        return ""

    return _format(scored, max_chars_per_record)


def recall_relevant_records(query: str, top_k: int = 5) -> list[dict]:
    """结构化召回：返回带 id/score 的命中列表，供 GAP 查重 + 前端回看链接用（plan 018）。

    与 recall_relevant（字符串版，主图 kg_context 用）并存、互不影响。每项：
    {id, title, date, mode, score, matched_by}。score 在语义路径是余弦(0-1)、2gram 路径是命中 gram 数(int)；
    matched_by ∈ {"semantic","2gram"}，上层据此按阈值判重（语义高分→几乎确定重复）。
    """
    if not KG_DIR.exists():
        return []
    records = _load_records()
    if not records:
        return []

    scored = _recall_semantic(query, records, top_k)
    matched_by = "semantic"
    if scored is None:
        scored = _recall_2gram(query, records, top_k)
        matched_by = "2gram"

    out: list[dict] = []
    for score, record in scored:
        brief = record.get("research_brief", "") or ""
        out.append({
            "id": record.get("id", ""),
            "title": brief[:60],
            "date": (record.get("timestamp", "") or "")[:10],
            "mode": record.get("mode", ""),
            "score": float(score),
            "matched_by": matched_by,
        })
    return out


def list_records() -> list[dict]:
    """列出全部历史研究的摘要（不含 embedding/正文），按时间倒序——供历史研究库网格。"""
    out: list[dict] = []
    for rec in _load_records():
        brief = (rec.get("research_brief") or "").strip()
        first_line = brief.splitlines()[0] if brief else ""
        out.append({
            "id": rec.get("id", ""),
            "date": (rec.get("timestamp", "") or "")[:10],
            "mode": rec.get("mode", ""),
            "title": (first_line[:60] or "（无主题）"),
            "notes_count": len(rec.get("notes", []) or []),
            "has_charts": bool(rec.get("chart_htmls")),
        })
    return out


def get_record(record_id: str) -> dict | None:
    """按 id 读单条 KG 记录（回看/下载用）。

    防路径穿越：只接受不含分隔符/`..` 的纯文件名 id（端点 GET /kg/{id} 暴露，必须收紧）。
    """
    if not record_id or "/" in record_id or "\\" in record_id or ".." in record_id:
        return None
    path = KG_DIR / f"{record_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
