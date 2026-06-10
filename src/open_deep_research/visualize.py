"""plan 009 Phase B: 数据可视化 — 五阶段保真流水线。

设计原则：LLM 提议，代码裁决。
  - Stage 1  Gate: 报告有无 ≥2 个可对比具体数值？没有则跳过。
  - Stage 2  带溯源抽取: 每个数据点携带 source_quote（原文片段）。
  - Stage 3  程序化校验: source_quote 子串匹配 + value 正则反查，幻觉结构上进不来。
  - Stage 4  只渲染通过校验的 spec。
  - Stage 5  诚实渲染: 轴标带单位，脚注标明来源，缺失值不补全。
"""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ─── 数据结构 ─────────────────────────────────────────────────────────────────


class DataPoint(BaseModel):
    """单个数据点，必须携带原文溯源。"""
    label: str
    value: float
    unit: str = ""
    source_quote: str = Field(
        description="报告中包含此数值的原文片段（用于校验，防幻觉）"
    )


class ChartSpec(BaseModel):
    """图表规格。"""
    chart_type: Literal["bar", "line", "pie"]
    title: str
    x_label: str = ""
    y_label: str = ""
    data_points: list[DataPoint]


class ChartExtractionResult(BaseModel):
    """LLM 抽取结果，含门控判断。"""
    has_chartable_data: bool = Field(
        description="报告中是否存在 ≥2 个可对比的具体数值"
    )
    specs: list[ChartSpec] = Field(
        default_factory=list,
        description="0-3 个图表规格，has_chartable_data=False 时为空列表"
    )


# ─── Stage 3: 程序化校验 ──────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """归一化用于子串匹配：去全部空白 + 常见标点/markdown，降低抽取改写导致的误丢。

    只去格式噪声，不动数字与文字字符，故不放松防幻觉（数字仍需真实出现在报告里）。
    """
    t = re.sub(r"\s+", "", text).lower()
    t = re.sub(r"[，,、。．.;；:：!！?？（）()\[\]【】{}\"'`*_~|—\-]", "", t)
    return t


def _value_in_quote(value: float, quote: str) -> bool:
    """检查 quote 中是否包含与 value 数值一致的数字（容差 5%）。

    兼容中文单位换算：模型常把「3.45 亿」归一化成 34500（万）以便同轴对比，此时归一化后的
    value 不会逐字出现在原文 quote 里。故对 quote 里的每个数字额外尝试 亿/万/个 之间的换算倍数
    （1e4 / 1e8 及其倒数）——数值仍源自原文真实数字，不放松防幻觉，只允许单位缩放。
    """
    numbers = re.findall(r"\d+(?:[.,]\d+)?", quote)
    mults = (1, 1e4, 1e8, 1e-4, 1e-8)  # 个↔万↔亿 互转
    for n in numbers:
        try:
            n_float = float(n.replace(",", ""))
        except ValueError:
            continue
        denom = max(abs(value), 1.0)
        for m in mults:
            if abs(n_float * m - value) / denom < 0.05:
                return True
    return False


def validate_spec(spec: ChartSpec, report: str) -> Optional[ChartSpec]:
    """校验 ChartSpec，返回过滤后的有效 spec，或 None（图整体无效）。

    校验规则：
    1. source_quote 必须是报告原文的子串
    2. value 必须能从 source_quote 中正则提出且数值一致
    3. 有效数据点 ≥ 2
    4. 饼图：数据之和在 [80, 120] 范围内（百分比数据）
    """
    report_norm = _normalize(report)
    valid: list[DataPoint] = []

    for dp in spec.data_points:
        sq_norm = _normalize(dp.source_quote)
        # 规则 1: source_quote 必须在报告中
        if sq_norm not in report_norm:
            continue
        # 规则 2: value 必须能从 source_quote 提出
        if not _value_in_quote(dp.value, dp.source_quote):
            continue
        valid.append(dp)

    # 规则 3: 至少 2 个有效点
    if len(valid) < 2:
        return None

    # 规则 4: 饼图和应 ≈ 100
    if spec.chart_type == "pie":
        total = sum(dp.value for dp in valid)
        if not (80 <= total <= 120):
            return None

    return ChartSpec(
        chart_type=spec.chart_type,
        title=spec.title,
        x_label=spec.x_label,
        y_label=spec.y_label,
        data_points=valid,
    )


# ─── Stage 4-5: Plotly 渲染 ───────────────────────────────────────────────────

def render_chart(spec: ChartSpec, source_note: str = "数据来源：本报告") -> str:
    """将 ChartSpec 渲染为自包含 HTML 字符串（Plotly）。

    返回可直接嵌入 Gradio gr.HTML / Streamlit st.components.html 的 HTML。
    """
    import plotly.express as px  # lazy import，仅 Phase B 启用时才需要

    labels = [dp.label for dp in spec.data_points]
    values = [dp.value for dp in spec.data_points]
    units = spec.data_points[0].unit if spec.data_points else ""

    y_label = f"{spec.y_label} ({units})" if units and spec.y_label else spec.y_label or units

    if spec.chart_type == "bar":
        fig = px.bar(
            x=labels, y=values, title=spec.title,
            labels={"x": spec.x_label or "类别", "y": y_label or "数值"},
        )
    elif spec.chart_type == "line":
        fig = px.line(
            x=labels, y=values, title=spec.title,
            labels={"x": spec.x_label or "时间", "y": y_label or "数值"},
            markers=True,
        )
    elif spec.chart_type == "pie":
        fig = px.pie(names=labels, values=values, title=spec.title)
    else:
        return ""

    # 诚实渲染：脚注标明数据来源
    fig.update_layout(
        annotations=[dict(
            text=source_note,
            showarrow=False, xref="paper", yref="paper",
            x=0.0, y=-0.12, xanchor="left",
            font=dict(size=10, color="gray"),
        )],
        margin=dict(b=60),
    )

    return fig.to_html(include_plotlyjs=True, full_html=False)


def render_critique_fallback_chart(criteria_breakdown: dict) -> str:
    """plan 012 兜底：报告无可图表化内容数据时，用 critic 五维评分渲一张 bar 图。

    这是**真实元数据**（机器审计的实际打分），非伪造内容数据；标题/脚注明确标注。
    """
    items = [(k, v) for k, v in (criteria_breakdown or {}).items() if isinstance(v, (int, float))]
    if len(items) < 2:
        return ""
    spec = ChartSpec(
        chart_type="bar",
        title="报告质量 · 机审五维评分",
        x_label="维度",
        y_label="评分",
        data_points=[DataPoint(label=k, value=float(v), unit="/10", source_quote="") for k, v in items],
    )
    return render_chart(spec, source_note="数据来源：跨模型 critic 机审评分（非报告内容数据）")


# ─── LLM 抽取提示词 ───────────────────────────────────────────────────────────

GATE_AND_EXTRACT_SYSTEM = """你是一个数据可视化专家，任务是从研究报告中识别并提取可图表化的数据。

【门控规则 — 有以下情况才返回图表，否则 has_chartable_data=false】
- 报告中存在 ≥2 个可直接对比的**具体数值**（必须有明确数字，不能是"A 比 B 大"这类描述）
- 数值之间有可比性（同一维度，如 MAU、份额、时间序列）

【抽取规则 — 严格执行】
1. **只抽报告中明确写出的数据，禁止推断、估算、补全缺失值**
2. 每个 data_point 必须填写 source_quote（从报告中**逐字复制**含该数值的原始片段，15-80字，
   含数字和单位，禁止改写/缩写/翻译/省略——改写会导致该点被程序校验丢弃）
3. 某项数据没有明确数字则**留空/不填该点**，不要用"约"、"大约"或估算值
4. 最多返回 3 个图表，优先选信息量最大的

【图表类型选择】
- bar：多项对比（竞品对比、功能对比）
- line：时间序列趋势
- pie：占比且各项之和 ≈ 100%（市场份额等）

【模式感知 — interview 模式重点】
interview 报告必含「竞品对比矩阵」表 + 「关键数据速查」清单，**优先且务必从这两处挖可对比数据**。
要主动找出**同一口径**的成对/成组数值（这是最容易出图的）：
- 同指标对比：如 A 留存率 44.5% vs B 留存率 32.1%；A 的 DAU vs B 的 DAU；各家市场份额%；各家融资额（亿）
- 同单位才放一张图：留存率(%) 一张、用户量（注意 亿/万 要先换算成同一单位再比）一张、融资额（亿）一张
- 中文数字与单位要会读：「1.45亿」=14500万、「967万」=967万、「44.5%」=44.5、「376亿」=376
- 矩阵单元格里常把数字和引用写在一起（如「DAU破1亿（2025年12月）[32]」），source_quote 要把含数字的那段**逐字**抄下来
**只要矩阵或关键数据里能凑出 ≥2 个同口径数值，就必须 has_chartable_data=true 并出图，不要轻易判 false。**
确实没有任何两个同口径数值时，才返回 false。"""

GATE_AND_EXTRACT_HUMAN = "请分析以下报告，按规则提取可视化数据：\n\n{report}"
