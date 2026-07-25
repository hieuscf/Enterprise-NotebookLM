/**
 * =============================================================================
 * File: LoginForm.tsx
 * Module/Service: Auth (Web App)
 * Layer: UI
 * Purpose: Email/password login form (Scholarly Precision design system).
 * Responsibilities:
 *   - Submit credentials to BFF /api/auth/login
 *   - Show clear 401 error; redirect on success
 *   - Icon inputs + show/hide password + loading state
 * Dependencies:
 *   - lib/api-client.authLogin, lib/utils.cn, lucide-react
 * Public Exports:
 *   - LoginForm
 * Database/Table: N/A
 * Related Modules: app/login/page.tsx, .cursor/rules/SKILL.md
 * Important Notes: Use design tokens only — no ad-hoc hex colors.
 * =============================================================================
 */

"use client";

import { AlertCircle, Eye, EyeOff, Loader2, Lock, LogIn, Mail } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";

import { authLogin } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const inputBaseClass = cn(
  "h-11 w-full rounded-md border border-border-default bg-surface pl-10 pr-3",
  "text-body text-primary placeholder:text-tertiary",
  "outline-none transition-colors",
  "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
);

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = searchParams.get("next") || "/workspaces";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const result = await authLogin(email.trim(), password);
    setSubmitting(false);

    if (!result.ok) {
      setError(result.message);
      return;
    }

    router.replace(nextPath.startsWith("/") ? nextPath : "/");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="flex w-full flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className="text-body-sm font-medium text-primary">
          Email
        </label>
        <div className="relative">
          <Mail
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
            aria-hidden
          />
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputBaseClass}
            placeholder="ban@congty.com"
          />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <label htmlFor="password" className="text-body-sm font-medium text-primary">
            Mật khẩu
          </label>
        </div>
        <div className="relative">
          <Lock
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
            aria-hidden
          />
          <input
            id="password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={cn(inputBaseClass, "pr-10")}
            placeholder="••••••••"
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-tertiary transition-colors hover:text-secondary"
          >
            {showPassword ? (
              <EyeOff className="h-4 w-4" aria-hidden />
            ) : (
              <Eye className="h-4 w-4" aria-hidden />
            )}
          </button>
        </div>
      </div>

      {error ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2.5 text-body-sm text-danger"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{error}</span>
        </div>
      ) : null}

      <button
        type="submit"
        disabled={submitting}
        className={cn(
          "mt-1 flex h-11 items-center justify-center gap-2 rounded-md bg-accent-primary",
          "text-body font-medium text-white shadow-xs",
          "transition-colors hover:bg-accent-primary-hover",
          "disabled:cursor-not-allowed disabled:opacity-60",
        )}
      >
        {submitting ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Đang đăng nhập…
          </>
        ) : (
          <>
            <LogIn className="h-4 w-4" aria-hidden />
            Đăng nhập
          </>
        )}
      </button>
    </form>
  );
}
