/**
 * =============================================================================
 * File: AddMemberModal.tsx
 * Module/Service: Workspace Service (Web App)
 * Layer: UI
 * Purpose: Modal to invite a member by searching name/email or picking from
 *          the candidate directory (UC10).
 * Responsibilities:
 *   - Debounced GET .../member-candidates; select a user; choose role
 *   - Fall back to exact email invite when no list match is selected
 * Dependencies:
 *   - lucide-react, lib/api-client.listWorkspaceMemberCandidates, lib/utils
 * Public Exports:
 *   - AddMemberModal, type AddMemberFormValues
 * Database/Table: N/A
 * Related Modules: features/workspaces/WorkspaceMembersView
 * Important Notes: POST still sends user_id (preferred) or email — never asks
 *   the admin to paste a raw UUID.
 * =============================================================================
 */

"use client";

import { Loader2, Search, UserRound, X } from "lucide-react";
import { FormEvent, useEffect, useId, useState } from "react";

import {
  ApiClientError,
  listWorkspaceMemberCandidates,
} from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { WorkspaceRole } from "@/types/auth";
import type { MemberCandidate } from "@/types/workspaces";

export type AddMemberFormValues = {
  userId?: string;
  email?: string;
  role: WorkspaceRole;
};

type Props = {
  open: boolean;
  workspaceId: string;
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

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function initialsOf(name: string, email: string): string {
  const trimmed = name.trim();
  if (trimmed) {
    return trimmed
      .split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() ?? "")
      .join("");
  }
  return email.trim()[0]?.toUpperCase() ?? "?";
}

export function AddMemberModal({
  open,
  workspaceId,
  submitting = false,
  error = null,
  onSubmit,
  onClose,
}: Props) {
  const titleId = useId();
  const listId = useId();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [role, setRole] = useState<WorkspaceRole>("viewer");
  const [selected, setSelected] = useState<MemberCandidate | null>(null);
  const [candidates, setCandidates] = useState<MemberCandidate[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setDebouncedQuery("");
    setRole("viewer");
    setSelected(null);
    setCandidates([]);
    setSearchError(null);
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

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  useEffect(() => {
    if (!open || !workspaceId) return;
    let cancelled = false;
    setLoadingCandidates(true);
    setSearchError(null);
    void (async () => {
      try {
        const rows = await listWorkspaceMemberCandidates(workspaceId, {
          q: debouncedQuery,
          limit: 20,
        });
        if (!cancelled) setCandidates(rows);
      } catch (err) {
        if (!cancelled) {
          setCandidates([]);
          setSearchError(
            err instanceof ApiClientError
              ? err.message
              : "Không tải được danh sách người dùng.",
          );
        }
      } finally {
        if (!cancelled) setLoadingCandidates(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, workspaceId, debouncedQuery]);

  if (!open) return null;

  const trimmedQuery = query.trim();
  const canSubmit =
    selected !== null || EMAIL_RE.test(trimmedQuery);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (selected) {
      await onSubmit({
        userId: selected.user_id,
        email: selected.email,
        role,
      });
      return;
    }
    if (!EMAIL_RE.test(trimmedQuery)) return;
    await onSubmit({ email: trimmedQuery, role });
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
        className="relative z-10 flex w-full max-w-lg flex-col rounded-lg border border-border-default bg-surface shadow-lg"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border-default px-6 py-4">
          <div>
            <h2 id={titleId} className="text-h2 text-primary">
              Thêm thành viên
            </h2>
            <p className="mt-0.5 text-caption text-tertiary">
              Tìm theo tên hoặc email, rồi chọn người dùng từ danh sách.
            </p>
          </div>
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

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-6 py-5">
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="member-search"
              className="text-body-sm font-medium text-primary"
            >
              Tìm người dùng <span className="text-danger">*</span>
            </label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
                aria-hidden
              />
              <input
                id="member-search"
                name="query"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setSelected(null);
                }}
                onBlur={() => setTouched(true)}
                className={cn(inputClass, "pl-9")}
                placeholder="Nhập tên hoặc email…"
                autoFocus
                autoComplete="off"
                spellCheck={false}
                role="combobox"
                aria-expanded={candidates.length > 0}
                aria-controls={listId}
                aria-autocomplete="list"
              />
            </div>

            {selected ? (
              <div className="flex items-center gap-2 rounded-md border border-accent-primary/30 bg-accent-primary-soft/40 px-3 py-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-primary-soft text-caption font-semibold text-accent-primary">
                  {initialsOf(selected.full_name, selected.email)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-body-sm font-medium text-primary">
                    {selected.full_name || selected.email}
                  </p>
                  <p className="truncate text-caption text-tertiary">
                    {selected.email}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  className="text-caption font-medium text-secondary hover:text-primary"
                >
                  Đổi
                </button>
              </div>
            ) : (
              <div
                id={listId}
                role="listbox"
                aria-label="Kết quả tìm kiếm"
                className="max-h-52 overflow-y-auto rounded-md border border-border-default"
              >
                {loadingCandidates ? (
                  <div className="flex items-center gap-2 px-3 py-4 text-body-sm text-tertiary">
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    Đang tìm…
                  </div>
                ) : searchError ? (
                  <p className="px-3 py-4 text-body-sm text-danger">{searchError}</p>
                ) : candidates.length === 0 ? (
                  <div className="flex flex-col gap-1 px-3 py-4 text-body-sm text-secondary">
                    <span className="flex items-center gap-2">
                      <UserRound className="h-4 w-4 text-tertiary" aria-hidden />
                      Không có kết quả phù hợp.
                    </span>
                    {EMAIL_RE.test(trimmedQuery) ? (
                      <span className="text-caption text-tertiary">
                        Có thể mời trực tiếp bằng email này nếu tài khoản đã tồn tại.
                      </span>
                    ) : (
                      <span className="text-caption text-tertiary">
                        Thử tên đầy đủ hoặc địa chỉ email.
                      </span>
                    )}
                  </div>
                ) : (
                  <ul className="divide-y divide-border-default">
                    {candidates.map((c) => (
                      <li key={c.user_id}>
                        <button
                          type="button"
                          role="option"
                          aria-selected={false}
                          onClick={() => {
                            setSelected(c);
                            setQuery(c.full_name || c.email);
                          }}
                          className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left hover:bg-elevated"
                        >
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-elevated text-caption font-semibold text-secondary">
                            {initialsOf(c.full_name, c.email)}
                          </span>
                          <span className="min-w-0">
                            <span className="block truncate text-body-sm font-medium text-primary">
                              {c.full_name || c.email}
                            </span>
                            <span className="block truncate text-caption text-tertiary">
                              {c.email}
                            </span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {touched && !canSubmit ? (
              <p className="text-caption text-danger">
                Chọn một người từ danh sách hoặc nhập email hợp lệ.
              </p>
            ) : null}
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
              disabled={submitting || !canSubmit}
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
