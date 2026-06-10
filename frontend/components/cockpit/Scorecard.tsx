"use client";

import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { Gauge } from "lucide-react";
import { Critique } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CountUp, usePrefersReducedMotion } from "@/lib/motion";
import { Panel, Badge, InfoHint } from "./primitives";
import { Radar } from "./Radar";

// 评分维度一句话释义（对齐 src/modes/*.yaml 的 critic_rubric）。悬停展示，降低认知负荷。
const CRITERIA_DESC: Record<string, string> = {
  事实密度: "每段是否都有可验证的事实/数据点，避免空洞概述",
  引用覆盖: "关键数据是否带 [数字] 引用，可追溯到来源列表",
  内部一致性: "不同章节、不同数据点之间是否相互一致",
  逻辑结构: "章节编排是否层层递进、论点有支撑，而非要点散乱堆砌",
  洞察深度: "是否超越事实罗列给出因果、权衡或判断，而非平铺直叙堆数据",
  四章节完整: "竞品矩阵 / 关键数据 / 3 分话术 / 技术架构 是否齐全且每章有实质内容",
  竞品对称性: "矩阵里每个产品在每个维度是否都有填充，避免某产品某维度空白",
  无冲突: "不同产品不同来源的数据不应自相矛盾",
};

// 单维度行：名称 + 评分进度条 + 常驻一句话释义 + 修订 delta（信息密度对齐冷启动）
function CriterionRow({
  name,
  score,
  before,
}: {
  name: string;
  score: number;
  before: number | null;
}) {
  const desc = CRITERIA_DESC[name];
  const up = before != null ? score - before : 0;
  return (
    <div className="flex flex-col gap-1 border-t border-border/60 pt-2 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5">
          <span className="text-[13px] font-medium text-foreground">{name}</span>
          {desc && <InfoHint text={desc} align="start" />}
        </span>
        <span className="shrink-0 font-mono text-[12px] text-muted-foreground">
          {before != null && (
            <>
              {before}
              <span className="mx-1 text-foreground">→</span>
            </>
          )}
          <span className="text-foreground">{score}</span>
          <span className="text-muted-foreground">/10</span>
          {up > 0 && <span className="ml-1 text-success">+{up}</span>}
        </span>
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-secondary">
        {before != null && (
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-muted-foreground/30"
            style={{ width: `${before * 10}%` }}
          />
        )}
        <div
          data-score-bar
          className="bg-viz-gradient absolute inset-y-0 left-0 origin-left rounded-full transition-all"
          style={{ width: `${score * 10}%` }}
        />
      </div>
    </div>
  );
}

function ConflictRow({
  c,
}: {
  c: Critique["conflicts"][number];
}) {
  const tone = c.severity === "high" ? "danger" : c.severity === "medium" ? "warning" : "neutral";
  const zone =
    c.severity === "high"
      ? "border-destructive/20 bg-destructive/8"
      : c.severity === "medium"
        ? "border-warning/25 bg-warning/10"
        : "border-border bg-secondary/50";
  return (
    <div className={cn("rounded-lg border p-2.5 text-[12px]", zone)}>
      <div className="mb-1 flex items-center gap-1.5">
        <Badge tone={tone}>来源分歧 · {c.severity}</Badge>
      </div>
      <p className="text-foreground">
        {c.claim_a}
        <span className="ml-1 font-mono text-[10px] text-muted-foreground">[{c.claim_a_source}]</span>
      </p>
      <p className="mt-0.5 text-foreground">
        {c.claim_b}
        <span className="ml-1 font-mono text-[10px] text-muted-foreground">[{c.claim_b_source}]</span>
      </p>
    </div>
  );
}

export function Scorecard({
  history,
  pending,
  onCollapse,
}: {
  history: Critique[];
  pending: boolean;
  onCollapse?: () => void;
}) {
  const latest = history[history.length - 1];
  const before = history.length > 1 ? history[0] : null;
  const rootRef = useRef<HTMLDivElement>(null);
  const reduced = usePrefersReducedMotion();

  // 评分卡入场：雷达描边铺开 + 评分条错峰填充。用 fromTo + clearProps，保证终态干净——
  // 否则 gsap.from 在 React 严格模式双调用下会把元素卡在起始态（scaleX:0 → 条被压成 0 宽、渐变看不见）。
  useGSAP(
    () => {
      if (reduced || !rootRef.current) return;
      const tl = gsap.timeline();
      const radar = rootRef.current.querySelector(".radar-wrap");
      if (radar) {
        tl.fromTo(
          radar,
          { autoAlpha: 0, scale: 0.9 },
          {
            autoAlpha: 1,
            scale: 1,
            transformOrigin: "center",
            duration: 0.5,
            ease: "power2.out",
            clearProps: "opacity,visibility,transform",
          },
        );
      }
      const bars = rootRef.current.querySelectorAll("[data-score-bar]");
      if (bars.length) {
        tl.fromTo(
          bars,
          { scaleX: 0 },
          { scaleX: 1, duration: 0.5, ease: "power2.out", stagger: 0.05, clearProps: "transform" },
          "-=0.2",
        );
      }
    },
    { scope: rootRef, dependencies: [latest?.score, reduced] },
  );

  if (!latest) {
    return (
      <Panel title="质量评分卡" icon={<Gauge />} hint="跨模型审计" onCollapse={onCollapse} collapseDir="right" className="h-full">
        <div className="flex flex-col items-center gap-2 py-6 text-center">
          <span className="flex size-10 items-center justify-center rounded-full bg-zone-lavender text-viz">
            <Gauge className="size-5" />
          </span>
          <p className="text-sm text-muted-foreground">
            {pending ? "审计进行中…" : "等待 critic 评分"}
          </p>
        </div>
      </Panel>
    );
  }

  // critic LLM 调用失败：显著呈现报错，便于诊断（而非默默显示 0/未通过）
  if (latest.error) {
    return (
      <Panel title="质量评分卡" icon={<Gauge />} hint="审计失败" onCollapse={onCollapse} collapseDir="right" className="h-full">
        <div className="flex flex-col gap-2">
          <Badge tone="danger">critic 未能完成评分</Badge>
          <p className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 font-mono text-[11px] leading-relaxed text-destructive">
            {latest.error}
          </p>
          <p className="text-[12px] text-muted-foreground">
            报告正文不受影响；此处仅审计环节出错。
          </p>
        </div>
      </Panel>
    );
  }

  const latestBreakdown = latest.criteria_breakdown ?? {};
  const beforeBreakdown = before?.criteria_breakdown ?? {};
  const axes = Object.keys(latestBreakdown);
  const afterVals = axes.map((k) => latestBreakdown[k]);
  const beforeVals = before ? axes.map((k) => beforeBreakdown[k] ?? 0) : null;

  return (
    <Panel
      title="质量评分卡"
      icon={<Gauge />}
      hint={`审计模型 ${latest.model_used.split(":").pop() ?? ""}`}
      onCollapse={onCollapse}
      collapseDir="right"
         >
      <div ref={rootRef} className="flex flex-col gap-4">
        {/* 审计域语义色 lavender：分数+判定收进 summary 块 */}
        <div className="flex items-center justify-between rounded-xl bg-zone-lavender/50 px-3.5 py-3">
          <div className="flex items-baseline gap-2">
            <CountUp
              value={latest.score}
              format={(n) => String(Math.round(n))}
              className="font-mono text-3xl font-semibold text-foreground"
            />
            <span className="font-mono text-sm text-muted-foreground">/ 10</span>
          </div>
          <Badge tone={latest.passed ? "success" : "danger"}>
            {latest.passed ? "通过" : "未通过"}
          </Badge>
        </div>

        {axes.length > 0 && (
          <div className="radar-wrap flex items-center justify-center rounded-xl bg-zone-lavender/30 py-2">
            <Radar
              axes={axes}
              series={[
                ...(beforeVals
                  ? [{ values: beforeVals, className: "fill-none stroke-muted-foreground/50" }]
                  : []),
                { values: afterVals, className: "fill-viz/15 stroke-viz" },
              ]}
            />
          </div>
        )}

        {axes.length > 0 && (
          <div className="flex flex-col gap-2">
            {before && (
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <span className="h-1.5 w-3 rounded-full bg-muted-foreground/30" /> 修订前
                <span className="ml-2 h-1.5 w-3 rounded-full bg-viz" /> 修订后
              </div>
            )}
            {axes.map((k) => (
              <CriterionRow
                key={k}
                name={k}
                score={latestBreakdown[k]}
                before={before ? beforeBreakdown[k] ?? 0 : null}
              />
            ))}
          </div>
        )}

        {latest.conflicts.length > 0 && (
          <div className="flex flex-col gap-2">
            <h3 className="font-serif text-[13px] font-semibold text-foreground">冲突标记</h3>
            {latest.conflicts.map((c, i) => (
              <ConflictRow key={i} c={c} />
            ))}
          </div>
        )}

        {latest.improvement_suggestions.length > 0 && (
          <div className="flex flex-col gap-1.5 rounded-lg bg-muted/40 p-3">
            <h3 className="font-serif text-[13px] font-semibold text-foreground">改进建议</h3>
            <ul className="flex flex-col gap-1">
              {latest.improvement_suggestions.map((s, i) => (
                <li key={i} className={cn("text-[12px] leading-snug text-muted-foreground")}>
                  {s}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Panel>
  );
}
