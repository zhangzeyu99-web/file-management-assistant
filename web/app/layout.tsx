import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "个人知识工作台 · Obsidian",
  description: "找回以前的做法，带着已有的积累继续工作。",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">{children}</body>
    </html>
  );
}
