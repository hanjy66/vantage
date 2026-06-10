"""plan 015-C：Obsidian 导出——写 vault 结构 + 双链化 + 实体去重合并（不打 LLM）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from open_deep_research.obsidian_export import (
    Entity,
    KnowledgeGraph,
    Relation,
    _linkify,
    write_vault,
)


def _sample_graph():
    return KnowledgeGraph(
        entities=[
            Entity(name="字节跳动", type="公司", aliases=["ByteDance"]),
            Entity(name="豆包", type="产品", aliases=["Doubao"]),
            Entity(name="Kimi", type="产品", aliases=[]),
        ],
        relations=[
            Relation(subject="豆包", predicate="属于", object="字节跳动"),
            Relation(subject="豆包", predicate="竞争", object="Kimi"),
        ],
    )


def test_write_vault_creates_structure(tmp_path):
    stats = write_vault(
        _sample_graph(),
        research_brief="字节豆包 vs Kimi 竞争",
        final_report="豆包属于字节跳动，与 Kimi 竞争。",
        mode="interview",
        vault_dir=tmp_path / "vault",
    )
    vault = tmp_path / "vault"
    assert (vault / "README.md").exists()
    assert (vault / "实体" / "字节跳动.md").exists()
    assert (vault / "实体" / "豆包.md").exists()
    assert stats["entities_created"] == 3
    assert len(list((vault / "研究记录").glob("*.md"))) == 1

    # 实体笔记含 frontmatter + 关系双链
    doubao = (vault / "实体" / "豆包.md").read_text(encoding="utf-8")
    assert "type: 产品" in doubao
    assert "[[字节跳动]]" in doubao
    assert "[[Kimi]]" in doubao


def test_research_note_linkifies_entities(tmp_path):
    write_vault(
        _sample_graph(),
        research_brief="字节豆包",
        final_report="豆包属于字节跳动，与 Kimi 竞争。",
        mode="general",
        vault_dir=tmp_path / "vault",
    )
    note = next((tmp_path / "vault" / "研究记录").glob("*.md")).read_text(encoding="utf-8")
    assert "[[豆包]]" in note
    assert "[[字节跳动]]" in note


def test_linkify_no_nested_brackets():
    """长名优先 + 占位法：不产生 [[豆包大[[模型]]]] 这类嵌套。"""
    out = _linkify("豆包大模型很强，豆包也行", ["豆包", "豆包大模型"])
    assert "[[豆包大模型]]" in out
    assert "[[[[" not in out
    assert "]]]]" not in out


def test_entity_merge_no_duplicate_file(tmp_path):
    """第二次导出同名实体（或其别名）→ 合并进现有笔记，不新建重复文件。"""
    vault = tmp_path / "vault"
    write_vault(_sample_graph(), "r1", "豆包属于字节跳动。", "general", vault)

    # 第二次：用别名 ByteDance 指代字节跳动 + 新关系
    g2 = KnowledgeGraph(
        entities=[Entity(name="ByteDance", type="公司", aliases=[])],
        relations=[Relation(subject="ByteDance", predicate="发布", object="豆包")],
    )
    stats = write_vault(g2, "r2", "ByteDance 发布豆包。", "general", vault)

    # 不应新建 ByteDance.md（应合并进 字节跳动.md）
    assert not (vault / "实体" / "ByteDance.md").exists()
    assert stats["entities_merged"] == 1
    bd = (vault / "实体" / "字节跳动.md").read_text(encoding="utf-8")
    assert "[[豆包]]" in bd  # 新关系已并入
