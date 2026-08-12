/**
 * =============================================================================
 * File: layout.tsx
 * Module/Service: Web App
 * Layer: UI
 * Purpose: Root layout — fonts + Scholarly Precision base styles.
 * Responsibilities:
 *   - Load Geist / Be Vietnam Pro / Source Serif 4 via next/font
 *   - Apply design-system CSS variables from globals.css
 * Dependencies:
 *   - next/font, app/globals.css
 * Public Exports:
 *   - default RootLayout
 * Database/Table: N/A
 * Related Modules: .cursor/rules/SKILL.md (typography)
 * Important Notes:
 *   - Do not invent fonts outside the design system.
 *   - suppressHydrationWarning on html/body only — do NOT MutationObserver-strip
 *     extension attrs (ColorZilla/MDL); that fights the extension and freezes the UI.
 * =============================================================================
 */

import type { Metadata } from "next";
import { Be_Vietnam_Pro, Geist, Geist_Mono, Source_Serif_4 } from "next/font/google";

import { ThemeBootstrap } from "@/features/settings/ThemeBootstrap";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const beVietnam = Be_Vietnam_Pro({
  variable: "--font-be-vietnam",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600"],
});

const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  weight: ["400", "600"],
});

export const metadata: Metadata = {
  title: "Enterprise NotebookLM",
  description:
    "Enterprise knowledge management with LLM + RAG — Auth & Workspace foundation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${beVietnam.variable} ${sourceSerif.variable} min-h-screen bg-base font-sans text-primary antialiased`}
        suppressHydrationWarning
      >
        <ThemeBootstrap />
        {children}
      </body>
    </html>
  );
}
