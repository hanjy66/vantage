// plan 019：把一次研究打包成自包含 HTML 存档（离线可看）。
// 报告正文直接取页面已渲染的 DOM（含 mermaid SVG），图表用后端自带 plotly.js 的 HTML 片段，
// 故不依赖任何 CDN / 新依赖，下载下来的单文件双击即可在浏览器看全貌。

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

const ARCHIVE_CSS = `
body{margin:0;background:#f7f7f5;color:#1a1a1a;line-height:1.7;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}
.doc{max-width:880px;margin:0 auto;padding:40px 24px;}
.meta{display:flex;justify-content:space-between;align-items:baseline;
  border-bottom:1px solid #ddd;padding-bottom:10px;margin-bottom:28px;color:#666;font-size:13px;}
.brand{font-weight:600;color:#1a1a1a;}
section{margin-bottom:30px;}
h1{font-size:24px;font-weight:700;margin:0 0 14px;}
h2{font-size:18px;font-weight:600;border-bottom:1px solid #e5e5e5;padding-bottom:6px;margin:26px 0 14px;}
h3{font-size:15px;font-weight:600;margin:18px 0 8px;}
p{margin:0 0 12px;}
.block{white-space:pre-wrap;background:#fff;border:1px solid #e5e5e5;border-radius:8px;
  padding:12px 14px;font-size:14px;margin:0;}
table{border-collapse:collapse;width:100%;font-size:13px;margin:0 0 14px;}
th,td{border:1px solid #ddd;padding:6px 10px;text-align:left;vertical-align:top;}
th{background:#f0f0ee;}
code{background:#efefec;padding:1px 5px;border-radius:4px;font-size:13px;}
pre{background:#f5f5f3;border:1px solid #e5e5e5;border-radius:6px;padding:12px;overflow-x:auto;}
a{color:#2563eb;}
blockquote{border-left:3px solid #ddd;margin:0 0 12px;padding-left:12px;color:#555;}
ul,ol{margin:0 0 12px;padding-left:22px;}
svg{max-width:100%;height:auto;}
.charts > *{margin-bottom:22px;}
`;

export function buildArchiveHtml(opts: {
  title?: string;
  query: string;
  brief?: string;
  reportHtml: string;
  chartHtmls: string[];
}): string {
  const { title, query, brief, reportHtml, chartHtmls } = opts;
  const date = new Date().toLocaleString("zh-CN");
  return `<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title || "ADRP 研究存档")}</title>
<style>${ARCHIVE_CSS}</style></head>
<body><main class="doc">
<header class="meta"><span class="brand">ADRP 研究存档</span><span>${esc(date)}</span></header>
<section><h2>研究主题</h2><pre class="block">${esc(query || "（无）")}</pre></section>
${brief ? `<section><h2>研究简报</h2><pre class="block">${esc(brief)}</pre></section>` : ""}
<section><h2>研究报告</h2><article class="report">${reportHtml}</article></section>
${chartHtmls.length ? `<section><h2>数据可视化</h2><div class="charts">${chartHtmls.join("\n")}</div></section>` : ""}
</main></body></html>`;
}

export function downloadHtml(filename: string, html: string): void {
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
