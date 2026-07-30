/**
 * =============================================================================
 * File: useToasts.ts
 * Module/Service: Web App shell
 * Layer: UI
 * Purpose: Minimal, dependency-free toast queue (no toast lib in package.json;
 *          hand-written like ConfirmDialog) — first consumer is Document Upload.
 * Responsibilities:
 *   - Hold an array of transient toasts; auto-dismiss after a timeout
 *   - Expose push()/dismiss() for feature code to call
 * Dependencies:
 *   - None
 * Public Exports:
 *   - useToasts, type Toast, type ToastVariant
 * Database/Table: N/A
 * Related Modules: components/ui/toast.tsx (ToastStack renders the queue)
 * Important Notes: Local to whichever component calls the hook — not a global
 *   singleton. Mount one ToastStack per page that needs it (e.g. upload page).
 * =============================================================================
 */

"use client";

import { useCallback, useRef, useState } from "react";

export type ToastVariant = "error" | "success" | "info";

export type Toast = {
  id: string;
  variant: ToastVariant;
  message: string;
};

const DEFAULT_DURATION_MS = 6000;

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counterRef = useRef(0);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (variant: ToastVariant, message: string, durationMs = DEFAULT_DURATION_MS) => {
      counterRef.current += 1;
      const id = `toast-${counterRef.current}`;
      setToasts((prev) => [...prev, { id, variant, message }]);
      if (durationMs > 0) {
        setTimeout(() => dismiss(id), durationMs);
      }
      return id;
    },
    [dismiss],
  );

  return {
    toasts,
    push,
    dismiss,
    pushError: (message: string) => push("error", message),
    pushSuccess: (message: string) => push("success", message),
  };
}
