import { Workflow } from "lucide-react";
import { TimelineStage, RunPhase } from "@/lib/types";
import { StatusDot } from "./primitives";

// 出报告后流水线降为顶部进度条——但不过度压缩：标题行 + 阶段行两段式，
// 每个阶段带状态点 + 标签 + 连接线，整体可读、可一眼看到「跑到哪了」。
export function PipelineStrip({
  stages,
  phase,
}: {
  stages: TimelineStage[];
  phase: RunPhase;
}) {
  const done = stages.filter((s) => s.status === "done").length;
  const pct = stages.length ? Math.round((done / stages.length) * 100) : 0;
  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-card px-4 py-3 shadow-soft">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-foreground">
          <span className="flex size-6 items-center justify-center rounded-lg bg-zone-sky text-viz">
            <Workflow className="size-4" />
          </span>
          <span className="font-serif text-sm font-semibold tracking-tight">研究流水线</span>
        </div>
        <span className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
          {phase === "streaming" && (
            <span className="rounded-full bg-info/10 px-2 py-0.5 text-info">进行中</span>
          )}
          {done}/{stages.length}
        </span>
      </div>

      <div className="flex items-center gap-2 overflow-x-auto pb-0.5">
        {stages.map((s, i) => (
          <div key={s.node} className="flex shrink-0 items-center gap-2">
            <div className="flex items-center gap-1.5">
              <StatusDot status={s.status} />
              <span
                className={
                  s.status === "pending"
                    ? "text-[12px] text-muted-foreground"
                    : s.status === "running"
                      ? "text-[12px] font-semibold text-foreground"
                      : "text-[12px] text-foreground"
                }
              >
                {s.label}
              </span>
            </div>
            {i < stages.length - 1 && (
              <span
                className={
                  s.status === "done" ? "h-px w-5 bg-success/40" : "h-px w-5 bg-border"
                }
              />
            )}
          </div>
        ))}
      </div>

      <div className="h-1 overflow-hidden rounded-full bg-secondary">
        <div
          className="bg-viz-gradient h-full rounded-full transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
