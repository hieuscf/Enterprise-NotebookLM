/**
 * =============================================================================
 * File: SettingsSaveBar.tsx
 * Module/Service: Settings (Web App)
 * Layer: UI
 * Purpose: Sticky unsaved-changes footer for Settings forms.
 * Responsibilities:
 *   - Surface Discard / Save actions when the form is dirty
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - SettingsSaveBar
 * Database/Table: N/A
 * Related Modules: features/settings/pages/*
 * Important Notes: Only render when dirty — keep chrome quiet otherwise.
 * =============================================================================
 */

"use client";

import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

type Props = {
  dirty: boolean;
  saving?: boolean;
  disabled?: boolean;
  message?: string;
  discardLabel?: string;
  saveLabel?: string;
  onDiscard: () => void;
  onSave: () => void;
};

export function SettingsSaveBar({
  dirty,
  saving = false,
  disabled = false,
  message = "Bạn có thay đổi chưa lưu.",
  discardLabel = "Huỷ bỏ",
  saveLabel = "Lưu thay đổi",
  onDiscard,
  onSave,
}: Props) {
  if (!dirty) return null;

  return (
    <div
      role="status"
      className={cn(
        "sticky bottom-0 z-10 -mx-4 mt-6 border-t border-border-default bg-surface/95 px-4 py-3 backdrop-blur-sm sm:-mx-6 sm:px-6",
        "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between",
      )}
    >
      <p className="text-body-sm text-secondary">{message}</p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={saving}
          onClick={onDiscard}
          className={cn(
            "h-10 rounded-md border border-border-default px-4",
            "text-body-sm font-medium text-secondary",
            "hover:bg-elevated hover:text-primary disabled:opacity-50",
          )}
        >
          {discardLabel}
        </button>
        <button
          type="button"
          disabled={saving || disabled}
          onClick={onSave}
          className={cn(
            "flex h-10 items-center gap-2 rounded-md bg-accent-primary px-4",
            "text-body-sm font-medium text-white",
            "hover:bg-accent-primary-hover",
            "disabled:cursor-not-allowed disabled:opacity-60",
          )}
        >
          {saving ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Đang lưu…
            </>
          ) : (
            saveLabel
          )}
        </button>
      </div>
    </div>
  );
}
