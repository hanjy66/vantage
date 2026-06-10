"use client";

import { useRef, useState } from "react";
import {
  PenLine,
  Upload,
  BarChart3,
  PauseCircle,
  ShieldCheck,
  Database,
  Share2,
  Play,
  RotateCcw,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Switch } from "@/lib/motion";
import { uploadAttachments } from "@/lib/api";
import { Panel, Badge, MetaChip, InfoHint } from "./primitives";

export function InputPanel({
  query,
  onQuery,
  onRun,
  onReset,
  streaming,
  enableViz,
  onEnableViz,
  enableHitl,
  onEnableHitl,
  strictAudit,
  onStrictAudit,
  enableKg,
  onEnableKg,
  enableObsidian,
  onEnableObsidian,
  onUploadId,
  onCollapse,
}: {
  query: string;
  onQuery: (v: string) => void;
  onRun: () => void;
  onReset: () => void;
  streaming: boolean;
  enableViz: boolean;
  onEnableViz: (v: boolean) => void;
  enableHitl: boolean;
  onEnableHitl: (v: boolean) => void;
  strictAudit: boolean;
  onStrictAudit: (v: boolean) => void;
  enableKg: boolean;
  onEnableKg: (v: boolean) => void;
  enableObsidian: boolean;
  onEnableObsidian: (v: boolean) => void;
  onUploadId: (id: string | null) => void;
  onCollapse?: () => void;
}) {
  const apiBase =
    process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";
  const [showGuide, setShowGuide] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [chips, setChips] = useState<{ name: string; type: string }[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);

  const handleFiles = async (list: FileList | null) => {
    if (!list || list.length === 0) return;
    setUploading(true);
    setUploadErr(null);
    try {
      const res = await uploadAttachments(Array.from(list));
      setChips(res.files);
      onUploadId(res.upload_id);
    } catch (e) {
      setUploadErr(e instanceof Error ? e.message : "上传失败");
      onUploadId(null);
    } finally {
      setUploading(false);
    }
  };

  const clearFiles = () => {
    setChips([]);
    onUploadId(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <Panel
      title="研究输入"
      icon={<PenLine />}
      onCollapse={onCollapse}
      collapseDir="left"
      className="h-full"
    >
      <div className="flex flex-col gap-4">
        <textarea
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          rows={4}
          aria-label="研究查询或 JD 输入"
          placeholder="粘贴 JD 或输入研究问题…"
          className="resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/40"
        />

        {/* 主行动紧跟输入框，无需下拖即可点 */}
        <div className="flex gap-2">
          <button
            onClick={onRun}
            disabled={streaming || !query.trim()}
            className={cn(
              "flex flex-1 items-center justify-center gap-2 rounded-full bg-primary px-3 py-2.5 text-sm font-medium text-primary-foreground shadow-soft transition-all duration-200 ease-out",
              "hover:-translate-y-px hover:bg-primary/90 hover:shadow-raised disabled:cursor-not-allowed disabled:translate-y-0 disabled:opacity-50 disabled:shadow-none",
            )}
          >
            <Play className="size-4" />
            {streaming ? "研究进行中…" : "运行研究"}
          </button>
          <button
            onClick={onReset}
            disabled={streaming}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground transition-all duration-200 ease-out hover:-translate-y-px hover:text-foreground hover:shadow-soft disabled:opacity-50"
          >
            <RotateCcw className="size-3.5" />
            重置
          </button>
        </div>

        <div className="flex flex-col gap-2 rounded-lg border border-dashed border-border bg-zone-sky/40 px-3 py-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-1.5">
              <span className="shrink-0 text-[12px] font-medium text-foreground">附件上传</span>
              <MetaChip>Phase A</MetaChip>
              <InfoHint
                align="start"
                text="上传 JD、竞品截图、图表或相关文档，模型先做多模态视觉解析再纳入研究：AI_PM 模式用它对标岗位要求、定位能力缺口，通用模式用它补充研究素材。支持图片与 PDF。"
              />
            </div>
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading || streaming}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[12px] text-muted-foreground transition-all duration-200 ease-out hover:-translate-y-px hover:text-foreground hover:shadow-soft disabled:opacity-50"
            >
              <Upload className="size-3.5" />
              {uploading ? "上传中…" : "选择文件"}
            </button>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".pdf,image/*"
              onChange={(e) => handleFiles(e.target.files)}
              className="hidden"
            />
          </div>
          {chips.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {chips.map((c, i) => (
                <Badge key={i} tone={c.type === "pdf" ? "info" : "accent"}>
                  {c.name}
                </Badge>
              ))}
              <button
                onClick={clearFiles}
                aria-label="清除附件"
                className="text-[11px] text-muted-foreground underline-offset-2 hover:underline"
              >
                清除
              </button>
            </div>
          )}
          {uploadErr && <p className="text-[11px] text-destructive">{uploadErr}</p>}
        </div>

        <div className="flex flex-col gap-2.5 rounded-lg bg-zone-mint/40 px-3 py-3">
          <Toggle
            icon={<BarChart3 className="size-4" />}
            label="数据可视化"
            meta="Phase B"
            hint="Plotly 图表：从报告事实自动抽取、source_quote 防幻觉校验后渲染。"
            checked={enableViz}
            onChange={onEnableViz}
          />
          <Toggle
            icon={<PauseCircle className="size-4" />}
            label="计划确认 HITL"
            meta="plan 006"
            hint="检索前暂停，审查研究简报确认后再继续。"
            checked={enableHitl}
            onChange={onEnableHitl}
          />
          <Toggle
            icon={<ShieldCheck className="size-4" />}
            label="严格审计"
            hint="强制一次修订，演示评分前→后对比的提升。"
            checked={strictAudit}
            onChange={onStrictAudit}
          />
          <Toggle
            icon={<Database className="size-4" />}
            label="存入知识库"
            meta="KG"
            hint="本次研究写回知识库，构建跨会话的专属知识体系。"
            checked={enableKg}
            onChange={onEnableKg}
          />
          <Toggle
            icon={<Share2 className="size-4" />}
            label="导出知识图谱"
            hint="抽取实体+关系，可导入 Obsidian 看图谱。"
            checked={enableObsidian}
            onChange={onEnableObsidian}
          />
        </div>

        <div className="flex flex-col gap-1.5 rounded-lg border border-dashed border-border bg-zone-amber/40 px-3 py-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[12px] text-foreground">Obsidian 知识库</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowGuide((v) => !v)}
                className="text-[11px] text-muted-foreground underline-offset-2 hover:underline"
              >
                {showGuide ? "收起教程" : "导入教程"}
              </button>
              <a
                href={`${apiBase}/export-vault`}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[12px] text-muted-foreground transition-all duration-200 ease-out hover:-translate-y-px hover:text-foreground hover:shadow-soft"
              >
                <BookOpen className="size-3.5" />
                导出 zip
              </a>
            </div>
          </div>
          {showGuide && (
            <ol className="list-decimal space-y-0.5 pl-4 text-[11px] leading-relaxed text-muted-foreground">
              <li>开「导出知识图谱」开关后跑研究 → 点「导出 zip」下载并解压。</li>
              <li>Obsidian →「Open folder as vault」选该文件夹 → 点图谱视图即见知识图谱。</li>
            </ol>
          )}
        </div>

      </div>
    </Panel>
  );
}

function Toggle({
  icon,
  label,
  meta,
  hint,
  checked,
  onChange,
}: {
  icon?: React.ReactNode;
  label: string;
  meta?: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2.5">
        {icon && (
          <span
            className={cn(
              "flex size-7 shrink-0 items-center justify-center rounded-lg transition-colors duration-200",
              checked ? "bg-viz/10 text-viz" : "bg-card text-muted-foreground",
            )}
          >
            {icon}
          </span>
        )}
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="truncate text-[13px] font-medium text-foreground">{label}</span>
          {meta && <MetaChip>{meta}</MetaChip>}
          {hint && <InfoHint text={hint} />}
        </div>
      </div>
      <Switch checked={checked} onChange={onChange} label={label} />
    </div>
  );
}
