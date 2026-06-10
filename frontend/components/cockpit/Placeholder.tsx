import { Hourglass } from "lucide-react";
import { Panel } from "./primitives";

// 优雅占位：展示架构而非空白（北极星：展示治理全貌）
export function Placeholder({
  title,
  desc,
  backend,
}: {
  title: string;
  desc: string;
  backend: string;
}) {
  return (
    <Panel title={title} icon={<Hourglass />} hint="即将上线" className="h-full">
      <div className="flex h-full flex-col justify-between gap-3">
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <span className="flex size-11 items-center justify-center rounded-2xl bg-zone-amber text-viz">
            <Hourglass className="size-5" />
          </span>
          <p className="max-w-xs text-[12px] leading-relaxed text-muted-foreground">{desc}</p>
        </div>
        <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          后端契约 · {backend}
        </p>
      </div>
    </Panel>
  );
}
