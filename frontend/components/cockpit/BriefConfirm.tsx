"use client";

import { useState, useEffect } from "react";
import { PendingBrief } from "@/lib/types";
import { Panel, Badge } from "./primitives";

// HITL：图停在 confirm_research_brief 的 interrupt，用户审查/编辑 brief 后续跑。
export function BriefConfirm({
  pending,
  onApprove,
  onEdit,
}: {
  pending: PendingBrief;
  onApprove: () => void;
  onEdit: (brief: string) => void;
}) {
  const [draft, setDraft] = useState(pending.draft_brief);
  const [editing, setEditing] = useState(false);

  // 切换到新一次中断时同步草稿
  useEffect(() => {
    setDraft(pending.draft_brief);
    setEditing(false);
  }, [pending.draft_brief]);

  const dirty = draft.trim() !== pending.draft_brief.trim();

  return (
    <Panel
      title="计划确认 · 人在回路"
      hint="已暂停"
      className="border-warning/40 bg-warning/5"
    >
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <Badge tone="warning">等待你确认研究简报</Badge>
          <span className="text-[12px] text-muted-foreground">
            研究已规划完毕，确认或修改后再开跑检索。
          </span>
        </div>

        {editing ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={6}
            aria-label="编辑研究简报"
            className="resize-y rounded-md border border-input bg-background px-3 py-2 text-[13px] leading-relaxed text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
          />
        ) : (
          <div className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-md border border-border bg-card px-3 py-2 text-[13px] leading-relaxed text-foreground/90">
            {pending.draft_brief || "（无草稿内容）"}
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => (editing && dirty ? onEdit(draft) : onApprove())}
            className="bg-viz-gradient flex-1 rounded-md px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            {editing && dirty ? "用修改后的简报开跑" : "确认并开跑检索"}
          </button>
          <button
            onClick={() => setEditing((v) => !v)}
            className="rounded-md border border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            {editing ? "取消编辑" : "编辑简报"}
          </button>
        </div>
      </div>
    </Panel>
  );
}
