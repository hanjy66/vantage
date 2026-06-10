"use client";

import { useRef, useState } from "react";
import { CoverageResult, GapItem, OverlapRef } from "@/lib/types";
import { fetchCoverageGap, uploadAttachments } from "@/lib/api";
import { Panel, Badge } from "./primitives";

const STATUS_META: Record<GapItem["status"], { tone: "success" | "warning" | "danger"; label: string }> = {
  covered: { tone: "success", label: "已覆盖" },
  partial: { tone: "warning", label: "部分" },
  gap: { tone: "danger", label: "缺口" },
};

const REC_META: Record<CoverageResult["recommendation"], { tone: "success" | "warning" | "danger"; label: string }> = {
  skip: { tone: "danger", label: "已充分覆盖 · 建议跳过" },
  incremental: { tone: "warning", label: "部分覆盖 · 建议增量" },
  proceed: { tone: "success", label: "无重叠 · 放心跑" },
};

const OVERLAP_TONE: Record<OverlapRef["overlap"], "danger" | "warning" | "neutral"> = {
  high: "danger",
  medium: "warning",
  low: "neutral",
};

export function CoverageGap({
  query,
  mode,
  onAppendTopic,
  onFillGap,
  onOpenRecord,
  filling,
}: {
  query: string; // 左侧研究框内容，作默认分析对象
  mode: "general" | "interview";
  onAppendTopic?: (text: string) => void; // 「跑这个」append 到研究框
  onFillGap?: (skill: string) => void; // 「补这个」append 单条缺口
  onOpenRecord?: (id: string) => void; // 点 overlap → 回看
  filling?: boolean;
}) {
  const [result, setResult] = useState<CoverageResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [pdfName, setPdfName] = useState<string | null>(null);
  const pdfUploadId = useRef<string>("");
  const fileRef = useRef<HTMLInputElement>(null);

  const effective = text.trim() || query;

  const handlePdf = async (list: FileList | null) => {
    if (!list || list.length === 0) return;
    setError(null);
    try {
      const res = await uploadAttachments(Array.from(list));
      pdfUploadId.current = res.upload_id;
      setPdfName(res.files.map((f) => f.name).join(", "));
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    }
  };

  const analyze = async () => {
    if ((!effective.trim() && !pdfUploadId.current) || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchCoverageGap(effective, mode, pdfUploadId.current);
      pdfUploadId.current = "";
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "分析失败");
    } finally {
      setLoading(false);
    }
  };

  const skills = result?.skill_gaps ?? result?.items ?? [];
  const rec = result ? REC_META[result.recommendation] : null;

  return (
    <Panel
      title="主题/JD ⇄ 过去研究/已有知识 GAP分析"
      hint={result ? "已分析" : ""}
      className="h-full"
    >
      <div className="flex h-full flex-col gap-3">
        <div className="flex items-start justify-between gap-2">
          <p className="text-[12px] text-muted-foreground">
            {result?.summary ||
              "与过去已完成的研究、已积累的知识做 GAP 分析，识别覆盖盲区与增量方向，避免重复投入资源。支持文字、截图、PDF 输入。"}
          </p>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              onClick={() => fileRef.current?.click()}
              title="支持 JD/主题 的 PDF 或截图"
              className="rounded-md border border-border px-2 py-1 text-[12px] text-muted-foreground transition-colors hover:text-foreground"
            >
              传文件
            </button>
            <button
              onClick={analyze}
              disabled={loading || (!effective.trim() && !pdfUploadId.current)}
              className="rounded-md border border-viz/30 bg-viz/10 px-2.5 py-1 text-[12px] font-medium text-viz transition-colors hover:bg-viz/15 disabled:opacity-50"
            >
              {loading ? "分析中…" : "GAP分析"}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,image/*"
              onChange={(e) => handlePdf(e.target.files)}
              className="hidden"
            />
          </div>
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          aria-label="研究主题或 JD"
          placeholder="输入研究主题或 JD…（留空则读取左侧研究框内容）"
          className="resize-none rounded-md border border-input bg-background px-2.5 py-1.5 text-[12px] text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/40"
        />
        {pdfName && (
          <div className="flex items-center gap-1.5">
            <Badge tone="info">已载入：{pdfName}</Badge>
            <button
              onClick={() => {
                pdfUploadId.current = "";
                setPdfName(null);
                if (fileRef.current) fileRef.current.value = "";
              }}
              aria-label="移除已载入文件"
              title="移除文件（可改用文字输入或换文件）"
              className="rounded-md border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:border-destructive/40 hover:text-destructive"
            >
              ✕
            </button>
          </div>
        )}
        {error && <p className="text-[12px] text-destructive">{error}</p>}

        {rec && (
          <div className="flex items-center justify-between gap-2">
            <Badge tone={rec.tone}>{rec.label}</Badge>
            {onAppendTopic && effective.trim() && (
              <button
                onClick={() => onAppendTopic(effective)}
                disabled={filling}
                title="把这个主题/JD 加到研究框（不覆盖，可叠加）后再运行"
                className="rounded-md border border-border px-2 py-0.5 text-[12px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
              >
                跑这个
              </button>
            )}
          </div>
        )}

        {result && result.overlaps.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              命中的过去研究（点开回看）
            </span>
            <ul className="flex flex-col divide-y divide-border">
              {result.overlaps.map((o) => (
                <li key={o.record_id} className="flex items-center justify-between gap-2 py-1.5">
                  <button
                    onClick={() => onOpenRecord?.(o.record_id)}
                    className="flex min-w-0 flex-col text-left"
                    title="点开回看这条历史研究"
                  >
                    <span className="truncate text-[13px] text-foreground underline-offset-2 hover:underline">
                      {o.title || "(无标题)"}
                    </span>
                    <span className="truncate text-[11px] text-muted-foreground">
                      {o.date} · {o.note}
                    </span>
                  </button>
                  <Badge tone={OVERLAP_TONE[o.overlap]}>{o.overlap}</Badge>
                </li>
              ))}
            </ul>
          </div>
        )}

        {skills.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              能力对标
            </span>
            <ul className="flex flex-col divide-y divide-border">
              {skills.map((g) => {
                const m = STATUS_META[g.status];
                return (
                  <li key={g.skill} className="flex items-center justify-between gap-3 py-2">
                    <div className="flex min-w-0 flex-col">
                      <span className="text-[13px] text-foreground">{g.skill}</span>
                      <span className="truncate text-[11px] text-muted-foreground">{g.note}</span>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {onFillGap && g.status !== "covered" && (
                        <button
                          onClick={() => onFillGap(g.skill)}
                          disabled={filling}
                          title="触发一次定向研究补齐此项，结果写回知识库"
                          className="rounded-md border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
                        >
                          补这个
                        </button>
                      )}
                      <Badge tone={m.tone}>{m.label}</Badge>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </Panel>
  );
}
