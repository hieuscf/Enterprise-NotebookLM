/**
 * =============================================================================
 * File: page.tsx (/login)
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Login page — Scholarly Precision branded split-screen auth entry.
 * Responsibilities:
 *   - Left: brand panel (teal gradient + product highlights, hidden on mobile)
 *   - Right: LoginForm card
 * Dependencies:
 *   - features/auth/LoginForm
 * Public Exports:
 *   - default page
 * Database/Table: N/A
 * Related Modules: middleware.ts, .cursor/rules/SKILL.md
 * Important Notes: Public route; brand accent = teal (accent-primary). Tokens only.
 * =============================================================================
 */

import { BookOpenCheck, MessagesSquare, ShieldCheck, Sparkles } from "lucide-react";
import { Suspense } from "react";

import { LoginForm } from "@/features/auth/LoginForm";

const highlights = [
  {
    icon: MessagesSquare,
    title: "AI Chat có trích dẫn",
    description: "Mọi câu trả lời đều dẫn nguồn rõ ràng, kiểm tra được ngay trong tài liệu gốc.",
  },
  {
    icon: BookOpenCheck,
    title: "Knowledge Base tập trung",
    description: "Tài liệu, phiên bản và pipeline xử lý được quản lý xuyên suốt Workspace.",
  },
  {
    icon: ShieldCheck,
    title: "Bảo mật theo Workspace",
    description: "Xác thực JWT và phân quyền admin / editor / viewer cho từng Workspace.",
  },
];

export default function LoginPage() {
  return (
    <main className="flex min-h-screen bg-base">
      {/* Left — brand panel */}
      <div className="relative hidden w-1/2 overflow-hidden bg-accent-primary lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(circle at 15% 20%, rgba(255,255,255,0.16), transparent 40%), radial-gradient(circle at 85% 0%, rgba(139,92,246,0.35), transparent 45%), radial-gradient(circle at 75% 90%, rgba(99,102,241,0.30), transparent 45%)",
          }}
        />

        <div className="relative z-10 flex items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-white/15">
            <Sparkles className="h-5 w-5 text-white" aria-hidden />
          </span>
          <span className="text-h3 font-semibold text-white">
            NotebookLM <span className="text-white/70">Enterprise</span>
          </span>
        </div>

        <div className="relative z-10 flex flex-col gap-8">
          <div className="flex flex-col gap-3">
            <h2 className="text-display text-white">
              Tri thức doanh nghiệp,
              <br />
              có kiểm chứng.
            </h2>
            <p className="max-w-md text-body text-white/80">
              Tập trung tài liệu, tìm kiếm ngữ nghĩa và trò chuyện với AI —
              mọi câu trả lời đều truy xuất được nguồn gốc.
            </p>
          </div>

          <ul className="flex flex-col gap-5">
            {highlights.map(({ icon: Icon, title, description }) => (
              <li key={title} className="flex items-start gap-3">
                <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-white/15">
                  <Icon className="h-[18px] w-[18px] text-white" aria-hidden />
                </span>
                <div className="flex flex-col gap-0.5">
                  <p className="text-body-sm font-semibold text-white">{title}</p>
                  <p className="text-body-sm text-white/75">{description}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative z-10 text-caption text-white/60">
          © {new Date().getFullYear()} Enterprise NotebookLM — Nền tảng RAG nội bộ.
        </p>
      </div>

      {/* Right — login form */}
      <div className="flex w-full flex-col items-center justify-center px-6 py-12 lg:w-1/2">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex flex-col gap-2 lg:hidden">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-accent-primary-soft">
                <Sparkles className="h-4 w-4 text-accent-primary" aria-hidden />
              </span>
              <span className="text-h3 font-semibold text-primary">
                NotebookLM <span className="text-secondary">Enterprise</span>
              </span>
            </div>
          </div>

          <div className="mb-8 flex flex-col gap-2">
            <h1 className="text-h1 text-primary">Chào mừng trở lại</h1>
            <p className="text-body-sm text-secondary">
              Đăng nhập để truy cập knowledge base và AI tools theo quyền
              Workspace của bạn.
            </p>
          </div>

          <div className="rounded-lg border border-border-default bg-surface p-6 shadow-sm sm:p-8">
            <Suspense
              fallback={<p className="text-body-sm text-tertiary">Đang tải…</p>}
            >
              <LoginForm />
            </Suspense>
          </div>

          <p className="mt-6 text-center text-caption text-tertiary">
            Cần trợ giúp truy cập? Liên hệ quản trị viên Workspace của bạn.
          </p>
        </div>
      </div>
    </main>
  );
}
