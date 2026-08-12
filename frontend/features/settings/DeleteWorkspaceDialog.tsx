/**
 * =============================================================================
 * File: DeleteWorkspaceDialog.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Destructive Workspace delete confirmation requiring exact name match.
 * Responsibilities:
 *   - Require typing the Workspace name before enabling Delete
 *   - Surface API errors; Escape / backdrop cancel while not submitting
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - DeleteWorkspaceDialog
 * Database/Table: N/A
 * Related Modules: features/settings/pages/WorkspaceSettings.tsx
 * Important Notes: Never deletes on a single click — name confirmation required.
 * =============================================================================
 */

"use client";

import { AlertTriangle, Loader2, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { cn } from "@/lib/utils";

type Props = {
  open: boolean;
  workspaceName: string;
  confirming?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
};

export function DeleteWorkspaceDialog({
  open,
  workspaceName,
  confirming = false,
  error = null,
  onConfirm,
  onCancel,
}: Props) {
  const titleId = useId();
  const descId = useId();
  const inputId = useId();
  const [typed, setTyped] = useState("");

  useEffect(() => {
    if (!open) return;
    setTyped("");
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !confirming) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, confirming, onCancel]);

  if (!open) return null;

  const matches = typed.trim() === workspaceName;

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
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-danger-soft">
            <AlertTriangle className="h-5 w-5 text-danger" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-h3 text-primary">
              Xoá Workspace?
            </h2>
            <p id={descId} className="mt-2 text-body-sm text-secondary">
              Thao tác này sẽ xoá vĩnh viễn Workspace và dữ liệu liên quan. Nhập
              chính xác tên Workspace để xác nhận.
            </p>
          </div>
          <button
            type="button"
            disabled={confirming}
            onClick={onCancel}
            className="rounded-md p-1 text-tertiary hover:bg-elevated hover:text-primary disabled:opacity-50"
            aria-label="Đóng"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <div className="mt-4 flex flex-col gap-1.5">
          <label htmlFor={inputId} className="text-body-sm font-medium text-primary">
            Tên Workspace
          </label>
          <input
            id={inputId}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            disabled={confirming}
            placeholder={workspaceName}
            autoComplete="off"
            spellCheck={false}
            className={cn(
              "h-11 w-full rounded-md border border-border-default bg-surface px-3",
              "text-body text-primary outline-none",
              "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
              "disabled:opacity-60",
            )}
          />
        </div>

        {error ? (
          <p
            role="alert"
            className="mt-4 rounded-md bg-danger-soft px-3 py-2 text-body-sm text-danger"
          >
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
            Huỷ
          </button>
          <button
            type="button"
            disabled={confirming || !matches}
            onClick={onConfirm}
            className={cn(
              "flex h-10 items-center gap-2 rounded-md bg-danger px-4",
              "text-body-sm font-medium text-white hover:opacity-90",
              "disabled:cursor-not-allowed disabled:opacity-60",
            )}
          >
            {confirming ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Đang xoá…
              </>
            ) : (
              "Xoá Workspace"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
