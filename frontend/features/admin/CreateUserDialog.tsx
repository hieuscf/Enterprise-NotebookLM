/**
 * =============================================================================
 * File: CreateUserDialog.tsx
 * Module/Service: Admin User Management (Web App) — FR12
 * Layer: UI
 * Purpose: Modal to create an enterprise user account via POST /admin/users.
 * Responsibilities:
 *   - Collect full_name, email, password, confirm_password
 *   - Client-side validation (required, email format, password match)
 *   - Never store/log password; submit plain password to API only
 * Dependencies:
 *   - lib/api-client.ApiClientError
 * Public Exports:
 *   - CreateUserDialog, mapCreateUserError, type CreateUserFormValues
 * Database/Table: users
 * Related Modules: features/admin/AdminUsersView
 * Important Notes: Confirm password is UI-only — not sent to the API.
 * =============================================================================
 */

"use client";

import { Loader2, X } from "lucide-react";
import { useEffect, useId, useState, type FormEvent } from "react";

import { ApiClientError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

export type CreateUserFormValues = {
  full_name: string;
  email: string;
  password: string;
};

type Props = {
  open: boolean;
  submitting: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (values: CreateUserFormValues) => void;
};

type FieldErrors = {
  full_name?: string;
  email?: string;
  password?: string;
  confirm_password?: string;
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateCreateUserForm(input: {
  full_name: string;
  email: string;
  password: string;
  confirm_password: string;
}): { ok: true; values: CreateUserFormValues } | { ok: false; errors: FieldErrors } {
  const errors: FieldErrors = {};
  const full_name = input.full_name.trim();
  const email = input.email.trim().toLowerCase();
  const password = input.password;
  const confirm_password = input.confirm_password;

  if (!full_name) errors.full_name = "Full name is required.";
  if (!email) errors.email = "Email is required.";
  else if (!EMAIL_RE.test(email)) errors.email = "Enter a valid email address.";
  if (!password) errors.password = "Password is required.";
  if (!confirm_password) errors.confirm_password = "Confirm your password.";
  else if (password && confirm_password !== password) {
    errors.confirm_password = "Passwords do not match.";
  }

  if (Object.keys(errors).length > 0) return { ok: false, errors };
  return { ok: true, values: { full_name, email, password } };
}

export function mapCreateUserError(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    if (err.status === 401) return "Your session has expired. Please sign in again.";
    if (err.status === 403) {
      return "You don't have permission to create user accounts.";
    }
    if (err.status === 409 || err.code === "email_exists") {
      return "An account with this email already exists.";
    }
    if (err.status === 422 || err.status === 400) {
      return err.message || "Please check the form and try again.";
    }
    if (err.status === 0 || err.code === "network_error") {
      return "Network error. Check your connection and try again.";
    }
    if (err.status >= 500) return "Something went wrong on the server. Please try again.";
    return err.message || fallback;
  }
  return fallback;
}

export function CreateUserDialog({ open, submitting, error, onClose, onSubmit }: Props) {
  const titleId = useId();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  useEffect(() => {
    if (!open) return;
    setFullName("");
    setEmail("");
    setPassword("");
    setConfirmPassword("");
    setFieldErrors({});
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

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const result = validateCreateUserForm({
      full_name: fullName,
      email,
      password,
      confirm_password: confirmPassword,
    });
    if (!result.ok) {
      setFieldErrors(result.errors);
      return;
    }
    setFieldErrors({});
    onSubmit(result.values);
  }

  const inputClass = cn(
    "h-10 w-full rounded-md border border-border-default bg-base px-3",
    "text-body-sm text-primary placeholder:text-tertiary",
    "outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20",
    "disabled:cursor-not-allowed disabled:opacity-60",
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex w-full max-w-md flex-col rounded-lg border border-border-default bg-surface shadow-lg"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border-default px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-h3 text-primary">
              Create account
            </h2>
            <p className="mt-0.5 text-body-sm text-secondary">
              Create a new enterprise user account.
            </p>
          </div>
          <button
            type="button"
            aria-label="Close"
            disabled={submitting}
            onClick={onClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-tertiary hover:bg-elevated disabled:opacity-50"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-5 py-4" noValidate>
          <label className="flex flex-col gap-1.5">
            <span className="text-body-sm font-medium text-primary">Full name</span>
            <input
              type="text"
              autoComplete="name"
              value={fullName}
              disabled={submitting}
              onChange={(e) => setFullName(e.target.value)}
              className={inputClass}
              aria-invalid={Boolean(fieldErrors.full_name)}
            />
            {fieldErrors.full_name ? (
              <span role="alert" className="text-caption text-danger">
                {fieldErrors.full_name}
              </span>
            ) : null}
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-body-sm font-medium text-primary">Email</span>
            <input
              type="email"
              autoComplete="email"
              value={email}
              disabled={submitting}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              aria-invalid={Boolean(fieldErrors.email)}
            />
            {fieldErrors.email ? (
              <span role="alert" className="text-caption text-danger">
                {fieldErrors.email}
              </span>
            ) : null}
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-body-sm font-medium text-primary">Password</span>
            <input
              type="password"
              autoComplete="new-password"
              value={password}
              disabled={submitting}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
              aria-invalid={Boolean(fieldErrors.password)}
            />
            {fieldErrors.password ? (
              <span role="alert" className="text-caption text-danger">
                {fieldErrors.password}
              </span>
            ) : null}
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-body-sm font-medium text-primary">Confirm password</span>
            <input
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              disabled={submitting}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={inputClass}
              aria-invalid={Boolean(fieldErrors.confirm_password)}
            />
            {fieldErrors.confirm_password ? (
              <span role="alert" className="text-caption text-danger">
                {fieldErrors.confirm_password}
              </span>
            ) : null}
          </label>

          {error ? (
            <p role="alert" className="text-body-sm text-danger">
              {error}
            </p>
          ) : null}

          <div className="flex justify-end gap-2 border-t border-border-default pt-4">
            <button
              type="button"
              disabled={submitting}
              onClick={onClose}
              className="inline-flex h-9 items-center rounded-md border border-border-default px-3 text-body-sm font-medium text-secondary hover:bg-elevated disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className={cn(
                "inline-flex h-9 items-center gap-2 rounded-md bg-accent-primary px-3",
                "text-body-sm font-medium text-white hover:bg-accent-primary-hover",
                "disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
              {submitting ? "Creating..." : "Create"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
