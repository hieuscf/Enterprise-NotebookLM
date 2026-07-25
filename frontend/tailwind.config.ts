/**
 * Enterprise NotebookLM — tailwind.config.ts
 * Map các CSS variables trong tokens.css sang theme Tailwind, cho phép dùng:
 *   bg-surface, text-primary, text-citation, border-strong, rounded-lg,
 *   shadow-sm, font-serif, text-h1, ...
 *
 * BẮT BUỘC: import/merge file tokens.css trước (globals.css) để các biến
 * --bg-surface, --text-primary, ... tồn tại trong :root / .dark.
 *
 * Next.js font setup gợi ý (app/layout.tsx):
 *
 *   import { GeistSans } from "geist/font/sans";
 *   import { GeistMono } from "geist/font/mono";
 *   import { Source_Serif_4, Be_Vietnam_Pro } from "next/font/google";
 *
 *   const sourceSerif = Source_Serif_4({ subsets: ["latin"], variable: "--font-serif-loaded" });
 *   const beVietnam = Be_Vietnam_Pro({
 *     subsets: ["latin", "vietnamese"],
 *     weight: ["400", "500", "600"],
 *     variable: "--font-vi-loaded",
 *   });
 *
 *   // gắn className={`${GeistSans.variable} ${GeistMono.variable} ${sourceSerif.variable} ${beVietnam.variable}`}
 *   // lên thẻ <html> hoặc <body>, rồi để var(--font-sans) trong tokens.css trỏ tới các biến loaded này
 *   // nếu muốn dùng font thật thay vì chỉ fallback hệ thống.
 */

import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class", // khớp với `.dark` trong tokens.css
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./features/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Neutrals / nền
        base: "var(--bg-base)",
        surface: "var(--bg-surface)",
        elevated: "var(--bg-elevated)",
        inset: "var(--bg-inset)",

        // Text
        primary: "var(--text-primary)",
        secondary: "var(--text-secondary)",
        tertiary: "var(--text-tertiary)",

        // Border
        "border-default": "var(--border-default)",
        "border-strong": "var(--border-strong)",

        // Accent — AI & tương tác
        "accent-primary": "var(--accent-primary)",
        "accent-primary-soft": "var(--accent-primary-soft)",
        "accent-primary-hover": "var(--accent-primary-hover)",
        "accent-secondary": "var(--accent-secondary)",
        "accent-tertiary": "var(--accent-tertiary)",

        // Semantic
        citation: "var(--citation)",
        "citation-soft": "var(--citation-soft)",
        success: "var(--success)",
        warning: "var(--warning)",
        danger: "var(--danger)",
        info: "var(--info)",

        // Document-specific
        "doc-bg": "var(--doc-bg)",
        "doc-text": "var(--doc-text)",
        "highlight-search": "var(--highlight-search)",
        "highlight-citation": "var(--highlight-citation)",
      },
      spacing: {
        1: "var(--space-1)",
        2: "var(--space-2)",
        3: "var(--space-3)",
        4: "var(--space-4)",
        5: "var(--space-5)",
        6: "var(--space-6)",
        8: "var(--space-8)",
        10: "var(--space-10)",
        12: "var(--space-12)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        full: "var(--radius-full)",
      },
      boxShadow: {
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        serif: ["var(--font-serif)"],
        mono: ["var(--font-mono)"],
      },
      fontSize: {
        display: ["var(--text-display)", { lineHeight: "1.2", fontWeight: "600" }],
        h1: ["var(--text-h1)", { lineHeight: "1.3", fontWeight: "600" }],
        h2: ["var(--text-h2)", { lineHeight: "1.35", fontWeight: "600" }],
        h3: ["var(--text-h3)", { lineHeight: "1.4", fontWeight: "600" }],
        body: ["var(--text-body)", { lineHeight: "1.6" }],
        "body-sm": ["var(--text-body-sm)", { lineHeight: "1.5" }],
        caption: ["var(--text-caption)", { lineHeight: "1.4", fontWeight: "500" }],
        mono: ["var(--text-mono)", { lineHeight: "1.5" }],
      },
    },
  },
  plugins: [],
};

export default config;