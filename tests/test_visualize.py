"""plan 009 Phase B unit tests — 数据可视化保真校验 + Plotly 渲染。"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from open_deep_research.visualize import (
    ChartSpec,
    DataPoint,
    render_chart,
    render_critique_fallback_chart,
    validate_spec,
)


def test_critique_fallback_chart_renders_with_scores():
    """plan 012：critic 五维评分 → 兜底 bar 图（保证非空）。"""
    html = render_critique_fallback_chart(
        {"事实密度": 9, "引用覆盖": 8, "内部一致性": 9, "逻辑结构": 8, "洞察深度": 7}
    )
    assert html and "<div" in html and "机审" in html


def test_critique_fallback_chart_empty_when_insufficient():
    """维度不足 2 个 → 不出兜底图（避免无意义单点）。"""
    assert render_critique_fallback_chart({"事实密度": 9}) == ""
    assert render_critique_fallback_chart({}) == ""


# ─── 测试数据工厂 ──────────────────────────────────────────────────────────────

def _bar_spec(points: list[tuple]) -> ChartSpec:
    """构造柱状图 spec，points = [(label, value, source_quote), ...]。"""
    return ChartSpec(
        chart_type="bar",
        title="竞品 MAU 对比",
        x_label="产品",
        y_label="MAU",
        data_points=[
            DataPoint(label=l, value=v, unit="百万", source_quote=sq)
            for l, v, sq in points
        ],
    )


REPORT = (
    "Perplexity AI 的月活跃用户（MAU）约为 1500 万。"
    "ChatGPT 的 MAU 超过 10000 万。"
    "Claude 的 MAU 约为 2000 万，增长迅速。"
    "字节豆包暂无公开 MAU 数据。"
)


# ─── validate_spec 测试 ───────────────────────────────────────────────────────

def test_valid_spec_passes():
    """正常 spec，source_quote 和 value 都在报告中，应通过校验。"""
    spec = _bar_spec([
        ("Perplexity", 1500, "Perplexity AI 的月活跃用户（MAU）约为 1500 万"),
        ("ChatGPT", 10000, "ChatGPT 的 MAU 超过 10000 万"),
        ("Claude", 2000, "Claude 的 MAU 约为 2000 万，增长迅速"),
    ])
    result = validate_spec(spec, REPORT)
    assert result is not None
    assert len(result.data_points) == 3


def test_hallucinated_source_quote_dropped():
    """source_quote 不在报告中的数据点被丢弃，其余有效点保留。"""
    spec = _bar_spec([
        ("Perplexity", 1500, "Perplexity AI 的月活跃用户（MAU）约为 1500 万"),
        ("Claude", 2000, "Claude 的 MAU 约为 2000 万，增长迅速"),
        ("幻觉产品", 9999, "幻觉产品拥有 9999 万用户规模"),  # 不在报告里
    ])
    result = validate_spec(spec, REPORT)
    assert result is not None
    assert len(result.data_points) == 2
    assert result.data_points[0].label == "Perplexity"


def test_unit_normalized_value_passes():
    """模型把「亿」归一化成「万」（3.45亿→34500）时，归一化后的 value 仍应通过校验。

    这是真实回归：旧逻辑要求 value 逐字出现在 quote，归一化后 34500 不在「3.45 亿」里 → 误丢 →
    有效点 <2 → 整图被丢 → 退化成 critic 兜底图。修复后单位换算（1e4/1e8）应让其通过。
    """
    report = "豆包 MAU 3.45 亿（2026 年 5 月）。Kimi MAU 约 1830 万（2025 年底）。"
    spec = _bar_spec([
        ("豆包", 34500, "豆包 MAU 3.45 亿（2026 年 5 月）"),  # 3.45亿 = 34500万
        ("Kimi", 1830, "Kimi MAU 约 1830 万（2025 年底）"),
    ])
    result = validate_spec(spec, report)
    assert result is not None
    assert len(result.data_points) == 2


def test_hallucinated_value_dropped():
    """value 与 source_quote 中的数字不一致（幻觉数字）被丢弃，其余有效点保留。"""
    spec = _bar_spec([
        ("Perplexity", 9999, "Perplexity AI 的月活跃用户（MAU）约为 1500 万"),  # 数字不符
        ("Claude", 2000, "Claude 的 MAU 约为 2000 万，增长迅速"),
        ("ChatGPT", 10000, "ChatGPT 的 MAU 超过 10000 万"),
    ])
    result = validate_spec(spec, REPORT)
    assert result is not None
    assert len(result.data_points) == 2
    assert result.data_points[0].label == "Claude"
    assert result.data_points[1].label == "ChatGPT"


def test_too_few_valid_points_returns_none():
    """有效数据点不足 2 个时，整个 spec 被丢弃。"""
    spec = _bar_spec([
        ("Perplexity", 1500, "Perplexity AI 的月活跃用户（MAU）约为 1500 万"),
        ("幻觉", 999, "幻觉产品是最大的"),  # 不在报告，被丢弃
    ])
    result = validate_spec(spec, REPORT)
    assert result is None


def test_pie_chart_non_100_returns_none():
    """饼图数据之和不在 [80, 120] 范围内时，spec 被丢弃。"""
    report = "A 产品市场份额为 30%，B 产品为 20%。"
    spec = ChartSpec(
        chart_type="pie",
        title="市场份额",
        data_points=[
            DataPoint(label="A", value=30, source_quote="A 产品市场份额为 30%"),
            DataPoint(label="B", value=20, source_quote="B 产品为 20%"),
        ],
    )
    result = validate_spec(spec, report)
    assert result is None  # 30+20=50，不在 [80,120]


def test_pie_chart_100_passes():
    """饼图数据之和 ≈ 100 时通过校验。"""
    report = "A 产品市场份额为 60%，B 产品为 40%。"
    spec = ChartSpec(
        chart_type="pie",
        title="市场份额",
        data_points=[
            DataPoint(label="A", value=60, source_quote="A 产品市场份额为 60%"),
            DataPoint(label="B", value=40, source_quote="B 产品为 40%"),
        ],
    )
    result = validate_spec(spec, report)
    assert result is not None
    assert len(result.data_points) == 2


# ─── render_chart 测试（需要 plotly） ────────────────────────────────────────

def test_render_bar_produces_html():
    """柱状图渲染产出包含 plotly 标记的 HTML 字符串。"""
    spec = _bar_spec([
        ("Perplexity", 1500, "Perplexity AI 的月活跃用户（MAU）约为 1500 万"),
        ("Claude", 2000, "Claude 的 MAU 约为 2000 万，增长迅速"),
    ])
    html = render_chart(spec)
    assert isinstance(html, str)
    assert len(html) > 100
    assert "plotly" in html.lower()
    assert "竞品 MAU 对比" in html


def test_render_line_produces_html():
    """折线图渲染产出 HTML。"""
    spec = ChartSpec(
        chart_type="line",
        title="增长趋势",
        x_label="季度",
        y_label="用户数",
        data_points=[
            DataPoint(label="Q1", value=100, source_quote="Q1 用户数为 100 万"),
            DataPoint(label="Q2", value=150, source_quote="Q2 用户数为 150 万"),
        ],
    )
    html = render_chart(spec)
    assert "plotly" in html.lower()
    assert "增长趋势" in html


def test_render_includes_source_note():
    """渲染图表包含数据来源脚注。"""
    spec = _bar_spec([
        ("Perplexity", 1500, "Perplexity AI 的月活跃用户（MAU）约为 1500 万"),
        ("Claude", 2000, "Claude 的 MAU 约为 2000 万，增长迅速"),
    ])
    html = render_chart(spec)
    assert "数据来源" in html


# ─── visualize 节点测试 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_visualize_disabled_passthrough(monkeypatch):
    """enable_visualization=False 时直接 passthrough，chart_htmls 为空列表。"""
    from open_deep_research import deep_researcher

    state = {"final_report": "一份报告", "research_failed": False}
    config = {"configurable": {"enable_visualization": False}}

    result = await deep_researcher.visualize(state, config)
    assert result.goto == "__end__"
    assert result.update.get("chart_htmls") == []


@pytest.mark.asyncio
async def test_visualize_research_failed_passthrough():
    """research_failed=True 时跳过可视化。"""
    from open_deep_research import deep_researcher

    state = {"final_report": "失败报告", "research_failed": True}
    config = {"configurable": {"enable_visualization": True}}

    result = await deep_researcher.visualize(state, config)
    assert result.update.get("chart_htmls") == []


@pytest.mark.asyncio
async def test_visualize_gate_no_data(monkeypatch):
    """Gate 判断无可视化数据时，返回空列表。"""
    from open_deep_research import deep_researcher
    from open_deep_research.visualize import ChartExtractionResult

    class FakeExtractModel:
        def with_structured_output(self, _, **kwargs):
            return self
        def with_retry(self, **_):
            return self
        def with_config(self, _):
            return self
        async def ainvoke(self, _):
            return ChartExtractionResult(has_chartable_data=False, specs=[])

    monkeypatch.setattr(deep_researcher, "configurable_model", FakeExtractModel())

    state = {
        "final_report": "报告中只有定性描述，没有具体数字。",
        "research_failed": False,
    }
    config = {"configurable": {"enable_visualization": True}}

    result = await deep_researcher.visualize(state, config)
    assert result.update.get("chart_htmls") == []
