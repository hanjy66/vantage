"""Obsidian 知识库导出（plan 015-C）。

研究完成后：① 一次 LLM 调用抽取「实体 + 关系」；② 写入一个带 `[[双链]]` 的 markdown vault。
用户两步导入 Obsidian 即得知识图谱视图（节点=实体，边=关系），随研究次数生长 = 演化。

设计要点：
- **不做召回/查询**，所以无需图数据库、无需语义实体消解——实体消解降级为「图美观」问题，
  用 aliases + 文件名/别名字符串去重兜底，接受少量重复节点。
- vault 跨会话累积（同一目录持续写入），README 内置两步导入教程。
- 可视化完全交给 Obsidian，本模块零自建图渲染。
"""

import os
import re
from datetime import date
from pathlib import Path

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from open_deep_research.configuration import Configuration
from open_deep_research.utils import (
    get_api_key_for_model,
    get_base_url_for_model,
    get_today_str,
)


class Entity(BaseModel):
    name: str = Field(description="实体规范名（公司/产品/技术/人物/概念）")
    type: str = Field(description="实体类型：公司 / 产品 / 技术 / 人物 / 概念 之一")
    aliases: list[str] = Field(default_factory=list, description="别名/英文名/简称")


class Relation(BaseModel):
    subject: str = Field(description="关系主体实体名")
    predicate: str = Field(description="关系（如 属于/竞争/收购/使用/发布）")
    object: str = Field(description="关系客体实体名")


class KnowledgeGraph(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)


_EXTRACT_PROMPT = """你是知识图谱抽取器。今天是 {date}。
从下面的研究简报与报告中，抽取**实体**与**实体间关系**，用于构建知识图谱。

要求：
- 实体只取有信息价值的专有名词（公司、产品、技术、人物、概念），不要抽取通用词。
- 每个实体给出规范名 name、类型 type、以及可能的别名 aliases（中英文名/简称，如 字节跳动 的别名 ByteDance）。
- 关系是三元组 (subject, predicate, object)，subject/object 必须是上面 entities 里的 name。
- predicate 用简短中文动词短语（属于/竞争/收购/使用/发布/合作 等）。
- 控制规模：实体不超过 25 个，关系不超过 40 条，聚焦最核心的。

<研究简报>
{research_brief}
</研究简报>

<研究报告>
{final_report}
</研究报告>
"""


def _build_extract_model(configurable: Configuration, config: RunnableConfig):
    """复用写模型（final_report_model，默认 deepseek-chat）做结构化抽取。"""
    model_config = {
        "model": configurable.final_report_model,
        "max_tokens": configurable.final_report_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.final_report_model, config),
    }
    base_url = get_base_url_for_model(configurable.final_report_model)
    if base_url:
        model_config["base_url"] = base_url
    return (
        init_chat_model(configurable_fields=("model", "max_tokens", "api_key", "base_url"))
        .with_structured_output(KnowledgeGraph, method="function_calling")
        .with_retry(stop_after_attempt=2)
        .with_config(model_config)
    )


async def extract_graph(
    research_brief: str,
    final_report: str,
    configurable: Configuration,
    config: RunnableConfig,
) -> KnowledgeGraph:
    """一次 LLM 调用抽取实体+关系；失败返回空图（调用方据此跳过写 vault）。"""
    model = _build_extract_model(configurable, config)
    prompt = _EXTRACT_PROMPT.format(
        date=get_today_str(),
        research_brief=research_brief,
        final_report=(final_report or "")[:8000],
    )
    return await model.ainvoke([HumanMessage(content=prompt)])


# ---------- vault 写入 ----------

_INVALID_FN = re.compile(r'[\\/:*?"<>|]')


def _safe_filename(name: str) -> str:
    return _INVALID_FN.sub("_", name).strip() or "untitled"


def _linkify(text: str, names: list[str]) -> str:
    """把正文里出现的实体名替换成 [[name]] 双链；长名优先 + 占位法避免嵌套。"""
    uniq = sorted({n for n in names if n}, key=len, reverse=True)
    placeholders: dict[str, str] = {}
    for i, name in enumerate(uniq):
        token = f"\x00{i}\x00"
        if name in text:
            text = text.replace(name, token)
            placeholders[token] = f"[[{name}]]"
    for token, link in placeholders.items():
        text = text.replace(token, link)
    return text


def _parse_aliases(md: str) -> list[str]:
    """从已有实体笔记的 frontmatter 读 aliases（穷人版解析）。"""
    m = re.search(r"aliases:\s*\[([^\]]*)\]", md)
    if not m:
        return []
    return [a.strip().strip("'\"") for a in m.group(1).split(",") if a.strip()]


def _build_alias_index(entity_dir: Path) -> dict[str, str]:
    """alias/文件名（小写）→ 规范文件名（不含扩展名），用于跨文件去重合并。"""
    index: dict[str, str] = {}
    if not entity_dir.exists():
        return index
    for p in entity_dir.glob("*.md"):
        canonical = p.stem
        index[canonical.lower()] = canonical
        for alias in _parse_aliases(p.read_text(encoding="utf-8")):
            index.setdefault(alias.lower(), canonical)
    return index


def _entity_note(entity: Entity, relations: list[Relation], tag: str) -> str:
    alias_str = ", ".join(entity.aliases)
    lines = [
        "---",
        f"aliases: [{alias_str}]",
        f"type: {entity.type}",
        f"created: {date.today().isoformat()}",
        f"tags: [{tag}]",
        "---",
        "",
        f"# {entity.name}",
        "",
    ]
    rel_lines = [
        f"- {r.predicate}：[[{r.object}]]"
        for r in relations
        if r.subject == entity.name and r.object
    ]
    if rel_lines:
        lines.append("## 关系")
        lines.extend(rel_lines)
        lines.append("")
    return "\n".join(lines)


_README = """# ADRP 知识库（Obsidian 兼容）

本目录由 ADRP 自动生成：每次研究抽取的实体与关系都沉淀为带 `[[双链]]` 的 Markdown，
随研究次数累积成长 = 你自己的知识图谱演化。

## 两步导入 Obsidian 看图谱

1. 打开 Obsidian → 「Open folder as vault」→ 选择**本文件夹**。
2. 点左侧「图谱视图」(Graph view) 图标 → 即可看到实体网络。

- `实体/`：每个实体一个笔记（节点），笔记里 `[[...]]` 是关系（边）。
- `研究记录/`：每次研究的完整报告，正文中的实体已自动转为 `[[双链]]`。
- 研究越多，图谱越密；按日期标签（tag）过滤可看不同时间点的「演化快照」。
"""


def write_vault(
    graph: KnowledgeGraph,
    research_brief: str,
    final_report: str,
    mode: str,
    vault_dir: Path,
) -> dict:
    """把知识图谱写入 vault（实体笔记 + 研究笔记 + README），合并已存在实体。返回统计。"""
    vault_dir = Path(vault_dir)
    entity_dir = vault_dir / "实体"
    research_dir = vault_dir / "研究记录"
    entity_dir.mkdir(parents=True, exist_ok=True)
    research_dir.mkdir(parents=True, exist_ok=True)

    readme = vault_dir / "README.md"
    if not readme.exists():
        readme.write_text(_README, encoding="utf-8")

    today = date.today().isoformat()
    tag = f"research/{today}"

    # 去重：把抽取实体名/别名映射到已存在的规范文件名
    alias_index = _build_alias_index(entity_dir)
    created, merged = 0, 0
    for entity in graph.entities:
        if not entity.name:
            continue
        canonical = alias_index.get(entity.name.lower())
        for a in entity.aliases:
            canonical = canonical or alias_index.get(a.lower())
        if canonical:
            # 合并：把本次关系补进已存在笔记（去重），并入新别名
            path = entity_dir / f"{canonical}.md"
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            new_rels = [
                f"- {r.predicate}：[[{r.object}]]"
                for r in graph.relations
                if r.subject == entity.name and r.object
                and f"[[{r.object}]]" not in existing
            ]
            if new_rels:
                if "## 关系" not in existing:
                    existing = existing.rstrip() + "\n\n## 关系\n"
                existing = existing.rstrip() + "\n" + "\n".join(new_rels) + "\n"
                path.write_text(existing, encoding="utf-8")
            merged += 1
        else:
            fn = _safe_filename(entity.name)
            (entity_dir / f"{fn}.md").write_text(
                _entity_note(entity, graph.relations, tag), encoding="utf-8"
            )
            alias_index[entity.name.lower()] = fn
            for a in entity.aliases:
                alias_index.setdefault(a.lower(), fn)
            created += 1

    # 研究笔记：报告正文 + 实体 mention 双链化
    names = [e.name for e in graph.entities]
    title = _safe_filename(research_brief[:24]) or "研究"
    body = _linkify(final_report or "", names)
    note = (
        f"---\ncreated: {today}\nmode: {mode}\ntags: [{tag}]\n---\n\n"
        f"# {research_brief[:60]}\n\n{body}\n"
    )
    (research_dir / f"{today}-{title}.md").write_text(note, encoding="utf-8")

    return {"entities_created": created, "entities_merged": merged, "vault": str(vault_dir)}


def get_vault_dir() -> Path:
    return Path(os.getenv("OBSIDIAN_VAULT_DIR", "data/obsidian_vault"))


async def export_to_vault(state, configurable, config, mode: str) -> dict | None:
    """编排：抽取实体+关系 → 写 vault。任何失败返回 None（调用方不阻断主流程）。"""
    try:
        research_brief = state.get("research_brief", "") or ""
        final_report = str(state.get("final_report", "") or "")
        if not research_brief or not final_report:
            return None
        graph = await extract_graph(research_brief, final_report, configurable, config)
        if not graph.entities:
            return None
        return write_vault(graph, research_brief, final_report, mode, get_vault_dir())
    except Exception:  # noqa: BLE001 — 导出失败不应中断研究
        return None
