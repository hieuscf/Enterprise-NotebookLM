/**
 * =============================================================================
 * File: toast.tsx
 * Module/Service: Web App shell
 * Layer: UI
 * Purpose: Fixed-position stack rendering toasts from useToasts (FR2 upload
 *          errors first, reusable by any future feature).
 * Responsibilities:
 *   - Render error/success/info toasts with dismiss button
 * Dependencies:
 *   - lucide-react, lib/utils, hooks/useToasts
 * Public Exports:
 *   - ToastStack
 * Database/Table: N/A
 * Related Modules: hooks/useToasts, features/documents/DocumentUploadView
 * Important Notes: Hand-written (no Radix/sonner dependency) — matches the
 *   existing hand-rolled ConfirmDialog pattern in this repo.
 * =============================================================================
 */

"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Toast } from "@/hooks/useToasts";

const VARIANT_STYLES: Record<Toast["variant"], string> = {
  error: "border-danger/30 bg-danger-soft text-danger",
  success: "border-success/30 bg-elevated text-primary",
  info: "border-border-default bg-surface text-primary",
};

const VARIANT_ICON = {
  error: AlertCircle,
  success: CheckCircle2,
  info: Info,
} as const;

type Props = {
  toasts: Toast[];
  onDismiss: (id: string) => void;
};

export function ToastStack({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2"
    >
      {toasts.map((toast) => {
        const Icon = VARIANT_ICON[toast.variant];
        return (
          <div
            key={toast.id}
            role="alert"
            className={cn(
              "flex items-start gap-2.5 rounded-md border px-3.5 py-3 shadow-md",
              "text-body-sm",
              VARIANT_STYLES[toast.variant],
            )}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <p className="min-w-0 flex-1">{toast.message}</p>
            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              aria-label="Đóng thông báo"
              className="shrink-0 rounded p-0.5 opacity-70 hover:opacity-100"
            >
              <X className="h-3.5 w-3.5" aria-hidden />
            </button>
          </div>
        );
      })}
    </div>
  );
}
