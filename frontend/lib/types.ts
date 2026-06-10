// 对齐后端 server/sse.py 的事件协议与 critic 输出结构

export type NodePhase = "start" | "end";

export interface NodeEvent {
  node: string;
  stage: string;
  phase: NodePhase;
}

export interface ConflictItem {
  claim_a: string;
  claim_a_source: string;
  claim_b: string;
  claim_b_source: string;
  severity: "high" | "medium" | "low";
}

export interface Critique {
  score: number;
  passed: boolean;
  criteria_breakdown: Record<string, number>;
  conflicts: ConflictItem[];
  improvement_suggestions: string[];
  model_used: string;
  error?: string; // critic LLM 调用失败时的报错（critic_failed / research_failed）
}

export interface ResultPayload {
  critique?: Critique;
  chart_htmls?: string[];
  final_report?: string;
  research_brief?: string;
  revision_count?: number;
  research_failed?: boolean;
  research_failure_reason?: string;
  escalated?: boolean;
  escalation_model_used?: string;
}

// 时间线节点运行态
export type StageStatus = "pending" | "running" | "done";

export interface TimelineStage {
  node: string;
  label: string;
  status: StageStatus;
}

// 主图顶层节点的规范顺序（与后端 NODE_STAGE 对应；澄清/确认在 headline demo 中跳过）
export const TIMELINE_ORDER: { node: string; label: string }[] = [
  { node: "ingest_attachments", label: "读取输入" },
  { node: "write_research_brief", label: "规划" },
  { node: "research_supervisor", label: "检索研究" },
  { node: "final_report_generation", label: "综合报告" },
  { node: "critic", label: "跨模型审计" },
  { node: "visualize", label: "数据可视化" },
];

// GAP 查重 + 能力对标（对齐后端 server/jd_gap.py，plan 018）
export interface GapItem {
  skill: string;
  status: "covered" | "partial" | "gap";
  note: string;
}

// 命中的一条过去研究（带 id 供回看）
export interface OverlapRef {
  record_id: string;
  title: string;
  date: string;
  overlap: "high" | "medium" | "low";
  note: string;
}

export interface CoverageResult {
  recommendation: "skip" | "incremental" | "proceed";
  summary: string;
  overlaps: OverlapRef[];
  skill_gaps: GapItem[];
  items?: GapItem[]; // 向后兼容别名 = skill_gaps
}

// 回看一条历史研究（GET /kg/{id}）——plan 022 扩存评分卡+图表，支持原样回看
export interface KgRecord {
  id: string;
  date: string;
  mode: string;
  research_topic?: string; // 用户原始输入的研究主题（回看时回填输入框）
  research_brief: string;
  final_report: string;
  critique?: Critique | null;
  chart_htmls?: string[];
  revision_count?: number;
}

// 历史研究库网格的一张卡（GET /kg 列表摘要）
export interface KgRecordSummary {
  id: string;
  date: string;
  mode: string;
  title: string;
  notes_count: number;
  has_charts: boolean;
}

export type RunPhase = "idle" | "streaming" | "awaiting_confirm" | "done" | "error";

// HITL：图停在 confirm_research_brief 的 interrupt，等用户确认/编辑 brief
export interface PendingBrief {
  thread_id: string;
  draft_brief: string;
  instruction: string;
}

export interface TokenUsage {
  input: number;
  output: number;
  total: number;
}

export interface RunState {
  phase: RunPhase;
  runId: string | null; // 每次 start() 生成的 UUID，与 feedback 一一绑定
  stages: TimelineStage[];
  result: ResultPayload | null;
  // critic 每次结束都 emit 一次 critique；留存用于"修订前→后"对比（如竞品对称性 5→9）
  critiqueHistory: Critique[];
  tokens: TokenUsage | null;
  pendingBrief: PendingBrief | null;
  error: string | null;
}
