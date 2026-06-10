"use client";

import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

// 面试模式技术架构图：把报告里的 ```mermaid 代码块渲染成 SVG。
// 渲染失败（模型偶尔吐错语法）时回退显示原始代码，绝不白屏/崩溃。
let initialized = false;

// 清洗模型常见的语法瑕疵，避免 mermaid 直接 Syntax error：
//  1) 箭头写成单字符 →（unicode）或单破折号 ->
//  2) 节点方括号标签里含 / : % & ( ) \ 等特殊字符——mermaid 要求这类标签必须加引号，
//     否则解析失败。这里统一把 [label] 自动改写成 ["label"] 并清掉转义反斜杠。
//  3) 全角/中文标点（：｜（）等）在 mermaid 11 strict 模式下即使在引号内也会报错，
//     统一替换为对应 ASCII 字符。
//  4) 标签内不平衡的括号（如多余的 ) ）会触发 mermaid 解析器崩溃，清除多余字符。
function sanitizeMermaid(code: string): string {
  let s = code
    .replace(/--&gt;/g, "-->") // html 转义还原
    .replace(/[→⟶➔➜⮕⭢⭮⇾]/g, "-->") // 各类 unicode 箭头 → -->
    .replace(/(^|[^-<|.])->(?!>)/g, "$1-->") // 单破折号箭头 -> 补成 -->
    .trim();
  // 给方括号节点标签自动加引号，兼容含特殊字符（/ : % & ( ) 等）的标签。
  s = s.replace(/\[([^\[\]\n]*)\]/g, (_m, label: string) => {
    let cleaned = label
      .replace(/\\/g, "") // 去转义反斜杠，如 \&
      .replace(/"/g, "") // 去内部引号，避免冲突
      .replace(/[（）]/g, (m) => (m === "（" ? "(" : ")")) // 全角括号→半角
      .replace(/：/g, ":") // 全角冒号→半角（mermaid 11 strict 不接受全角冒号）
      .replace(/｜/g, "|") // 全角竖线→半角
      .replace(/，/g, ",") // 全角逗号→半角
      .replace(/。/g, ".") // 中文句号→半角（可选，保留中文字符不影响解析）
      .trim();
    // 清除标签内不平衡的右括号（如模型吐出 "API商业化)" 多了一个 )）
    // 注意：String.replace 回调的第三参数是原始输入串，必须直接操作 cleaned
    const openCount = (cleaned.match(/\(/g) || []).length;
    const closeCount = (cleaned.match(/\)/g) || []).length;
    if (closeCount > openCount) {
      let excess = closeCount - openCount;
      cleaned = cleaned.replace(/\)/g, (ch) => {
        if (excess > 0) { excess--; return ""; }
        return ch;
      });
    }
    return `["${cleaned}"]`;
  });
  return s;
}

export function MermaidBlock({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(false); // code 变化时重置，避免上一张图失败态卡住这一张
    if (!initialized) {
      mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
      initialized = true;
    }
    const sanitized = sanitizeMermaid(code);
    const id = "mmd-" + Math.random().toString(36).slice(2);

    // 确定性复杂度闸门：subgraph 子图 / 过多边 在窄面板里会渲染成一团乱麻（即便语法合法）。
    // 这类直接退回原码块（可读）而非硬渲染成糊图——宁可朴素也不要乱。
    const edgeCount = (sanitized.match(/-->/g) || []).length;
    const tooComplex = /\bsubgraph\b/.test(sanitized) || edgeCount > 12;
    if (tooComplex) {
      setError(true);
      return;
    }

    (async () => {
      // mermaid v11 的 render() 在解析失败时不会 reject，而是把 bomb SVG 注入 DOM
      // 并 resolve，导致 .catch() 永远不触发。必须先用 parse() 显式校验语法。
      let parseOk = false;
      try {
        const result = await mermaid.parse(sanitized, { suppressErrors: true });
        parseOk = result !== false;
      } catch {
        parseOk = false;
      }
      if (!parseOk) {
        if (!cancelled) setError(true);
        return;
      }
      try {
        const { svg } = await mermaid.render(id, sanitized);
        if (!cancelled && ref.current) ref.current.innerHTML = svg;
      } catch {
        if (!cancelled) setError(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code]);

  if (error) {
    return (
      <pre className="mb-3 overflow-x-auto rounded-md border border-border bg-secondary/50 p-3">
        <code className="font-mono text-[11px] text-foreground">{code}</code>
      </pre>
    );
  }

  return (
    <div
      ref={ref}
      className="my-3 flex justify-center overflow-x-auto rounded-md border border-border bg-card p-3"
    />
  );
}
