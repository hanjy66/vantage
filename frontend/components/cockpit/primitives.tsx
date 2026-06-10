import { Info, PanelLeftOpen, PanelLeftClose, PanelRightClose } from "lucide-react";
import { cn } from "@/lib/utils";

// 分区面板：flat、1px 边框、微调色层叠（非重卡片、非侧色条）
export function Panel({
  title,
  hint,
  icon,
  onCollapse,
  collapseDir = "left",
  children,
  className,
}: {
  title?: string;
  hint?: string;
  icon?: React.ReactNode;
  onCollapse?: () => void; // 折叠侧栏（仅桌面显示）
  collapseDir?: "left" | "right";
  children: React.ReactNode;
  className?: string;
}) {
  const CollapseIcon = collapseDir === "right" ? PanelRightClose : PanelLeftClose;
  return (
    <section
      className={cn(
        "flex flex-col rounded-xl border border-border bg-card shadow-soft transition-shadow duration-200",
        className,
      )}
    >
      {title && (
        <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            {icon && (
              <span className="flex text-muted-foreground [&_svg]:size-[15px]">
                {icon}
              </span>
            )}
            <h2 className="truncate font-serif text-sm font-semibold tracking-tight text-foreground">
              {title}
            </h2>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {hint && (
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {hint}
              </span>
            )}
            {onCollapse && (
              <button
                type="button"
                onClick={onCollapse}
                aria-label="收起面板"
                title="收起面板"
                className="hidden rounded-md p-0.5 text-muted-foreground/70 outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/40 lg:inline-flex"
              >
                <CollapseIcon className="size-4" />
              </button>
            )}
          </div>
        </header>
      )}
      <div className="flex-1 p-4">{children}</div>
    </section>
  );
}

// 机器读数：等宽
export function Stat({
  label,
  value,
  className,
}: {
  label: string;
  value: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="font-mono text-sm text-foreground">{value}</span>
    </div>
  );
}

type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

const TONE: Record<Tone, string> = {
  neutral: "border-border bg-secondary text-secondary-foreground",
  accent: "border-viz/25 bg-viz/10 text-viz",
  success: "border-success/25 bg-success/10 text-success",
  warning: "border-warning/30 bg-warning/15 text-warning-foreground",
  danger: "border-destructive/25 bg-destructive/10 text-destructive",
  info: "border-info/25 bg-info/10 text-info",
};

export function Badge({
  children,
  tone = "neutral",
  mono,
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  mono?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
        mono && "font-mono",
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

// 机器元信息（Phase B / plan 006 / KG…）→ mono 小写 chip，与人类文字物理分开
export function MetaChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex shrink-0 items-center rounded-md border border-border/70 bg-secondary/70 px-1.5 py-px font-mono text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
      {children}
    </span>
  );
}

// 渐进披露：长帮助描述默认收成 ⓘ 点，hover/focus 才出。纯 CSS、键盘可达
export function InfoHint({
  text,
  align = "center",
}: {
  text: string;
  align?: "start" | "center" | "end";
}) {
  return (
    <span className="group/hint relative inline-flex shrink-0 leading-none">
      <button
        type="button"
        aria-label="说明"
        className="text-muted-foreground/55 outline-none transition-colors hover:text-muted-foreground focus-visible:text-muted-foreground"
      >
        <Info className="size-3.5" />
      </button>
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute top-full z-30 mt-1.5 w-56 rounded-lg border border-border bg-popover px-2.5 py-1.5 text-[11px] leading-snug text-muted-foreground opacity-0 shadow-raised transition-opacity duration-150 group-hover/hint:opacity-100 group-focus-within/hint:opacity-100",
          align === "end"
            ? "right-0"
            : align === "start"
              ? "left-0"
              : "left-1/2 -translate-x-1/2",
        )}
      >
        {text}
      </span>
    </span>
  );
}

// 专注阅读模式下，侧面板折成的细轨：竖排图标+名称，点击展开
export function CollapsedRail({
  icon,
  label,
  onExpand,
}: {
  icon: React.ReactNode;
  label: string;
  onExpand: () => void;
}) {
  return (
    <button
      onClick={onExpand}
      title={`展开「${label}」`}
      aria-label={`展开「${label}」`}
      className="flex h-full w-full flex-col items-center gap-3 rounded-xl border border-border bg-card py-3 shadow-soft outline-none transition-colors duration-200 hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring/40"
    >
      <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary [&_svg]:size-4">
        {icon}
      </span>
      <span className="text-[11px] tracking-wide text-muted-foreground [writing-mode:vertical-rl]">
        {label}
      </span>
      <PanelLeftOpen className="mt-auto size-4 shrink-0 text-muted-foreground/70" />
    </button>
  );
}

export function StatusDot({ status }: { status: "pending" | "running" | "done" }) {
  if (status === "running") {
    return (
      <span className="relative flex h-2.5 w-2.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-info opacity-60" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-info" />
      </span>
    );
  }
  return (
    <span
      className={cn(
        "h-2.5 w-2.5 rounded-full",
        status === "done" ? "bg-success" : "border border-border bg-transparent",
      )}
    />
  );
}
