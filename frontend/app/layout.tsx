import type { Metadata } from "next";
import { Geist, Geist_Mono, Source_Serif_4, Noto_Sans_SC } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

// 中文正文高质量字体（思源黑体）：拉丁/数字仍走 Geist，中文交给它，根治小字毛坯
const notoSansSC = Noto_Sans_SC({
  variable: "--font-noto-sc",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  preload: false,
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// editorial 衬线（拉丁字形 + 数字）；中文走系统衬线兜底（见 globals.css --font-serif 栈）
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  weight: ["400", "600"],
});

export const metadata: Metadata = {
  title: "Vantage — Multi-field Agentic Deep Research Platform",
  description: "多领域 Agentic 深度研究平台 — 控制、审计、修订、评估一次深度研究",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      className={`${geistSans.variable} ${geistMono.variable} ${sourceSerif.variable} ${notoSansSC.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
