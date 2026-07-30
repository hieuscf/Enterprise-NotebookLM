/**
 * =============================================================================
 * File: DocumentEmptyState.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Empty state for the document list — guides the user to Part 1's
 *          upload page instead of leaving a bare table (FR2 Part 2).
 * Responsibilities:
 *   - Short instructions + CTA link to /workspaces/{id}/upload
 * Dependencies:
 *   - next/link, lucide-react, lib/utils
 * Public Exports:
 *   - DocumentEmptyState
 * Database/Table: N/A
 * Related Modules: features/documents/DocumentList, DocumentUploadView (Part 1)
 * Important Notes: Distinct from the "no results for this filter" case, which
 *   DocumentList renders inline instead of this component.
 * =============================================================================
 */

import { FolderOpen, UploadCloud } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
};

export function DocumentEmptyState({ workspaceId }: Props) {
  return (
    <section className="relative overflow-hidden rounded-xl border border-dashed border-border-strong bg-surface px-6 py-14 text-center shadow-xs">
      <span className="relative mx-auto flex h-14 w-14 items-center justify-center rounded-xl bg-accent-primary-soft">
        <FolderOpen className="h-7 w-7 text-accent-primary" aria-hidden />
      </span>
      <h2 className="relative mt-5 text-h2 text-primary">Chưa có tài liệu nào</h2>
      <p className="relative mx-auto mt-2 max-w-md text-body-sm text-secondary">
        Tải lên tài liệu đầu tiên (PDF, DOCX, XLSX, PPTX, TXT) để bắt đầu xử lý pipeline
        và dùng cho Chat / tìm kiếm sau này.
      </p>
      <Link
        href={`/workspaces/${workspaceId}/upload`}
        className={cn(
          "relative mt-6 inline-flex h-11 items-center gap-2 rounded-md bg-accent-primary px-5",
          "text-body-sm font-medium text-white shadow-sm hover:bg-accent-primary-hover",
        )}
      >
        <UploadCloud className="h-4 w-4" aria-hidden />
        Tải lên tài liệu
      </Link>
    </section>
  );
}
