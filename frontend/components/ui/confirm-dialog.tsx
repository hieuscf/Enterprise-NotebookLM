/**
 * =============================================================================
 * File: confirm-dialog.tsx
 * Module/Service: Web App shell
 * Layer: UI
 * Purpose: Accessible confirm dialog for consequential actions — destructive
 *          (delete/remove) or informational (e.g. rollback document version).
 * Responsibilities:
 *   - Require explicit confirm; show loading + error; Escape / backdrop cancel
 *   - `variant="danger"` (red, default) vs `variant="primary"` (teal, for
 *     non-destructive but consequential actions like Set current version)
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - ConfirmDialog
 * Database/Table: N/A
 * Related Modules: features/workspaces/WorkspaceDetailView, WorkspaceMembersView,
 *   features/documents/DocumentVersionHistory
 * Important Notes: Does not auto-close until parent sets open=false after success.
 *   Moved here from features/workspaces/ConfirmDialog.tsx (Part 2 of FE Documents
 *   work) since it is a shared primitive, not workspace-specific.
 * =============================================================================
 */

"use client";

import { AlertTriangle, Info, Loader2, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";

import { cn } from "@/lib/utils";

type Variant = "danger" | "primary";

type Props = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirming?: boolean;
  error?: string | null;
  variant?: Variant;
  onConfirm: () => void;
  onCancel: () => void;
};

const VARIANT_ICON_WRAP: Record<Variant, string> = {
  danger: "bg-danger-soft",
  primary: "bg-accent-primary-soft",
};

const VARIANT_ICON_COLOR: Record<Variant, string> = {
  danger: "text-danger",
  primary: "text-accent-primary",
};

const VARIANT_CONFIRM_BUTTON: Record<Variant, string> = {
  danger: "bg-danger hover:opacity-90",
  primary: "bg-accent-primary hover:bg-accent-primary-hover",
};

const VARIANT_CONFIRMING_LABEL: Record<Variant, string> = {
  danger: "Đang xoá…",
  primary: "Đang xử lý…",
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Xác nhận xoá",
  cancelLabel = "Huỷ",
  confirming = false,
  error = null,
  variant = "danger",
  onConfirm,
  onCancel,
}: Props) {
  const titleId = useId();
  const descId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const Icon = variant === "danger" ? AlertTriangle : Info;

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !confirming) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, confirming, onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Đóng hộp thoại"
        className="absolute inset-0 bg-primary/40"
        onClick={() => {
          if (!confirming) onCancel();
        }}
      />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="relative z-10 w-full max-w-md rounded-lg border border-border-default bg-surface p-6 shadow-lg"
      >
        <div className="flex items-start gap-3">
          <span
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-md",
              VARIANT_ICON_WRAP[variant],
            )}
          >
            <Icon className={cn("h-5 w-5", VARIANT_ICON_COLOR[variant])} aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-h3 text-primary">
              {title}
            </h2>
            <p id={descId} className="mt-2 text-body-sm text-secondary">
              {description}
            </p>
          </div>
          <button
            type="button"
            ref={cancelRef}
            disabled={confirming}
            onClick={onCancel}
            className="rounded-md p-1 text-tertiary hover:bg-elevated hover:text-primary disabled:opacity-50"
            aria-label="Đóng"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        {error ? (
          <p role="alert" className="mt-4 rounded-md bg-danger-soft px-3 py-2 text-body-sm text-danger">
            {error}
          </p>
        ) : null}

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            disabled={confirming}
            onClick={onCancel}
            className={cn(
              "h-10 rounded-md border border-border-default px-4",
              "text-body-sm font-medium text-secondary",
              "hover:bg-elevated hover:text-primary disabled:opacity-50",
            )}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            disabled={confirming}
            onClick={onConfirm}
            className={cn(
              "flex h-10 items-center gap-2 rounded-md px-4",
              "text-body-sm font-medium text-white",
              "disabled:cursor-not-allowed disabled:opacity-60",
              VARIANT_CONFIRM_BUTTON[variant],
            )}
          >
            {confirming ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                {VARIANT_CONFIRMING_LABEL[variant]}
              </>
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
