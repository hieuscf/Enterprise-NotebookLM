/**
 * =============================================================================
 * File: WorkspaceFormModal.tsx
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: Modal form to create or edit a workspace (name + description).
 * Responsibilities:
 *   - Validate required name; surface API errors (incl. 403)
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - WorkspaceFormModal
 * Database/Table: N/A
 * Related Modules: features/workspaces list/detail views
 * Important Notes: Parent owns submit handlers and revalidation after success.
 * =============================================================================
 */

"use client";

import { Loader2, X } from "lucide-react";
import { FormEvent, useEffect, useId, useState } from "react";

import { cn } from "@/lib/utils";

export type WorkspaceFormValues = {
  name: string;
  description: string;
};

type Props = {
  open: boolean;
  mode: "create" | "edit";
  initial?: WorkspaceFormValues;
  submitting?: boolean;
  error?: string | null;
  onSubmit: (values: WorkspaceFormValues) => void | Promise<void>;
  onClose: () => void;
};

const inputClass = cn(
  "h-11 w-full rounded-md border border-border-default bg-surface px-3",
  "text-body text-primary placeholder:text-tertiary",
  "outline-none transition-colors",
  "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
);

export function WorkspaceFormModal({
  open,
  mode,
  initial,
  submitting = false,
  error = null,
  onSubmit,
  onClose,
}: Props) {
  const titleId = useId();
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");

  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setDescription(initial?.description ?? "");
  }, [open, initial?.name, initial?.description]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, submitting, onClose]);

  if (!open) return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    await onSubmit({
      name: trimmed,
      description: description.trim(),
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Đóng hộp thoại"
        className="absolute inset-0 bg-primary/40"
        onClick={() => {
          if (!submitting) onClose();
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 w-full max-w-lg rounded-lg border border-border-default bg-surface p-6 shadow-lg"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id={titleId} className="text-h2 text-primary">
            {mode === "create" ? "Tạo Workspace mới" : "Sửa Workspace"}
          </h2>
          <button
            type="button"
            disabled={submitting}
            onClick={onClose}
            className="rounded-md p-1 text-tertiary hover:bg-elevated hover:text-primary disabled:opacity-50"
            aria-label="Đóng"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="ws-name" className="text-body-sm font-medium text-primary">
              Tên <span className="text-danger">*</span>
            </label>
            <input
              id="ws-name"
              name="name"
              required
              maxLength={255}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputClass}
              placeholder="Ví dụ: Phòng R&D"
              autoFocus
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="ws-description"
              className="text-body-sm font-medium text-primary"
            >
              Mô tả
            </label>
            <textarea
              id="ws-description"
              name="description"
              rows={3}
              maxLength={2000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className={cn(inputClass, "h-auto resize-y py-2.5")}
              placeholder="Mô tả ngắn về phòng ban / dự án (tuỳ chọn)"
            />
          </div>

          {error ? (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-body-sm text-danger">
              {error}
            </p>
          ) : null}

          <div className="mt-1 flex justify-end gap-2">
            <button
              type="button"
              disabled={submitting}
              onClick={onClose}
              className={cn(
                "h-10 rounded-md border border-border-default px-4",
                "text-body-sm font-medium text-secondary",
                "hover:bg-elevated hover:text-primary disabled:opacity-50",
              )}
            >
              Huỷ
            </button>
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className={cn(
                "flex h-10 items-center gap-2 rounded-md bg-accent-primary px-4",
                "text-body-sm font-medium text-white",
                "hover:bg-accent-primary-hover",
                "disabled:cursor-not-allowed disabled:opacity-60",
              )}
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                  Đang lưu…
                </>
              ) : mode === "create" ? (
                "Tạo Workspace"
              ) : (
                "Lưu thay đổi"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
