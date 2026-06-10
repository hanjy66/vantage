"use client";

import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { Workflow } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePrefersReducedMotion } from "@/lib/motion";
import { TimelineStage, RunPhase } from "@/lib/types";
import { Panel, StatusDot, Badge } from "./primitives";

const STAGE_NOTE: Record<string, string> = {
  research_supervisor: "多子 agent 并行检索",
  final_report_generation: "DeepSeek 撰写",
  critic: "Kimi 跨模型审计",
};

export function Timeline({
  stages,
  phase,
  compact,
}: {
  stages: TimelineStage[];
  phase: RunPhase;
  compact?: boolean; // AI_PM 模式：GAP 占中列主位，流水线缩小
}) {
  const doneCount = stages.filter((s) => s.status === "done").length;
  const listRef = useRef<HTMLOListElement>(null);
  const reduced = usePrefersReducedMotion();

  // SSE 步骤逐条点亮：入场 stagger（呼应"实时流式"）；reduced-motion 直接显示
  useGSAP(
    () => {
      if (reduced || !listRef.current) return;
      gsap.from(listRef.current.querySelectorAll("[data-stage]"), {
        autoAlpha: 0,
        y: 8,
        duration: 0.4,
        ease: "power2.out",
        stagger: 0.07,
      });
    },
    { scope: listRef, dependencies: [reduced] },
  );

  return (
    <Panel
      title="研究流水线"
      icon={<Workflow />}
      hint={`${doneCount}/${stages.length} ${phase === "streaming" ? "· 进行中" : ""}`}
      className="h-full"
    >
      <ol ref={listRef} className="relative flex flex-col">
        {stages.map((s, i) => {
          const last = i === stages.length - 1;
          return (
            <li key={s.node} data-stage className={cn("relative flex gap-3 last:pb-0", compact ? "pb-2.5" : "pb-5")}>
              {!last && (
                <span
                  className={cn(
                    "absolute left-[5px] top-4 h-full w-px",
                    s.status === "done" ? "bg-success/40" : "bg-border",
                  )}
                />
              )}
              <span className="z-10 mt-1">
                <StatusDot status={s.status} />
              </span>
              <div className="flex flex-1 items-baseline justify-between gap-2">
                <div className="flex flex-col">
                  <span
                    className={cn(
                      "text-sm",
                      s.status === "pending" ? "text-muted-foreground" : "text-foreground",
                      s.status === "running" && "font-medium",
                    )}
                  >
                    {s.label}
                  </span>
                  {STAGE_NOTE[s.node] && (
                    <span className="text-[11px] text-muted-foreground">
                      {STAGE_NOTE[s.node]}
                    </span>
                  )}
                </div>
                {s.status === "running" && (
                  <Badge tone="info" mono>
                    运行中
                  </Badge>
                )}
                {s.status === "done" && (
                  <span className="font-mono text-[11px] text-success">✓</span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
