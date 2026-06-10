"use client";

// GSAP 统一封装（plan 021 步骤 3）：只服务 3 处「高级时刻」——
// 数字滚动 / 评分卡入场 / 时间线点亮。全部尊重 prefers-reduced-motion。
import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { PanelLeftOpen, PanelRightOpen } from "lucide-react";
import { cn } from "@/lib/utils";

gsap.registerPlugin(useGSAP);
gsap.defaults({ duration: 0.6, ease: "power2.out" });

// 系统「减少动态效果」开关：true 时所有动效降级为直接落终态
export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

// 数字滚动累加：从上一值平滑滚到新值；reduced-motion 直接落终值
export function CountUp({
  value,
  className,
  format = (n: number) => Math.round(n).toLocaleString(),
}: {
  value: number;
  className?: string;
  format?: (n: number) => string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const prev = useRef(value);
  const reduced = usePrefersReducedMotion();

  useGSAP(
    () => {
      const el = ref.current;
      if (!el) return;
      if (reduced) {
        el.textContent = format(value);
        prev.current = value;
        return;
      }
      const obj = { n: prev.current };
      gsap.to(obj, {
        n: value,
        duration: 0.8,
        ease: "power2.out",
        onUpdate: () => {
          el.textContent = format(obj.n);
        },
        onComplete: () => {
          prev.current = value;
        },
      });
    },
    { dependencies: [value, reduced] },
  );

  return (
    <span ref={ref} className={className}>
      {format(value)}
    </span>
  );
}

// 可折叠侧栏：GSAP 动 flex-basis/width 平滑收成细轨；内容固定宽避免回流，rail 叠加淡入。
// 仅桌面(lg)生效；移动端始终全宽展开。reduced-motion 直接切。
export function CollapsibleAside({
  side,
  expandedWidth,
  collapsed,
  onExpand,
  railIcon,
  railLabel,
  scrollable,
  stretch,
  children,
}: {
  side: "left" | "right";
  expandedWidth: number;
  collapsed: boolean;
  onExpand: () => void;
  railIcon: React.ReactNode;
  railLabel: string;
  scrollable?: boolean; // 内容超长时内部独立滚动（视口高封顶），避免与页面一起无限拖动
  stretch?: boolean;    // 侧栏跟中列等高（填满 flex 行高），避免 sticky 后底部漏灰
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);
  const first = useRef(true);
  const reduced = usePrefersReducedMotion();

  useGSAP(
    () => {
      const el = ref.current;
      if (!el || window.matchMedia("(max-width: 1023px)").matches) return; // 移动端不动
      const target = collapsed ? 56 : expandedWidth;
      if (first.current || reduced) {
        gsap.set(el, { flexBasis: target, width: target });
        first.current = false;
        return;
      }
      gsap.to(el, { flexBasis: target, width: target, duration: 0.5, ease: "power3.out" });
    },
    { dependencies: [collapsed, expandedWidth, reduced] },
  );

  const ExpandIcon = side === "left" ? PanelLeftOpen : PanelRightOpen;

  return (
    <aside
      ref={ref}
      style={{ flexBasis: expandedWidth, width: expandedWidth }}
      className="relative shrink-0 max-lg:!w-full max-lg:!basis-auto lg:sticky lg:top-3 lg:self-start"
    >
      <div
        style={scrollable ? undefined : { width: expandedWidth }}
        aria-hidden={collapsed}
        className={cn(
          "max-lg:!w-full",
          // stretch 模式：卡片撑成「视口高」而非容器高——保持 self-start + sticky 跟随滑动有效，
          // 同时白卡填满可视区，长报告滚动时左栏底部不漏灰（Panel h-full 接管这块高度）
          stretch && "lg:h-[calc(100dvh-1.5rem)]",
          // 内部滚动：视口高封顶 + y 轴可滚；x 轴裁切防横向滚动条（tooltip 用 align=start 不溢出）
          scrollable &&
            "lg:max-h-[calc(100dvh-1.5rem)] lg:w-full lg:overflow-y-auto lg:overflow-x-hidden lg:pr-0.5",
          collapsed && "pointer-events-none opacity-0 transition-opacity duration-150",
        )}
      >
        {children}
      </div>
      <button
        type="button"
        onClick={onExpand}
        aria-label={`展开「${railLabel}」`}
        className={cn(
          "absolute inset-0 hidden flex-col items-center gap-3 rounded-xl border border-border bg-card py-3 shadow-soft outline-none transition-opacity duration-300 hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring/40 lg:flex",
          collapsed ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      >
        <span className="flex size-7 items-center justify-center rounded-lg bg-viz/10 text-viz [&_svg]:size-4">
          {railIcon}
        </span>
        <span className="text-[11px] tracking-wide text-muted-foreground [writing-mode:vertical-rl]">
          {railLabel}
        </span>
        <ExpandIcon className="mt-auto size-4 text-muted-foreground/70" />
      </button>
    </aside>
  );
}

// 高级开关：thumb 用 GSAP power3.out 顺滑滑动 + 轻微 scale 弹一下（非 bounce）。
// reduced-motion 直接 set 终态。track h-6 w-11、thumb 20px 带柔阴影。
const SWITCH_TRAVEL = 20; // px：(44 track - 20 thumb - 2*2 inset)

export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  const thumbRef = useRef<HTMLSpanElement>(null);
  const reduced = usePrefersReducedMotion();

  useGSAP(
    () => {
      const el = thumbRef.current;
      if (!el) return;
      const x = checked ? SWITCH_TRAVEL : 0;
      if (reduced) {
        gsap.set(el, { x, scale: 1 });
        return;
      }
      gsap
        .timeline()
        .to(el, { x, duration: 0.32, ease: "power3.out" }, 0)
        .to(el, { scale: 1.14, duration: 0.11, ease: "power2.out" }, 0)
        .to(el, { scale: 1, duration: 0.2, ease: "power2.out" }, 0.11);
    },
    { dependencies: [checked, reduced] },
  );

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-6 w-11 shrink-0 cursor-pointer rounded-full border outline-none transition-colors duration-300 ease-out focus-visible:ring-2 focus-visible:ring-ring/40",
        checked ? "border-transparent bg-viz-gradient" : "border-border bg-secondary",
      )}
    >
      <span
        ref={thumbRef}
        className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-background shadow-[0_1px_3px_oklch(0.45_0.03_262_/_0.25)]"
        style={{ transform: `translateX(${checked ? SWITCH_TRAVEL : 0}px)` }}
      />
    </button>
  );
}
