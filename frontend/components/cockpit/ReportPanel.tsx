import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText, Sparkles, Maximize2, Minimize2 } from "lucide-react";
import { Panel, Badge } from "./primitives";
import { MARKDOWN_COMPONENTS as MD } from "./markdown";

export function ReportPanel({
  report,
  revisionCount,
  modelUsed,
  onDownload,
  onDownloadMd,
  focus,
  onToggleFocus,
}: {
  report: string;
  revisionCount?: number;
  modelUsed?: string;
  onDownload?: () => void;   // 下载 .html 自包含存档
  onDownloadMd?: () => void; // 下载 .md 纯文本
  focus?: boolean;           // 专注阅读：侧栏收起、报告近全宽
  onToggleFocus?: () => void;
}) {
  const hint =
    revisionCount && revisionCount > 0 ? `修订 ${revisionCount} 轮 · 已过审` : "终稿";
  return (
    <Panel title="研究报告正文" icon={<FileText />} hint={hint} className="h-full">
      {report ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              {modelUsed && (
                <Badge tone="accent" mono>
                  DeepSeek 撰写
                </Badge>
              )}
              {revisionCount != null && revisionCount > 0 && (
                <Badge tone="success">按 critic 建议修订后定稿</Badge>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {onToggleFocus && (
                <button
                  onClick={onToggleFocus}
                  title={focus ? "退出专注阅读" : "专注阅读（侧栏收起、报告铺满）"}
                  aria-pressed={focus}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[12px] font-medium text-muted-foreground transition-all duration-200 ease-out hover:-translate-y-px hover:text-foreground hover:shadow-soft"
                >
                  {focus ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
                  {focus ? "退出专注" : "专注阅读"}
                </button>
              )}
            {(onDownload || onDownloadMd) && (
              <div className="flex shrink-0 items-center gap-0">
                {onDownload && (
                  <button
                    onClick={onDownload}
                    title="下载自包含 HTML（含 mermaid SVG + 数据图表，离线双击即看）"
                    className="rounded-l-md border border-viz/30 bg-viz/10 px-2.5 py-1 text-[12px] font-medium text-viz transition-colors hover:bg-viz/15"
                  >
                    下载 .html
                  </button>
                )}
                {onDownloadMd && (
                  <button
                    onClick={onDownloadMd}
                    title="下载 markdown 纯文本（便于粘贴到笔记/文档工具）"
                    className="rounded-r-md border border-l-0 border-viz/30 bg-viz/10 px-2.5 py-1 text-[12px] font-medium text-viz transition-colors hover:bg-viz/15"
                  >
                    .md
                  </button>
                )}
              </div>
            )}
            </div>
          </div>
          <article id="adrp-report-article" className="max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
              {report}
            </ReactMarkdown>
          </article>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-zone-sky text-viz">
            <Sparkles className="size-6" />
          </span>
          <p className="max-w-xs text-[13px] leading-relaxed text-muted-foreground">
            运行研究后，终稿正文将在此呈现——它正是上方评分卡所审计的对象。
          </p>
        </div>
      )}
    </Panel>
  );
}
