"""plan 020 — 确定性架构图：代码渲染 mermaid + 占位符注入（零 LLM）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from open_deep_research.arch_diagram import (
    ARCH_PLACEHOLDER,
    ArchEdge,
    ArchNode,
    ArchSpec,
    inject_arch_diagram,
    render_mermaid,
)


def _spec(nodes, edges, has=True, direction="LR"):
    return ArchSpec(
        has_diagram=has,
        direction=direction,
        nodes=[ArchNode(id=i, label=l) for i, l in nodes],
        edges=[ArchEdge(source=s, target=t) for s, t in edges],
    )


# ─── render_mermaid ───────────────────────────────────────────────────────────

def test_render_basic_valid_flowchart():
    out = render_mermaid(_spec([("A", "豆包"), ("B", "Kimi")], [("A", "B")]))
    assert out.startswith("flowchart LR")
    assert 'A["豆包"]' in out and 'B["Kimi"]' in out
    assert "A --> B" in out


def test_render_escapes_special_chars_in_label():
    """label 含 / : % ( ) 全角等也输出合法（代码统一清洗，不靠引号硬扛）。"""
    out = render_mermaid(_spec(
        [("A", "豆包/字节(自研):MoE 200B%"), ("B", "Kimi（月之暗面）")],
        [("A", "B")],
    ))
    # 不应残留方/花括号、竖线；全角括号→半角；整体仍是合法 [".."]
    assert "[[" not in out and "]]" not in out
    assert "（" not in out and "）" not in out
    assert 'A["' in out and 'B["' in out
    assert "A --> B" in out


def test_render_caps_nodes_at_8():
    nodes = [(chr(65 + i), f"模块{i}") for i in range(12)]
    edges = [("A", "B")]
    out = render_mermaid(_spec(nodes, edges))
    decl = [l for l in out.splitlines() if l.strip().endswith('"]')]
    assert len(decl) == 8


def test_render_drops_edges_to_unknown_nodes():
    out = render_mermaid(_spec(
        [("A", "豆包"), ("B", "Kimi")],
        [("A", "B"), ("A", "Z"), ("X", "B"), ("A", "A")],  # Z/X 不存在、A->A 自环
    ))
    assert "A --> B" in out
    assert "--> Z" not in out and "X -->" not in out
    assert "A --> A" not in out


def test_render_empty_when_no_diagram_or_too_few():
    assert render_mermaid(_spec([("A", "x"), ("B", "y")], [], has=False)) == ""
    assert render_mermaid(_spec([("A", "只有一个")], [])) == ""
    assert render_mermaid(None) == ""


def test_render_dedupes_node_ids():
    out = render_mermaid(_spec([("A", "豆包"), ("A", "重复"), ("B", "Kimi")], [("A", "B")]))
    decl = [l for l in out.splitlines() if l.strip().endswith('"]')]
    assert len(decl) == 2  # A 去重


# ─── inject_arch_diagram ──────────────────────────────────────────────────────

def test_inject_replaces_placeholder():
    report = f"## 技术架构\n讲解…\n\n{ARCH_PLACEHOLDER}\n\n后续段落"
    out = inject_arch_diagram(report, "flowchart LR\n    A --> B")
    assert ARCH_PLACEHOLDER not in out
    assert "```mermaid" in out and "A --> B" in out
    assert "后续段落" in out


def test_inject_empty_mermaid_removes_placeholder_no_blank_block():
    report = f"## 技术架构\n讲解…\n\n{ARCH_PLACEHOLDER}\n\n后续"
    out = inject_arch_diagram(report, "")
    assert ARCH_PLACEHOLDER not in out
    assert "```mermaid" not in out
    assert "\n\n\n" not in out  # 不留多余空行


def test_inject_missing_placeholder_inserts_after_arch_heading():
    report = "# 报告\n\n## 三、技术架构要点\n架构讲解段。\n\n## 四、其它"
    out = inject_arch_diagram(report, "flowchart LR\n    A --> B")
    assert "```mermaid" in out
    # 图应插在技术架构标题之后、其它段之前
    assert out.index("```mermaid") > out.index("技术架构")
    assert out.index("```mermaid") < out.index("## 四、其它")


def test_inject_missing_placeholder_no_heading_appends():
    report = "# 报告\n\n纯文字结论，没有架构段。"
    out = inject_arch_diagram(report, "flowchart LR\n    A --> B")
    assert out.rstrip().endswith("```")
    assert "```mermaid" in out
