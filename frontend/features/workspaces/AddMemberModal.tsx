/**
 * =============================================================================
 * File: AddMemberModal.tsx
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: Modal form to add a member to a workspace by user ID + role (UC10).
 * Responsibilities:
 *   - Validate UUID + role selection; surface API errors (403/404/409)
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - AddMemberModal
 * Database/Table: N/A
 * Related Modules: features/workspaces/WorkspaceMembersView
 * Important Notes: POST /workspaces/{id}/members requires user_id (UUID) per
 *   OpenAPI contract — there is no email-lookup endpoint yet, so the admin
 *   must already know the target user's ID (e.g. from an invite/onboarding
 *   flow outside this phase's scope).
 * =============================================================================
 */

"use client";

import { Loader2, X } from "lucide-react";
import { FormEvent, useEffect, useId, useState } from "react";

import { cn } from "@/lib/utils";
import type { WorkspaceRole } from "@/types/auth";

export type AddMemberFormValues = {
  userId: string;
  role: WorkspaceRole;
};

type Props = {
  open: boolean;
  submitting?: boolean;
  error?: string | null;
  onSubmit: (values: AddMemberFormValues) => void | Promise<void>;
  onClose: () => void;
};

const inputClass = cn(
  "h-11 w-full rounded-md border border-border-default bg-surface px-3",
  "text-body text-primary placeholder:text-tertiary",
  "outline-none transition-colors",
  "focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
);

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function AddMemberModal({
  open,
  submitting = false,
  error = null,
  onSubmit,
  onClose,
}: Props) {
  const titleId = useId();
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<WorkspaceRole>("viewer");
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (!open) return;
    setUserId("");
    setRole("viewer");
    setTouched(false);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !submitting) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, submitting, onClose]);

  if (!open) return null;

  const trimmedId = userId.trim();
  const isValidId = UUID_RE.test(trimmedId);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (!isValidId) return;
    await onSubmit({ userId: trimmedId, role });
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
            Thêm thành viên
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
            <label
              htmlFor="member-user-id"
              className="text-body-sm font-medium text-primary"
            >
              User ID (UUID) <span className="text-danger">*</span>
            </label>
            <input
              id="member-user-id"
              name="userId"
              required
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              onBlur={() => setTouched(true)}
              className={inputClass}
              placeholder="ví dụ: 8f14e45f-ceea-4c8a-b3b6-06c3f2c7e5a1"
              autoFocus
              autoComplete="off"
              spellCheck={false}
            />
            {touched && trimmedId && !isValidId ? (
              <p className="text-caption text-danger">
                User ID phải là UUID hợp lệ.
              </p>
            ) : (
              <p className="text-caption text-tertiary">
                Chưa có tính năng tìm user theo email — cần biết trước UUID của
                người dùng cần thêm.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="member-role"
              className="text-body-sm font-medium text-primary"
            >
              Vai trò
            </label>
            <select
              id="member-role"
              value={role}
              onChange={(e) => setRole(e.target.value as WorkspaceRole)}
              className={cn(inputClass, "cursor-pointer appearance-none")}
            >
              <option value="admin">Quản trị viên (admin)</option>
              <option value="editor">Biên tập viên (editor)</option>
              <option value="viewer">Người xem (viewer)</option>
            </select>
          </div>

          {error ? (
            <p
              role="alert"
              className="rounded-md bg-danger-soft px-3 py-2 text-body-sm text-danger"
            >
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
              disabled={submitting || !isValidId}
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
                  Đang thêm…
                </>
              ) : (
                "Thêm thành viên"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
