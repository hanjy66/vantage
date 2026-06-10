"use client";

import { Search, Coins, LayoutGrid, ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { CountUp } from "@/lib/motion";
import { Badge } from "./primitives";

type Mode = "general" | "interview";

// Vantage 品牌标记：双层上升山峰 = 制高点(视角/优势) + 分层(深度)
function VantageMark() {
  return (
    <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary shadow-soft">
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-primary-foreground"
        aria-hidden
      >
        <path d="M4 15 L12 7 L20 15" />
        <path d="M7.5 18.5 L12 13 L16.5 18.5" opacity="0.5" />
      </svg>
    </span>
  );
}

export function TopBar({
  mode,
  onMode,
  tokens,
  onOpenGap,
  onToggleLibrary,
  inLibrary = false,
}: {
  mode: Mode;
  onMode: (m: Mode) => void;
  tokens?: number | null;
  onOpenGap?: () => void; // 通用模式：打开 GAP 查重抽屉（二级入口）
  onToggleLibrary?: () => void; // 点 Logo 在 研究台 ⇄ 研究库 间切换（仿 NotebookLM 点 Logo）
  inLibrary?: boolean; // 当前是否在研究库（决定引导图标/文案）
}) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-card px-5 py-3">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onToggleLibrary}
          title={inLibrary ? "返回研究台" : "研究库 · 查看过去完成的研究"}
          className="group flex items-center gap-3 rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        >
          <span className="transition-transform duration-200 group-hover:-translate-y-px">
            <VantageMark />
          </span>
          <div className="flex flex-col gap-0.5 text-left">
            <h1 className="font-sans text-xl font-semibold leading-none tracking-tight text-foreground">
              Vantage
            </h1>
            <span className="font-mono text-[9.5px] uppercase leading-none tracking-[0.14em] text-muted-foreground">
              Multi-field Agentic Deep Research Platform
            </span>
          </div>
        </button>

        {/* 显式引导：带标签的 viz pill（与 GAP 按钮同语言），初次用户也能一眼发现「过去研究」入口 */}
        <button
          type="button"
          onClick={onToggleLibrary}
          title={inLibrary ? "返回研究台" : "查看过去完成的研究"}
          className="inline-flex self-center items-center gap-1.5 rounded-full border border-viz/40 bg-viz/10 px-3 py-1.5 text-[13px] font-medium text-viz shadow-soft transition-all duration-200 ease-out hover:-translate-y-px hover:bg-viz/20 hover:shadow-raised focus-visible:ring-2 focus-visible:ring-ring/40"
        >
          {inLibrary ? <ArrowLeft className="size-4" /> : <LayoutGrid className="size-4" />}
          {inLibrary ? "返回研究台" : "研究库"}
        </button>
      </div>

      <div className="flex items-center gap-3">
        <Badge tone="accent" mono>
          DeepSeek 写 · Kimi 审
        </Badge>

        {mode === "general" && onOpenGap && (
          <button
            onClick={onOpenGap}
            title="与已有研究做 GAP 分析，识别覆盖盲区，避免重复投入"
            className="inline-flex items-center gap-1.5 rounded-full border border-viz/40 bg-viz/10 px-3 py-1 text-xs font-medium text-viz transition-all duration-200 ease-out hover:-translate-y-px hover:bg-viz/20 hover:shadow-soft"
          >
            <Search className="size-3.5" />
            与已有研究GAP分析
          </button>
        )}

        <div className="flex items-center rounded-full border border-border bg-secondary/40 p-0.5">
          {(["general", "interview"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => onMode(m)}
              aria-pressed={mode === m}
              className={cn(
                "rounded-full px-3 py-1 text-xs outline-none transition-all duration-200 ease-out focus-visible:ring-2 focus-visible:ring-ring/40",
                mode === m
                  ? "bg-viz-gradient text-white shadow-soft"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {m === "general" ? "通用" : "AI_PM"}
            </button>
          ))}
        </div>

        <div className="hidden items-center gap-1.5 md:flex">
          <Coins className="size-3.5 text-muted-foreground" />
          <span className="text-[11px] text-muted-foreground">Tokens</span>
          {tokens != null ? (
            <CountUp value={tokens} className="font-mono text-xs text-foreground" />
          ) : (
            <span className="font-mono text-xs text-foreground">—</span>
          )}
        </div>
      </div>
    </header>
  );
}
