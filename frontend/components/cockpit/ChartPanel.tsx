import { BarChart3 } from "lucide-react";
import { Panel, Badge } from "./primitives";

// Plotly 图表（plan 009 Phase B）：chart_htmls 是含 <script> 的完整 HTML，
// dangerouslySetInnerHTML 不执行脚本，必须用 iframe srcDoc 渲染。
export function ChartPanel({ charts }: { charts: string[] }) {
  if (!charts || charts.length === 0) return null;
  return (
    <Panel title="数据可视化" icon={<BarChart3 />} hint={`Plotly · ${charts.length} 图`} className="h-full">
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <Badge tone="info" mono>
            Phase B
          </Badge>
          <span className="text-[12px] text-muted-foreground">
            从报告事实自动抽取、source_quote 防幻觉校验后渲染。
          </span>
        </div>
        {charts.map((html, i) => (
          <iframe
            key={i}
            srcDoc={html}
            title={`图表 ${i + 1}`}
            className="h-[420px] w-full rounded-lg border border-border bg-white"
            sandbox="allow-scripts"
          />
        ))}
      </div>
    </Panel>
  );
}
