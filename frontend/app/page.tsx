"use client";

import { useState } from "react";
import { useResearchStream } from "@/lib/sse";
import {
  EXAMPLE_QUERY,
  EXAMPLE_STAGES,
  EXAMPLE_CRITIQUE_HISTORY,
} from "@/lib/fixture";
import { TopBar } from "@/components/cockpit/TopBar";
import { InputPanel } from "@/components/cockpit/InputPanel";
import { Timeline } from "@/components/cockpit/Timeline";
import { Scorecard } from "@/components/cockpit/Scorecard";
import { CoverageGap } from "@/components/cockpit/CoverageGap";
import { GapDrawer } from "@/components/cockpit/GapDrawer";
import { RecordModal } from "@/components/cockpit/RecordModal";
import { FeedbackControl } from "@/components/cockpit/FeedbackControl";
import { ReportPanel } from "@/components/cockpit/ReportPanel";
import { BriefConfirm } from "@/components/cockpit/BriefConfirm";
import { ChartPanel } from "@/components/cockpit/ChartPanel";
import { EXAMPLE_RESULT } from "@/lib/fixture";
import { buildArchiveHtml, downloadHtml } from "@/lib/archive";
import { PipelineStrip } from "@/components/cockpit/PipelineStrip";
import { ResearchLibrary } from "@/components/cockpit/ResearchLibrary";
import { Badge, InfoHint, Panel } from "@/components/cockpit/primitives";
import { CollapsibleAside } from "@/lib/motion";
import { fetchKgRecord } from "@/lib/api";
import { TIMELINE_ORDER } from "@/lib/types";
import type { KgRecord, Critique, ResultPayload, TimelineStage } from "@/lib/types";
import { X, Sparkles, PenLine, Gauge, ArrowLeft, History, ScrollText } from "lucide-react";

// 回看历史研究时，流水线一律呈现为「全部完成」
const ARCHIVE_STAGES: TimelineStage[] = TIMELINE_ORDER.map((s) => ({
  node: s.node,
  label: s.label,
  status: "done",
}));

// 模式切换的可见后果：不同模式整页信息架构不同（AI_PM 把查重 GAP 提到中列，通用收进二级抽屉）
const MODE_EFFECT: Record<"general" | "interview", string> = {
  general: "通用研究报告 · 标准结构（摘要 / 正文 / 结论）· GAP 分析在二级入口",
  interview: "AI_PM · 深度研究层 + 求职面试层两段输出，GAP 分析前置中列",
};

// context bar 的紧凑版（全文进 ⓘ 渐进披露，不再用全宽彩条平铺）
const MODE_BRIEF: Record<"general" | "interview", string> = {
  general: "标准结构 · 摘要 / 正文 / 结论",
  interview: "深度研究层 + 求职面试层两段输出",
};

export default function Home() {
  const [query, setQuery] = useState(EXAMPLE_QUERY);
  const [mode, setMode] = useState<"general" | "interview">("general");
  const [enableViz, setEnableViz] = useState(false);
  const [enableHitl, setEnableHitl] = useState(false);
  const [strictAudit, setStrictAudit] = useState(false);
  const [enableKg, setEnableKg] = useState(false);
  const [enableObsidian, setEnableObsidian] = useState(false);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [hasRun, setHasRun] = useState(false);
  const [gapDrawerOpen, setGapDrawerOpen] = useState(false);
  const [openRecordId, setOpenRecordId] = useState<string | null>(null);
  const [hintDismissed, setHintDismissed] = useState(false);
  const [leftCollapsed, setLeftCollapsed] = useState(false); // 左：研究输入折叠
  const [rightCollapsed, setRightCollapsed] = useState(false); // 右：质量评分卡折叠
  const [view, setView] = useState<"cockpit" | "library">("cockpit"); // 整页切换：研究台 / 历史库
  const [archive, setArchive] = useState<KgRecord | null>(null); // 非空 = 正在原样回看某条历史研究
  const { state, start, resume, reset } = useResearchStream();

  const cold = !hasRun && state.phase === "idle";

  // 回看态：用历史记录驱动 报告/评分卡/图表，覆盖实时 state（只读）
  const archiveResult: ResultPayload | null = archive
    ? {
        final_report: archive.final_report,
        research_brief: archive.research_brief,
        critique: archive.critique ?? undefined,
        chart_htmls: archive.chart_htmls ?? [],
        revision_count: archive.revision_count,
      }
    : null;
  const archiveHistory: Critique[] = archive?.critique ? [archive.critique] : [];

  const stages = archive ? ARCHIVE_STAGES : cold ? EXAMPLE_STAGES : state.stages;
  const history = archive ? archiveHistory : cold ? EXAMPLE_CRITIQUE_HISTORY : state.critiqueHistory;
  const result = archive ? archiveResult : cold ? EXAMPLE_RESULT : state.result;
  const streaming = state.phase === "streaming";
  const hasReport = !!result?.final_report; // 有正文报告 → 报告升中央主位

  const handleRun = () => {
    setArchive(null); // 开跑即退出回看态
    setHasRun(true);
    start(query, {
      mode,
      enableVisualization: enableViz,
      hitl: enableHitl,
      strictAudit,
      enableKg,
      enableObsidian,
      uploadId: uploadId ?? undefined,
    });
  };
  const handleReset = () => {
    setArchive(null);
    setHasRun(false);
    setEnableKg(false);
    reset();
  };

  // 历史库：打开某条历史研究 → 拉全量 → 灌入回看态，切回研究台原样呈现
  const handleOpenRecord = async (id: string) => {
    try {
      const rec = await fetchKgRecord(id);
      setArchive(rec);
      // 输入框回填用户原始主题（老记录无 topic 时退回系统简报）
      setQuery(rec.research_topic || rec.research_brief || "");
      if (rec.mode === "general" || rec.mode === "interview") setMode(rec.mode);
      setView("cockpit");
    } catch {
      // 失败静默：库页停留，用户可重试（端点已兜底可读错误）
    }
  };

  // 历史库「新建研究」：清回看 + 重置，回到空白研究台
  const handleNewResearch = () => {
    setView("cockpit");
    handleReset();
  };

  // plan 011 P2：点 gap 的「补这个」→ 填入查询框（可累加合并）+ 开「存入知识库」，
  // 不自动开跑，留给用户编辑/合并/调开关后再点运行研究（HITL 停顿）
  const handleFillGap = (skill: string) => {
    setEnableKg(true);
    const head = "深入研究以下方向，形成可复用的知识要点（覆盖定义/现状/关键数据/代表案例）：";
    setQuery((prev) => (prev.startsWith(head) ? `${prev}\n- ${skill}` : `${head}\n- ${skill}`));
  };

  // plan 019「跑这个」：把 GAP 分析的主题/JD append（不覆盖）到研究框，可多次叠加
  const handleAppendTopic = (text: string) => {
    const t = text.trim();
    if (!t) return;
    setQuery((prev) => (prev.includes(t) ? prev : prev.trim() ? `${prev}\n\n${t}` : t));
    setGapDrawerOpen(false);
  };

  // plan 019：下载自包含 HTML 存档——报告正文取页面已渲染 DOM（含 mermaid SVG），
  // 图表用后端自带 plotly.js 的 HTML 片段，主题/简报来自 state。离线单文件可看。
  const handleDownloadReport = () => {
    const reportHtml =
      document.getElementById("adrp-report-article")?.innerHTML ?? "";
    if (!reportHtml) return;
    const title =
      result?.final_report?.match(/^#\s+(.+)$/m)?.[1]?.trim() || "ADRP 研究存档";
    const html = buildArchiveHtml({
      title,
      query,
      brief: result?.research_brief,
      reportHtml,
      chartHtmls: result?.chart_htmls ?? [],
    });
    downloadHtml(`adrp-research-${Date.now()}.html`, html);
  };

  const handleDownloadMd = () => {
    if (!result?.final_report) return;
    const parts: string[] = [];
    if (query) parts.push(`# 研究主题\n\n${query}`);
    if (result.research_brief) parts.push(`# 研究简报\n\n${result.research_brief}`);
    parts.push(`# 研究报告\n\n${result.final_report}`);
    const md = parts.join("\n\n---\n\n");
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `adrp-research-${Date.now()}.md`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };

  const coverageGap = (
    <CoverageGap
      query={query}
      mode={mode}
      onAppendTopic={handleAppendTopic}
      onFillGap={handleFillGap}
      onOpenRecord={setOpenRecordId}
      filling={streaming}
    />
  );

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopBar
        mode={mode}
        onMode={setMode}
        tokens={cold ? 48213 : state.tokens?.total ?? null}
        onOpenGap={() => setGapDrawerOpen(true)}
        onToggleLibrary={() => setView((v) => (v === "library" ? "cockpit" : "library"))}
        inLibrary={view === "library"}
      />

      {view === "library" ? (
        <ResearchLibrary onOpenRecord={handleOpenRecord} onNew={handleNewResearch} />
      ) : (
        <>
      {/* 回看历史研究：顶部 banner（只读 + 返回）取代 context bar */}
      {archive ? (
        <div className="flex items-center justify-between gap-3 border-b border-viz/30 bg-viz/8 px-5 py-2 text-[12px]">
          <div className="flex min-w-0 items-center gap-2 text-foreground">
            <History className="size-4 shrink-0 text-viz" />
            <span className="font-medium">正在回看历史研究</span>
            <Badge tone="accent" mono>{archive.date}</Badge>
            <Badge tone="neutral" mono>{archive.mode === "interview" ? "AI_PM" : "通用"}</Badge>
            <span className="hidden text-muted-foreground sm:inline">· 只读</span>
          </div>
          <button
            onClick={() => setArchive(null)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-[12px] text-muted-foreground transition-all duration-200 ease-out hover:-translate-y-px hover:text-foreground hover:shadow-soft"
          >
            <ArrowLeft className="size-3.5" /> 返回当前研究
          </button>
        </div>
      ) : (
      /* 单条精致 context bar：模式契约 compact + ⓘ 渐进披露；示例提示可关闭。取代两条全宽彩条 */
      <div className="flex items-center justify-between gap-3 border-b border-border bg-card/50 px-5 py-2 text-[11px]">
        <div className="flex items-center gap-2">
          <Badge tone="accent" mono>
            {mode === "interview" ? "AI_PM" : "通用"}
          </Badge>
          <span className="text-muted-foreground">{MODE_BRIEF[mode]}</span>
          <InfoHint text={MODE_EFFECT[mode]} />
        </div>
        {cold && !hintDismissed && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Sparkles className="size-3.5 shrink-0 text-primary/70" />
            <span className="hidden sm:inline">
              <span className="font-medium text-foreground">示例快照</span> · 改写问题并点运行研究看实时流式过程
            </span>
            <button
              onClick={() => setHintDismissed(true)}
              aria-label="关闭提示"
              className="rounded p-0.5 outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/40"
            >
              <X className="size-3" />
            </button>
          </div>
        )}
      </div>
      )}

      {state.phase === "error" && (
        <div className="border-b border-destructive/30 bg-destructive/10 px-5 py-2 text-[12px] text-destructive">
          研究出错：{state.error}
        </div>
      )}

      {/* 状态驱动·报告为中心 + 左右独立可折叠侧栏（GSAP 滑收）+ 侧栏 sticky 跟随滚动 */}
      <main className="flex flex-1 flex-col gap-3 p-3 lg:flex-row lg:items-start">
        {/* 左：研究输入（自带折叠钮，GSAP 收细轨） */}
        <CollapsibleAside
          side="left"
          expandedWidth={340}
          collapsed={leftCollapsed}
          onExpand={() => setLeftCollapsed(false)}
          railIcon={<PenLine />}
          railLabel="研究输入"
          stretch
        >
          <InputPanel
            query={query}
            onQuery={setQuery}
            onRun={handleRun}
            onReset={handleReset}
            streaming={streaming}
            enableViz={enableViz}
            onEnableViz={setEnableViz}
            enableHitl={enableHitl}
            onEnableHitl={setEnableHitl}
            strictAudit={strictAudit}
            onStrictAudit={setStrictAudit}
            enableKg={enableKg}
            onEnableKg={setEnableKg}
            enableObsidian={enableObsidian}
            onEnableObsidian={setEnableObsidian}
            onUploadId={setUploadId}
            onCollapse={() => setLeftCollapsed(true)}
          />
        </CollapsibleAside>

        {/* 中：阶段驱动主区 */}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          {state.phase === "awaiting_confirm" && state.pendingBrief && (
            <BriefConfirm
              pending={state.pendingBrief}
              onApprove={() => resume("approve")}
              onEdit={(brief) => resume("edit", brief)}
            />
          )}
          {/* 出报告：流水线置顶（横条），AI_PM 下排在 GAP 之上，让整列从「流程」起读 */}
          {hasReport && <PipelineStrip stages={stages} phase={state.phase} />}

          {/* 回看态：原样呈现系统生成的研究简报（只读），呼应初始 HITL 简报 */}
          {archive && archive.research_brief && (
            <Panel title="研究简报" icon={<ScrollText />} hint="系统生成 · 只读">
              <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-muted-foreground">
                {archive.research_brief}
              </p>
            </Panel>
          )}

          {/* AI_PM 模式：查重 GAP 前置中列（模式专属） */}
          {mode === "interview" && coverageGap}

          {hasReport ? (
            <>
              <ReportPanel
                report={result?.final_report ?? ""}
                revisionCount={result?.revision_count}
                modelUsed={result?.critique?.model_used}
                onDownload={handleDownloadReport}
                onDownloadMd={handleDownloadMd}
              />
              <ChartPanel charts={result?.chart_htmls ?? []} />
            </>
          ) : (
            /* 没报告：实时流水线当主角，看 Agent 跑 */
            <Timeline stages={stages} phase={state.phase} compact={mode === "interview"} />
          )}
        </div>

        {/* 右：质量评分卡 + 打分回流（自带折叠钮，GSAP 收细轨） */}
        <CollapsibleAside
          side="right"
          expandedWidth={352}
          collapsed={rightCollapsed}
          onExpand={() => setRightCollapsed(false)}
          railIcon={<Gauge />}
          railLabel="质量评分卡"
          scrollable
        >
          <div className="flex flex-col gap-3">
            <Scorecard
              history={history}
              pending={streaming}
              onCollapse={() => setRightCollapsed(true)}
            />
            {hasReport && (
              <FeedbackControl
                researchBrief={archive ? archive.research_brief : query}
                reportPreview={result?.final_report ?? ""}
                mode={mode}
                runId={archive ? archive.id : state.runId}
              />
            )}
          </div>
        </CollapsibleAside>
      </main>
        </>
      )}

      {/* 通用模式：GAP 查重收进二级抽屉，保持通用页简洁 */}
      <GapDrawer open={mode === "general" && gapDrawerOpen} onClose={() => setGapDrawerOpen(false)}>
        {coverageGap}
      </GapDrawer>

      {/* 历史研究回看 modal（点 GAP 命中项触发） */}
      {openRecordId && (
        <RecordModal recordId={openRecordId} onClose={() => setOpenRecordId(null)} />
      )}
    </div>
  );
}
