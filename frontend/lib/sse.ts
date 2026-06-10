"use client";

import { useCallback, useRef, useState } from "react";
import {
  Critique,
  NodeEvent,
  PendingBrief,
  ResultPayload,
  RunState,
  TimelineStage,
  TokenUsage,
  TIMELINE_ORDER,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

function freshStages(): TimelineStage[] {
  return TIMELINE_ORDER.map((s) => ({ node: s.node, label: s.label, status: "pending" }));
}

export interface StartOptions {
  mode?: "general" | "interview";
  enableVisualization?: boolean;
  maxRevisions?: number;
  hitl?: boolean;
  uploadId?: string;
  strictAudit?: boolean;
  enableKg?: boolean;
  enableObsidian?: boolean;
}

const IDLE: RunState = {
  phase: "idle",
  runId: null,
  stages: freshStages(),
  result: null,
  critiqueHistory: [],
  tokens: null,
  pendingBrief: null,
  error: null,
};

export function useResearchStream(initial?: Partial<RunState>) {
  const [state, setState] = useState<RunState>({ ...IDLE, ...initial });
  const esRef = useRef<EventSource | null>(null);

  const close = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const reset = useCallback(() => {
    close();
    setState({ ...IDLE, stages: freshStages() });
  }, [close]);

  // start 与 resume 共用：挂事件监听。resume 不重置时间线/token，从中断处继续累积。
  const wire = useCallback(
    (url: string) => {
      close();
      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener("node", (e) => {
        const ev: NodeEvent = JSON.parse((e as MessageEvent).data);
        setState((prev) => ({
          ...prev,
          stages: prev.stages.map((s) =>
            s.node === ev.node
              ? { ...s, status: ev.phase === "start" ? "running" : "done" }
              : s,
          ),
        }));
      });

      es.addEventListener("result", (e) => {
        const payload: ResultPayload = JSON.parse((e as MessageEvent).data);
        setState((prev) => {
          const history = [...prev.critiqueHistory];
          if (payload.critique) history.push(payload.critique as Critique);
          return {
            ...prev,
            result: { ...prev.result, ...payload },
            critiqueHistory: history,
          };
        });
      });

      es.addEventListener("tokens", (e) => {
        const usage: TokenUsage = JSON.parse((e as MessageEvent).data);
        setState((prev) => ({ ...prev, tokens: usage }));
      });

      es.addEventListener("interrupt", (e) => {
        const pending: PendingBrief = JSON.parse((e as MessageEvent).data);
        setState((prev) => ({ ...prev, phase: "awaiting_confirm", pendingBrief: pending }));
        close();
      });

      es.addEventListener("error", (e) => {
        const data = (e as MessageEvent).data;
        if (data) {
          try {
            const { message } = JSON.parse(data);
            setState((prev) => ({ ...prev, phase: "error", error: message }));
            return;
          } catch {
            /* not a backend error frame */
          }
        }
        setState((prev) =>
          prev.phase === "streaming" ? { ...prev, phase: "error", error: "连接中断" } : prev,
        );
        close();
      });

      es.addEventListener("done", () => {
        setState((prev) => ({
          ...prev,
          // interrupt/error 已设终态，done 不覆盖
          phase: prev.phase === "streaming" ? "done" : prev.phase,
        }));
        close();
      });
    },
    [close],
  );

  const start = useCallback(
    (query: string, opts: StartOptions = {}) => {
      const runId = crypto.randomUUID();
      setState({
        phase: "streaming",
        runId,
        stages: freshStages(),
        result: null,
        critiqueHistory: [],
        tokens: null,
        pendingBrief: null,
        error: null,
      });
      const params = new URLSearchParams({
        q: query,
        mode: opts.mode ?? "general",
        enable_visualization: String(opts.enableVisualization ?? false),
        max_revisions: String(opts.maxRevisions ?? 1),
        hitl: String(opts.hitl ?? false),
        strict_audit: String(opts.strictAudit ?? false),
        enable_kg: String(opts.enableKg ?? false),
        enable_obsidian_export: String(opts.enableObsidian ?? false),
      });
      if (opts.uploadId) params.set("upload_id", opts.uploadId);
      wire(`${API_BASE}/stream?${params.toString()}`);
    },
    [wire],
  );

  // HITL：用户确认/编辑 brief 后续跑（保留已点亮的时间线与累计 token）
  const resume = useCallback(
    (action: "approve" | "edit", finalBrief?: string) => {
      const tid = state.pendingBrief?.thread_id;
      if (!tid) return;
      setState((prev) => ({ ...prev, phase: "streaming", pendingBrief: null }));
      const params = new URLSearchParams({ thread_id: tid, action });
      if (action === "edit" && finalBrief) params.set("final_brief", finalBrief);
      wire(`${API_BASE}/resume?${params.toString()}`);
    },
    [wire, state.pendingBrief],
  );

  return { state, start, resume, reset };
}
