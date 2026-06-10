import { Critique, GapItem, ResultPayload, TimelineStage, TIMELINE_ORDER } from "./types";

// 冷启动示例快照：让环境不定的冷访客 5 秒看懂系统能力，无需等真后端跑完。
// 点"重跑/换问题"才打真 /stream。

export const EXAMPLE_QUERY = "对比 Perplexity、ChatGPT、Claude、豆包的产品定位与竞争策略";

const CRITIQUE_BEFORE: Critique = {
  score: 5,
  passed: false,
  criteria_breakdown: {
    事实密度: 6,
    引用覆盖: 6,
    内部一致性: 7,
    逻辑结构: 5,
    洞察深度: 5,
  },
  conflicts: [],
  improvement_suggestions: [
    "[逻辑结构] 缺少横向对比表，读者难以一眼比较，建议先立对比矩阵再分述。",
    "[洞察深度] 多为事实罗列，缺少“为什么/意味着什么”的因果与判断。",
  ],
  model_used: "openai:moonshot-v1-128k",
};

const CRITIQUE_AFTER: Critique = {
  score: 9,
  passed: true,
  criteria_breakdown: {
    事实密度: 9,
    引用覆盖: 8,
    内部一致性: 9,
    逻辑结构: 9,
    洞察深度: 9,
  },
  conflicts: [
    {
      claim_a: "Perplexity 月活约 1500 万",
      claim_a_source: "TechCrunch 2025-03",
      claim_b: "Perplexity 月活已突破 3000 万",
      claim_b_source: "公司博客 2025-04",
      severity: "medium",
    },
  ],
  improvement_suggestions: [
    "[引用覆盖] 部分国内数据缺一手来源，建议补官方财报或招股书。",
  ],
  model_used: "openai:moonshot-v1-128k",
};

export const EXAMPLE_RESULT: ResultPayload = {
  critique: CRITIQUE_AFTER,
  chart_htmls: [EXAMPLE_CHART_HTML()],
  revision_count: 1,
  research_failed: false,
  escalated: false,
  final_report: EXAMPLE_REPORT_MD(),
};

// 冷启动示例报告正文：覆盖标题/列表/表格/强调，验证 markdown 渲染管线
function EXAMPLE_REPORT_MD(): string {
  return `# 四大 AI 对话产品竞品分析

## 摘要

Perplexity 以「答案引擎 + 引用溯源」切研究场景；ChatGPT 以通用能力与生态护城河领先；Claude 主打长上下文与企业级合规；豆包依托字节流量在国内快速起量。四者定位互不重叠，竞争发生在用户心智的**边界地带**。

## 横向对比

| 产品 | 核心定位 | 关键壁垒 | 主要风险 |
| --- | --- | --- | --- |
| Perplexity | 答案引擎 | 引用溯源体验 | 通用模型方挤压 |
| ChatGPT | 通用助手 | 生态 + 分发 | 监管与成本 |
| Claude | 长上下文 / 合规 | 企业信任 | C 端心智弱 |
| 豆包 | 国内流量入口 | 字节分发 | 同质化竞争 |

## 关键判断

- **研究场景**是 Perplexity 的护城河，但易被通用模型的「联网 + 引用」功能侵蚀。
- ChatGPT 的真正壁垒在分发与生态，而非模型本身。
- Claude 的企业级合规定位与 C 端心智存在张力，需差异化叙事。

## 结论

短期看格局稳定，中期看通用模型能力外溢会重塑竞争边界，垂直产品需在体验深度上建立不可替代性。

## 来源列表

[1] Perplexity 官方定价页: https://www.perplexity.ai/pro
[2] OpenAI API 定价: https://openai.com/api/pricing
[3] Anthropic Claude 定价: https://www.anthropic.com/pricing
[4] 火山引擎（豆包 API 定价）: https://www.volcengine.com/docs/82379/1099320`;
}

// 冷启动示例图表（轻量内联 SVG，零外部依赖；明确为示例快照，不误导）
function EXAMPLE_CHART_HTML(): string {
  return `<!doctype html><html><head><meta charset="utf-8">
<style>body{margin:0;font-family:system-ui,sans-serif;background:#fff;color:#1c2433}
.wrap{padding:16px}.t{font-size:14px;font-weight:600;margin:0 0 12px}
.row{display:flex;align-items:center;gap:8px;margin:8px 0;font-size:12px}
.lbl{width:88px;text-align:right;color:#475569}
.bar{height:18px;border-radius:3px;background:#3b4d8f}
.val{font-variant-numeric:tabular-nums;color:#334155}
.note{margin-top:14px;font-size:10px;color:#94a3b8}</style></head>
<body><div class="wrap"><p class="t">主流 AI 产品月活跃用户（MAU，万）</p>
<div class="row"><span class="lbl">ChatGPT</span><span class="bar" style="width:88%"></span><span class="val">~80000</span></div>
<div class="row"><span class="lbl">豆包</span><span class="bar" style="width:38%"></span><span class="val">~34500</span></div>
<div class="row"><span class="lbl">Perplexity</span><span class="bar" style="width:11%"></span><span class="val">~10000</span></div>
<div class="row"><span class="lbl">Claude</span><span class="bar" style="width:3%"></span><span class="val">~1890</span></div>
<p class="note">示例数据 · 仅用于界面展示</p></div></body></html>`;
}

export const EXAMPLE_CRITIQUE_HISTORY: Critique[] = [CRITIQUE_BEFORE, CRITIQUE_AFTER];

export const EXAMPLE_STAGES: TimelineStage[] = TIMELINE_ORDER.map((s) => ({
  node: s.node,
  label: s.label,
  status: "done" as const,
}));

// JD gap 示例（冷启动展示用；真实分析走 /jd-gap REST）
export const EXAMPLE_JD_GAP: GapItem[] = [
  { skill: "LLM 应用架构", status: "covered", note: "多 agent 编排 + 上下文防火墙已落地" },
  { skill: "评估体系", status: "covered", note: "25 条评测集 + 跨模型 critic + 人机对照" },
  { skill: "数据可视化", status: "partial", note: "Plotly 图表已做，仪表盘交互待补" },
  { skill: "增长/商业化", status: "gap", note: "缺商业化指标与增长实验经验" },
  { skill: "大规模在线系统", status: "gap", note: "demo 规模，缺高并发生产经验" },
];
