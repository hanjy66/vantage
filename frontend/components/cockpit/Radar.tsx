// 纯 SVG 雷达图，无图表库依赖。scores 0-10。可叠加 before/after 两层。

interface Series {
  values: number[];
  className: string; // stroke/fill 用 currentColor，外部传 text-* 控制色
}

export function Radar({
  axes,
  series,
  max = 10,
  size = 180,
}: {
  axes: string[];
  series: Series[];
  max?: number;
  size?: number;
}) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 26;
  const n = axes.length;

  const point = (i: number, value: number) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const rad = (value / max) * r;
    return [cx + rad * Math.cos(angle), cy + rad * Math.sin(angle)];
  };

  const polygon = (values: number[]) =>
    values.map((v, i) => point(i, v).join(",")).join(" ");

  const rings = [0.25, 0.5, 0.75, 1];

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="overflow-visible">
      {rings.map((t) => (
        <polygon
          key={t}
          points={axes.map((_, i) => point(i, max * t).join(",")).join(" ")}
          className="fill-none stroke-border"
          strokeWidth={1}
        />
      ))}
      {axes.map((_, i) => {
        const [x, y] = point(i, max);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} className="stroke-border" strokeWidth={1} />;
      })}
      {series.map((s, idx) => (
        <polygon
          key={idx}
          points={polygon(s.values)}
          className={s.className}
          strokeWidth={1.5}
        />
      ))}
      {axes.map((label, i) => {
        const [x, y] = point(i, max + 1.6);
        return (
          <text
            key={label}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            className="fill-muted-foreground text-[9px]"
          >
            {label}
          </text>
        );
      })}
    </svg>
  );
}
