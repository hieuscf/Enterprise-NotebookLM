/**
 * =============================================================================
 * File: AdminRowMenu.tsx
 * Module/Service: Workspace Service / Observability (Web App)
 * Layer: UI
 * Purpose: Compact row action menu for Admin Console tables (View / Edit /
 *          Delete). Hand-rolled — the repo has no Radix DropdownMenu yet
 *          (same approach as ConfirmDialog / ToastStack).
 * Responsibilities:
 *   - Toggle a small menu; close on Escape / outside click / item select
 *   - Expose accessible aria-haspopup / aria-expanded / aria-label
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - AdminRowMenu, type AdminRowMenuItem
 * Database/Table: N/A
 * Related Modules: features/admin/AdminWorkspacesTable.tsx
 * Important Notes: Menu items are filtered by the parent (RBAC) — this
 *   component only renders what it is given.
 * =============================================================================
 */

"use client";

import { MoreHorizontal } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export type AdminRowMenuItem = {
  key: string;
  label: string;
  onSelect: () => void;
  destructive?: boolean;
  disabled?: boolean;
  /** Native tooltip when disabled (e.g. self-delete protection). */
  title?: string;
};

type Props = {
  label: string;
  items: AdminRowMenuItem[];
};

export function AdminRowMenu({ label, items }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointer(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (items.length === 0) return null;

  return (
    <div ref={rootRef} className="relative inline-flex justify-end">
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded-md text-tertiary",
          "hover:bg-elevated hover:text-primary",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/30",
        )}
      >
        <MoreHorizontal className="h-4 w-4" aria-hidden />
      </button>
      {open ? (
        <ul
          id={menuId}
          role="menu"
          aria-label={label}
          className="absolute right-0 top-full z-20 mt-1 min-w-[10rem] rounded-md border border-border-default bg-surface py-1 shadow-md"
        >
          {items.map((item) => (
            <li key={item.key} role="none">
              <button
                type="button"
                role="menuitem"
                disabled={item.disabled}
                title={item.title}
                onClick={() => {
                  if (item.disabled) return;
                  setOpen(false);
                  item.onSelect();
                }}
                className={cn(
                  "flex w-full px-3 py-2 text-left text-body-sm",
                  item.destructive
                    ? "text-danger hover:bg-danger-soft"
                    : "text-secondary hover:bg-elevated hover:text-primary",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                )}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
