/**
 * =============================================================================
 * File: DocumentActionsMenu.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Overflow menu for document actions (download, versions, delete).
 * Responsibilities:
 *   - Group actions; separate destructive delete; copy link
 * Dependencies:
 *   - lucide-react, lib/utils, lib/rbac
 * Public Exports:
 *   - DocumentActionsMenu
 * Database/Table: N/A
 * Related Modules: DocumentDetailView
 * Important Notes: Delete gated by canDeleteDocuments; confirmation is parent.
 * =============================================================================
 */

"use client";

import {
  Copy,
  Download,
  ExternalLink,
  History,
  MoreHorizontal,
  Printer,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { cn } from "@/lib/utils";

type Props = {
  canUploadVersion: boolean;
  canDelete: boolean;
  onOpenOriginal: () => void;
  onDownload: () => void;
  onPrint: () => void;
  onUploadVersion: () => void;
  onVersionHistory: () => void;
  onCopyLink: () => void;
  onDelete: () => void;
};

export function DocumentActionsMenu({
  canUploadVersion,
  canDelete,
  onOpenOriginal,
  onDownload,
  onPrint,
  onUploadVersion,
  onVersionHistory,
  onCopyLink,
  onDelete,
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function run(fn: () => void) {
    setOpen(false);
    fn();
  }

  const itemClass =
    "flex w-full items-center gap-2 px-3 py-2 text-left text-body-sm text-secondary hover:bg-elevated hover:text-primary";

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label="Document actions"
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 w-9 items-center justify-center rounded-md text-secondary hover:bg-elevated hover:text-primary"
      >
        <MoreHorizontal className="h-4 w-4" aria-hidden />
      </button>

      {open ? (
        <div
          id={menuId}
          role="menu"
          className="absolute right-0 z-30 mt-1 w-56 rounded-md border border-border-default bg-surface py-1 shadow-md"
        >
          <button type="button" role="menuitem" className={itemClass} onClick={() => run(onOpenOriginal)}>
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            Open original
          </button>
          <button type="button" role="menuitem" className={itemClass} onClick={() => run(onDownload)}>
            <Download className="h-3.5 w-3.5" aria-hidden />
            Download original
          </button>
          <button type="button" role="menuitem" className={itemClass} onClick={() => run(onPrint)}>
            <Printer className="h-3.5 w-3.5" aria-hidden />
            Print
          </button>

          <div className="my-1 border-t border-border-default" />

          {canUploadVersion ? (
            <button type="button" role="menuitem" className={itemClass} onClick={() => run(onUploadVersion)}>
              <UploadCloud className="h-3.5 w-3.5" aria-hidden />
              Upload new version
            </button>
          ) : null}
          <button type="button" role="menuitem" className={itemClass} onClick={() => run(onVersionHistory)}>
            <History className="h-3.5 w-3.5" aria-hidden />
            View version history
          </button>

          <div className="my-1 border-t border-border-default" />

          <button type="button" role="menuitem" className={itemClass} onClick={() => run(onCopyLink)}>
            <Copy className="h-3.5 w-3.5" aria-hidden />
            Copy document link
          </button>

          {canDelete ? (
            <>
              <div className="my-1 border-t border-border-default" />
              <button
                type="button"
                role="menuitem"
                className={cn(itemClass, "text-danger hover:bg-danger-soft hover:text-danger")}
                onClick={() => run(onDelete)}
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden />
                Delete document
              </button>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
