"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import {
  Plus,
  FileText,
  BarChart3,
  BookText,
  Sparkles,
  Download,
  Search,
  LayoutGrid,
  List as ListIcon,
} from "lucide-react";
import { KgRecordSummary } from "@/lib/types";
import { listKgRecords, kgDownloadUrl } from "@/lib/api";
import { usePrefersReducedMotion } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { Badge, MetaChip } from "./primitives";

// 历史研究库：仿 NotebookLM 首页——搜索 + 网格/列表切换 + 新建。点开某条原样回看。
export function ResearchLibrary({
  onOpenRecord,
  onNew,
}: {
  onOpenRecord: (id: string) => void;
  onNew: () => void;
}) {
  const [records, setRecords] = useState<KgRecordSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [view, setView] = useState<"grid" | "list">("grid");
  const listRef = useRef<HTMLDivElement>(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    let cancelled = false;
    listKgRecords()
      .then((r) => !cancelled && setRecords(r))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "加载失败"));
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    if (!records) return [];
    const kw = q.trim().toLowerCase();
    return kw ? records.filter((r) => r.title.toLowerCase().includes(kw)) : records;
  }, [records, q]);

  // 入场动画：fromTo 保证终态可见 + clearProps 收尾，避免 from 被打断后卡在半透明。
  // 只在数据首次加载/视图切换时跑一次；搜索过滤产生的新节点按 CSS 默认（可见）呈现。
  useGSAP(
    () => {
      if (reduced || !listRef.current || records === null) return;
      gsap.fromTo(
        listRef.current.querySelectorAll("[data-card]"),
        { autoAlpha: 0, y: 12 },
        {
          autoAlpha: 1,
          y: 0,
          duration: 0.4,
          ease: "power2.out",
          stagger: 0.03,
          clearProps: "opacity,visibility,transform",
        },
      );
    },
    { scope: listRef, dependencies: [records, view, reduced] },
  );

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-7">
      {/* 标题 + 工具栏：搜索 / 视图切换 / 新建 */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">研究库</h1>
          <p className="text-[13px] text-muted-foreground">
            过去完成的研究 · 仅显示开启「存入知识库」后保存的研究
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="按标题搜索…"
              className="h-9 w-44 rounded-full border border-border bg-card pl-8 pr-3 text-[13px] text-foreground outline-none transition-all placeholder:text-muted-foreground focus-visible:w-56 focus-visible:ring-2 focus-visible:ring-ring/40"
            />
          </div>

          <div className="flex items-center rounded-full border border-border bg-secondary/40 p-0.5">
            {(["grid", "list"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                aria-pressed={view === v}
                aria-label={v === "grid" ? "网格视图" : "列表视图"}
                className={cn(
                  "flex size-7 items-center justify-center rounded-full transition-all duration-200",
                  view === v ? "bg-card text-foreground shadow-soft" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {v === "grid" ? <LayoutGrid className="size-4" /> : <ListIcon className="size-4" />}
              </button>
            ))}
          </div>

          <button
            onClick={onNew}
            className="bg-viz-gradient inline-flex h-9 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-medium text-white shadow-soft transition-all duration-200 ease-out hover:-translate-y-px hover:shadow-raised"
          >
            <Plus className="size-4" /> 新建
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-[13px] text-destructive">
          加载历史研究库失败：{error}
        </div>
      )}

      {/* 加载骨架 */}
      {records === null && !error && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="min-h-[148px] animate-pulse rounded-xl border border-border bg-card/50 shadow-soft" />
          ))}
        </div>
      )}

      {/* 空态 */}
      {records !== null && records.length === 0 && !error && (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-border bg-card/40 py-14 text-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-zone-sky text-viz">
            <Sparkles className="size-6" />
          </span>
          <p className="text-sm font-medium text-foreground">还没有保存过的研究</p>
          <p className="max-w-md text-[12.5px] text-muted-foreground">
            在研究输入里开启「存入知识库」开关后跑一轮研究，完成的研究就会出现在这里，可随时原样回看。
          </p>
          <button onClick={onNew} className="mt-2 text-[13px] font-medium text-viz hover:underline">
            ＋ 新建研究
          </button>
        </div>
      )}

      {/* 搜索无命中 */}
      {records !== null && records.length > 0 && filtered.length === 0 && (
        <p className="rounded-xl border border-dashed border-border bg-card/40 py-10 text-center text-[13px] text-muted-foreground">
          没有匹配「{q}」的研究
        </p>
      )}

      {/* 网格视图 */}
      {records !== null && filtered.length > 0 && view === "grid" && (
        <div ref={listRef} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <button
            data-card
            onClick={onNew}
            className="group flex min-h-[148px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-card/60 p-5 text-muted-foreground shadow-soft outline-none transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-viz/50 hover:text-foreground hover:shadow-raised focus-visible:ring-2 focus-visible:ring-ring/40"
          >
            <span className="flex size-11 items-center justify-center rounded-full bg-viz/10 text-viz transition-transform duration-200 group-hover:scale-110">
              <Plus className="size-5" />
            </span>
            <span className="text-sm font-medium">新建研究</span>
          </button>
          {filtered.map((r) => (
            <GridCard key={r.id} rec={r} onOpen={() => onOpenRecord(r.id)} />
          ))}
        </div>
      )}

      {/* 列表视图 */}
      {records !== null && filtered.length > 0 && view === "list" && (
        <div ref={listRef} className="overflow-hidden rounded-xl border border-border bg-card shadow-soft">
          <div className="flex items-center gap-3 border-b border-border px-4 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            <span className="flex-1">标题</span>
            <span className="w-16 text-right">来源</span>
            <span className="w-24 text-right">日期</span>
            <span className="w-20 text-right">模式</span>
          </div>
          {filtered.map((r) => (
            <ListRow key={r.id} rec={r} onOpen={() => onOpenRecord(r.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function GridCard({ rec, onOpen }: { rec: KgRecordSummary; onOpen: () => void }) {
  const interview = rec.mode === "interview";
  return (
    <div
      data-card
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen())}
      className="group relative flex min-h-[148px] cursor-pointer flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-soft outline-none transition-all duration-200 ease-out hover:-translate-y-0.5 hover:shadow-raised focus-visible:ring-2 focus-visible:ring-ring/40"
    >
      <div className="flex items-start justify-between gap-2">
        <span
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-xl text-viz",
            interview ? "bg-zone-lavender" : "bg-zone-sky",
          )}
        >
          {interview ? <BookText className="size-5" /> : <FileText className="size-5" />}
        </span>
        <a
          href={kgDownloadUrl(rec.id)}
          onClick={(e) => e.stopPropagation()}
          aria-label="下载 .md"
          title="下载 .md"
          className="rounded-md p-1 text-muted-foreground/60 opacity-0 outline-none transition-all hover:bg-muted hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
        >
          <Download className="size-4" />
        </a>
      </div>

      <h3 className="line-clamp-2 flex-1 text-[14px] font-medium leading-snug text-foreground">
        {rec.title}
      </h3>

      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone="accent" mono>
          {interview ? "AI_PM" : "通用"}
        </Badge>
        <MetaChip>{rec.date}</MetaChip>
        <span className="font-mono text-[10px] text-muted-foreground">{rec.notes_count} 来源</span>
        {rec.has_charts && (
          <span className="inline-flex items-center gap-0.5 font-mono text-[10px] text-viz">
            <BarChart3 className="size-3" /> 图表
          </span>
        )}
      </div>
    </div>
  );
}

function ListRow({ rec, onOpen }: { rec: KgRecordSummary; onOpen: () => void }) {
  const interview = rec.mode === "interview";
  return (
    <div
      data-card
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen())}
      className="group flex cursor-pointer items-center gap-3 border-b border-border/60 px-4 py-3 text-[13px] outline-none transition-colors last:border-b-0 hover:bg-muted/40 focus-visible:bg-muted/40"
    >
      <span
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-lg text-viz",
          interview ? "bg-zone-lavender" : "bg-zone-sky",
        )}
      >
        {interview ? <BookText className="size-4" /> : <FileText className="size-4" />}
      </span>
      <span className="line-clamp-1 flex-1 font-medium text-foreground">{rec.title}</span>
      <span className="flex w-16 items-center justify-end gap-1 font-mono text-[11px] text-muted-foreground">
        {rec.has_charts && <BarChart3 className="size-3 text-viz" />}
        {rec.notes_count}
      </span>
      <span className="w-24 text-right font-mono text-[11px] text-muted-foreground">{rec.date}</span>
      <span className="flex w-20 justify-end">
        <Badge tone="accent" mono>
          {interview ? "AI_PM" : "通用"}
        </Badge>
      </span>
    </div>
  );
}
