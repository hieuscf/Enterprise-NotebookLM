/**
 * =============================================================================
 * File: DocumentContextBar.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Show which documents are in the current chat citation context.
 * Responsibilities:
 *   - Chip list of documents used in conversation; popover to browse all
 * Dependencies:
 *   - types/documents
 * Public Exports:
 *   - DocumentContextBar
 * Database/Table: N/A
 * Related Modules: ChatComposer
 * Important Notes: Chat retrieval is workspace-scoped — chips are informational
 *   (no client-side filter API). "Quản lý tài liệu" links to Documents.
 * =============================================================================
 */

"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { BookOpen, FileText, ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Document } from "@/types/documents";

export type ContextDocument = {
  id: string;
  title: string;
  fileType?: string;
};

type Props = {
  workspaceId: string;
  /** Documents referenced by citations in this conversation. */
  usedDocuments: ContextDocument[];
  /** Optional workspace catalog for the popover. */
  workspaceDocuments?: Document[];
};

export function DocumentContextBar({
  workspaceId,
  usedDocuments,
  workspaceDocuments = [],
}: Props) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const count = usedDocuments.length;
  const catalog = useMemo(() => {
    if (workspaceDocuments.length > 0) return workspaceDocuments;
    return usedDocuments.map(
      (d) =>
        ({
          id: d.id,
          title: d.title,
          file_type: (d.fileType as Document["file_type"]) || "pdf",
          workspace_id: workspaceId,
          current_version_id: null,
          created_at: "",
          updated_at: "",
        }) satisfies Document,
    );
  }, [workspaceDocuments, usedDocuments, workspaceId]);

  useEffect(() => {
    if (!open) return;
    function onDocClick(event: MouseEvent) {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={wrapRef} className="relative flex flex-col gap-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex w-fit items-center gap-1.5 text-caption font-medium text-secondary hover:text-primary"
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <BookOpen className="h-3.5 w-3.5 text-accent-primary" aria-hidden />
        {count > 0
          ? `${count} tài liệu đang sử dụng`
          : `${catalog.length > 0 ? catalog.length : "Các"} tài liệu trong workspace`}
        <ChevronDown
          className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </button>

      {count > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {usedDocuments.slice(0, 6).map((doc) => (
            <li key={doc.id}>
              <Link
                href={`/workspaces/${workspaceId}/documents/${doc.id}`}
                className={cn(
                  "inline-flex max-w-[12rem] items-center gap-1 rounded-full border border-border-default",
                  "bg-elevated/50 px-2 py-0.5 text-[11px] text-secondary hover:border-accent-primary/40 hover:text-accent-primary",
                )}
                title={doc.title}
              >
                <FileText className="h-3 w-3 shrink-0" aria-hidden />
                <span className="truncate">{doc.title}</span>
              </Link>
            </li>
          ))}
          {usedDocuments.length > 6 ? (
            <li className="text-[11px] text-tertiary">+{usedDocuments.length - 6}</li>
          ) : null}
        </ul>
      ) : null}

      {open ? (
        <div
          role="dialog"
          aria-label="Tài liệu trong ngữ cảnh"
          className="absolute bottom-full left-0 z-30 mb-2 w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-border-default bg-surface shadow-lg"
        >
          <div className="border-b border-border-default px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-tertiary">
              Tài liệu trong ngữ cảnh
            </p>
            <p className="text-caption text-secondary">
              Chat truy vấn toàn bộ workspace. Các mục dưới đây giúp theo dõi nguồn.
            </p>
          </div>
          <ul className="max-h-52 overflow-y-auto p-2">
            {catalog.length === 0 ? (
              <li className="px-2 py-3 text-caption text-tertiary">
                Chưa có tài liệu trong workspace.
              </li>
            ) : (
              catalog.slice(0, 40).map((doc) => {
                const used = usedDocuments.some((u) => u.id === doc.id);
                return (
                  <li key={doc.id}>
                    <Link
                      href={`/workspaces/${workspaceId}/documents/${doc.id}`}
                      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-caption text-secondary hover:bg-elevated hover:text-primary"
                      onClick={() => setOpen(false)}
                    >
                      <span
                        className={cn(
                          "flex h-3.5 w-3.5 items-center justify-center rounded-sm border text-[9px]",
                          used
                            ? "border-accent-primary bg-accent-primary text-white"
                            : "border-border-strong text-transparent",
                        )}
                        aria-hidden
                      >
                        {used ? "✓" : ""}
                      </span>
                      <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      <span className="truncate">{doc.title}</span>
                    </Link>
                  </li>
                );
              })
            )}
          </ul>
          <div className="border-t border-border-default px-3 py-2">
            <Link
              href={`/workspaces/${workspaceId}/documents`}
              className="text-caption font-medium text-accent-primary hover:underline"
              onClick={() => setOpen(false)}
            >
              Quản lý tài liệu →
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
