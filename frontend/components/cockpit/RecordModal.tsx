"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { KgRecord } from "@/lib/types";
import { fetchKgRecord, kgDownloadUrl } from "@/lib/api";
import { buildArchiveHtml, downloadHtml } from "@/lib/archive";
import { MARKDOWN_COMPONENTS } from "./markdown";
import { Badge } from "./primitives";

// 历史研究回看：点 GAP 命中的过去研究 → 弹窗渲染存档报告 markdown + 下载 .md。
export function RecordModal({ recordId, onClose }: { recordId: string; onClose: () => void }) {
  const [record, setRecord] = useState<KgRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRecord(null);
    setError(null);
    fetchKgRecord(recordId)
      .then((r) => !cancelled && setRecord(r))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "加载失败"));
    return () => {
      cancelled = true;
    };
  }, [recordId]);

  // Esc 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const handleDownloadHtml = () => {
    if (!record) return;
    const article = document.getElementById("kg-record-article");
    const reportHtml = article?.innerHTML ?? "";
    const html = buildArchiveHtml({
      title: record.research_brief?.slice(0, 60) || "历史研究存档",
      query: record.research_brief ?? "",
      reportHtml,
      chartHtmls: [],
    });
    downloadHtml(`adrp-archive-${record.id.slice(0, 8)}.html`, html);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-lg border border-border bg-card shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="font-serif text-sm font-semibold text-foreground">历史研究回看</span>
            {record && (
              <>
                <Badge tone="info" mono>{record.date}</Badge>
                <Badge tone="accent" mono>{record.mode}</Badge>
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            {record && (
              <>
                <button
                  onClick={handleDownloadHtml}
                  className="rounded-md border border-viz/30 bg-viz/10 px-2.5 py-1 text-[12px] font-medium text-viz transition-colors hover:bg-viz/15"
                >
                  下载 .html
                </button>
                <a
                  href={kgDownloadUrl(record.id)}
                  className="rounded-md border border-viz/30 bg-viz/10 px-2.5 py-1 text-[12px] font-medium text-viz transition-colors hover:bg-viz/15"
                >
                  下载 .md
                </a>
              </>
            )}
            <button
              onClick={onClose}
              aria-label="关闭"
              className="rounded-md border border-border px-2 py-1 text-[12px] text-muted-foreground transition-colors hover:text-foreground"
            >
              关闭
            </button>
          </div>
        </div>

        <div className="overflow-y-auto px-5 py-4">
          {error && <p className="text-[13px] text-destructive">回看失败：{error}</p>}
          {!error && !record && (
            <p className="text-[13px] text-muted-foreground">加载中…</p>
          )}
          {record && (
            <article id="kg-record-article" className="max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
                {record.final_report || record.research_brief || "（无内容）"}
              </ReactMarkdown>
            </article>
          )}
        </div>
      </div>
    </div>
  );
}
