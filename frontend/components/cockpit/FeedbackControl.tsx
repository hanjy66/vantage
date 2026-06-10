"use client";

import { useEffect, useState } from "react";
import { postFeedback } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Panel, Badge } from "./primitives";

export function FeedbackControl({
  researchBrief,
  reportPreview,
  mode,
  runId,
}: {
  researchBrief: string;
  reportPreview: string;
  mode: "general" | "interview";
  runId?: string | null;
}) {
  const [stars, setStars] = useState(0);
  const [hover, setHover] = useState(0);
  const [comment, setComment] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 跑了新一轮（报告变化）→ 重置反馈表单，让用户能给新一轮单独打分（每轮一条反馈）。
  useEffect(() => {
    setStars(0);
    setComment("");
    setDone(false);
    setError(null);
  }, [reportPreview]);

  const submit = async () => {
    if (stars === 0) {
      setError("请先选择星级");
      return;
    }
    setError(null);
    try {
      await postFeedback({
        research_brief: researchBrief,
        user_score: stars * 2, // 1-5 星 → 0-10 人评
        report_preview: reportPreview,
        comment: comment.trim(),
        mode,
        run_id: runId ?? undefined,
      });
      setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    }
  };

  return (
    <Panel title="用户打分回流" hint={done ? "已入评测集" : "人评 × 机评"} className="h-full">
      <div className="flex h-full flex-col gap-3">
        <p className="text-[12px] leading-relaxed text-muted-foreground">
          打分 + 评论回流写入评测集（feedback.jsonl），构成人评×机评数据飞轮，驱动下一轮迭代。
        </p>

        <div className="flex items-center gap-1" onMouseLeave={() => setHover(0)}>
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              onClick={() => setStars(n)}
              onMouseEnter={() => setHover(n)}
              aria-label={`评 ${n} 星`}
              className={cn(
                "rounded p-1 text-xl leading-none outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/40",
                (hover || stars) >= n ? "text-warning" : "text-border",
              )}
            >
              ★
            </button>
          ))}
        </div>

        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          aria-label="评论反馈"
          placeholder="写下具体反馈（如：豆包数据缺一手来源 / 洞察够深但结构松散）…"
          className="resize-none rounded-md border border-input bg-background px-3 py-2 text-[12px] text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/40"
        />

        <div className="flex items-center gap-3">
          <button
            onClick={submit}
            disabled={done}
            className="bg-viz-gradient rounded-md px-3 py-1.5 text-[13px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {done ? "已提交" : "提交反馈"}
          </button>
          {done && <Badge tone="success">已纳入评测集</Badge>}
        </div>

        {error && <p className="text-[12px] text-destructive">{error}</p>}
      </div>
    </Panel>
  );
}
