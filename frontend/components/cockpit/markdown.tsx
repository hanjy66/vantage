import type { Components } from "react-markdown";
import { MermaidBlock } from "./MermaidBlock";

// 共享 markdown 渲染配置：研究报告正文 + 历史研究回看 复用同一套排版。
// 社论衬线标题 + 克制正文 + mermaid 代码块 → SVG + 可点击链接。
export const MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => (
    <h1 className="mb-3 mt-1 font-serif text-xl font-semibold tracking-tight text-foreground">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-5 border-b border-border pb-1 font-serif text-base font-semibold tracking-tight text-foreground">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-1.5 mt-4 font-serif text-sm font-semibold text-foreground">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="mb-3 text-[13px] leading-relaxed text-foreground/90">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="mb-3 list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-foreground/90">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 list-decimal space-y-1 pl-5 text-[13px] leading-relaxed text-foreground/90">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="marker:text-muted-foreground">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-viz underline underline-offset-2">
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto rounded-md border border-border">
      <table className="w-full border-collapse text-[12px]">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-secondary/60">{children}</thead>,
  th: ({ children }) => (
    <th className="border-b border-border px-3 py-1.5 text-left font-medium text-foreground">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-border px-3 py-1.5 text-foreground/90">{children}</td>
  ),
  pre: ({ children }) => <>{children}</>,
  code: ({ className, children }) => {
    const text = String(children ?? "");
    if (className?.includes("language-mermaid")) {
      return <MermaidBlock code={text.replace(/\n$/, "")} />;
    }
    if (className?.startsWith("language-")) {
      return (
        <pre className="mb-3 overflow-x-auto rounded-md border border-border bg-secondary/50 p-3">
          <code className="font-mono text-[11px] text-foreground">{children}</code>
        </pre>
      );
    }
    return (
      <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[11px] text-foreground">
        {children}
      </code>
    );
  },
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-2 border-border pl-3 text-[13px] italic text-muted-foreground">
      {children}
    </blockquote>
  ),
};
