"""plan 020：确定性架构图 —— LLM 只产结构化 ArchSpec，mermaid DSL 由代码生成。

根治 BC-10 的 mermaid 分支：把"LLM 直接写 mermaid 语法"（非确定性、反复挂）改为
"LLM 产 nodes/edges 结构 → 代码独占语法生成极简 flowchart"。代码控制箭头/引号/转义/节点上限，
LLM 永不碰 DSL → 整类语法/复杂度故障一次性消灭。与数据可视化（ChartSpec→Plotly）同一模式。
"""

import re
from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

MAX_NODES = 8
MAX_LABEL = 14
ARCH_PLACEHOLDER = "[[ARCH_DIAGRAM]]"


# ─── 结构化模型（LLM 只填这个，不写 mermaid）──────────────────────────────────

class ArchNode(BaseModel):
    id: str = Field(description="节点短标识，只含字母数字下划线（如 A / doubao）")
    label: str = Field(description="节点显示文字（中文模块/产品名，≤14 字，勿用特殊符号）")


class ArchEdge(BaseModel):
    source: str = Field(description="起点节点 id")
    target: str = Field(description="终点节点 id")


class ArchSpec(BaseModel):
    has_diagram: bool = Field(description="报告是否确有可画的架构/流程（多模块+关系）")
    direction: Literal["LR", "TD"] = "LR"
    nodes: list[ArchNode] = Field(default_factory=list)
    edges: list[ArchEdge] = Field(default_factory=list)


# ─── 代码确定性渲染（独占全部 mermaid 语法）──────────────────────────────────

_FULLWIDTH = {
    "（": "(", "）": ")", "：": ":", "｜": "|", "，": ",", "。": ".",
    "【": "[", "】": "]", "、": ",", "；": ";",
}


def _clean_label(s: str) -> str:
    """节点文字：全角→半角，去掉会干扰 mermaid 的字符，截断。即便加引号也尽量干净。"""
    s = (s or "").replace("\\", "").replace('"', "")
    for k, v in _FULLWIDTH.items():
        s = s.replace(k, v)
    s = re.sub(r"[\[\]{}|<>]", " ", s)  # 方/花括号、竖线、尖括号一律清掉
    s = re.sub(r"\s+", " ", s).strip()
    return s[:MAX_LABEL] if len(s) > MAX_LABEL else s


def _clean_id(s: str) -> str:
    """节点 id：只留字母数字下划线，保证是合法 mermaid 节点标识。"""
    cid = re.sub(r"[^A-Za-z0-9_]", "", s or "")
    return cid or "N"


def render_mermaid(spec: Optional[ArchSpec]) -> str:
    """ArchSpec → 极简 flowchart 字符串。无图/有效节点<2 → 返回 ""。

    代码独占语法：箭头只会是 `-->`、节点一律 `id["label"]` 加引号、坏边丢弃、节点 cap 8。
    """
    if not spec or not spec.has_diagram:
        return ""

    nodes: dict[str, str] = {}  # 去重 id → label
    for n in spec.nodes[:MAX_NODES]:
        cid = _clean_id(n.id)
        if cid not in nodes:
            nodes[cid] = _clean_label(n.label) or cid
    if len(nodes) < 2:
        return ""

    direction = spec.direction if spec.direction in ("LR", "TD") else "LR"
    lines = [f"flowchart {direction}"]
    for cid, label in nodes.items():
        lines.append(f'    {cid}["{label}"]')

    seen_edges: set[tuple[str, str]] = set()
    for e in spec.edges:
        s, t = _clean_id(e.source), _clean_id(e.target)
        if s in nodes and t in nodes and s != t and (s, t) not in seen_edges:
            seen_edges.add((s, t))
            lines.append(f"    {s} --> {t}")
    return "\n".join(lines)


# ─── 抽取（structured output，LLM 只决定画什么）────────────────────────────────

ARCH_SYSTEM = """你是技术架构图抽取器。从研究报告（尤其"技术架构"段）中识别核心模块及其关系，\
输出一张极简流程图的结构化描述。

规则：
1. has_diagram：报告确有可画的架构/流程（多个模块 + 明确流向/依赖关系）才 true；纯文字结论、无结构则 false。
2. nodes：≤8 个最关键的模块/产品/层。id 只用字母数字下划线（如 A、doubao）；label 是中文显示名，≤14 字，不要放 / : % ( ) 等特殊符号。
3. edges：模块间的流向或依赖，source/target 必须是上面 nodes 里的 id。
4. 宁简勿繁，抓主干即可，不要几十个节点。
**只输出结构化字段，绝不要写任何 mermaid 语法。**"""

ARCH_HUMAN = "研究报告：\n\n{report}\n\n请抽取架构图结构。"


async def build_arch_mermaid(report_text: str, structured_model) -> str:
    """抽 ArchSpec → 渲染 mermaid。structured_model 是已配置好的 chat model（外部传入便于复用 chart_model）。

    失败 / 无图 → 返回 ""，调用方据此删除占位符（不留空块）。
    """
    try:
        spec: ArchSpec = await structured_model.with_structured_output(
            ArchSpec, method="function_calling"
        ).ainvoke([
            SystemMessage(content=ARCH_SYSTEM),
            HumanMessage(content=ARCH_HUMAN.format(report=report_text[:8000])),
        ])
    except Exception:  # noqa: BLE001 — 抽取失败不应中断报告生成
        return ""
    return render_mermaid(spec)


# ─── 注入（保持内联，替换占位符）──────────────────────────────────────────────

def inject_arch_diagram(report: str, mermaid: str) -> str:
    """把代码生成的 mermaid 内联回报告：替换 `[[ARCH_DIAGRAM]]` 占位符。

    - 有占位符：替换（空 mermaid → 占位符删除，不留空块）。
    - 无占位符但有图：插在「技术架构」段标题之后；找不到该段则附在报告末尾。
    - 无占位符且无图：原样返回。
    """
    block = f"```mermaid\n{mermaid}\n```" if mermaid.strip() else ""

    if ARCH_PLACEHOLDER in report:
        # 占位符可能独占一行，替换后清理可能残留的空行
        out = report.replace(ARCH_PLACEHOLDER, block)
        return re.sub(r"\n{3,}", "\n\n", out)

    if not block:
        return report

    # 占位符缺失：尽量插在「技术架构」相关标题之后
    m = re.search(r"(?m)^#{1,6}\s*.*技术架构.*$", report)
    if m:
        idx = report.find("\n", m.end())
        if idx == -1:
            return report + "\n\n" + block + "\n"
        return report[: idx + 1] + "\n" + block + "\n" + report[idx + 1 :]
    return report.rstrip() + "\n\n" + block + "\n"
