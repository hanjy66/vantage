import { CoverageResult, KgRecord, KgRecordSummary } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

// plan 018：GAP 查重（研究主题 / JD ⇄ 过去研究）。query 为统一入口。
export async function fetchCoverageGap(
  query: string,
  mode = "general",
  uploadId = "",
): Promise<CoverageResult> {
  const res = await fetch(`${API_BASE}/jd-gap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, mode, upload_id: uploadId }),
  });
  if (!res.ok) throw new Error(`GAP 查重分析失败 (${res.status})`);
  return res.json();
}

// 历史研究库：列出全部已存研究的摘要（plan 022 整页网格）
export async function listKgRecords(): Promise<KgRecordSummary[]> {
  const res = await fetch(`${API_BASE}/kg`);
  if (!res.ok) throw new Error(`加载历史研究库失败 (${res.status})`);
  const data = await res.json();
  return data.records ?? [];
}

// 回看一条历史研究
export async function fetchKgRecord(id: string): Promise<KgRecord> {
  const res = await fetch(`${API_BASE}/kg/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`回看历史研究失败 (${res.status})`);
  return res.json();
}

// 历史研究 markdown 下载直链
export function kgDownloadUrl(id: string): string {
  return `${API_BASE}/kg/${encodeURIComponent(id)}/download`;
}

export interface UploadResult {
  upload_id: string;
  files: { name: string; type: "pdf" | "image" }[];
}

// plan 009 Phase A：上传 JD PDF / 竞品截图，返回 upload_id 供 /stream 引用
export async function uploadAttachments(files: File[]): Promise<UploadResult> {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: fd });
  if (!res.ok) throw new Error(`附件上传失败 (${res.status})`);
  return res.json();
}

export interface FeedbackPayload {
  research_brief: string;
  user_score: number;
  report_preview?: string;
  comment?: string;
  mode?: string;
  run_id?: string; // 当轮研究的 UUID，与 feedback 一一绑定
}

export async function postFeedback(
  p: FeedbackPayload,
): Promise<{ feedback_id: string; added_to_eval: boolean }> {
  const res = await fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(p),
  });
  if (!res.ok) throw new Error(`提交反馈失败 (${res.status})`);
  return res.json();
}
