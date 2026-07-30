/**
 * =============================================================================
 * File: FileTypeIcon.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Consistent icon per document file_type across list/detail (FR2).
 * Responsibilities:
 *   - Map pdf/docx/xlsx/pptx/txt → a distinct lucide icon + accent color
 * Dependencies:
 *   - lucide-react, lib/utils
 * Public Exports:
 *   - FileTypeIcon
 * Database/Table: documents.file_type
 * Related Modules: features/documents/DocumentList, DocumentDetailView
 * Important Notes: Keep the icon/color map here only — never inline elsewhere.
 * =============================================================================
 */

import { File, FileSpreadsheet, FileText, Presentation, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import type { FileType } from "@/types/documents";

const ICON: Record<FileType, LucideIcon> = {
  pdf: FileText,
  docx: FileText,
  xlsx: FileSpreadsheet,
  pptx: Presentation,
  txt: File,
};

const COLOR: Record<FileType, string> = {
  pdf: "text-danger bg-danger-soft",
  docx: "text-info bg-info/10",
  xlsx: "text-success bg-success/10",
  pptx: "text-warning bg-warning/10",
  txt: "text-tertiary bg-elevated",
};

type Props = {
  fileType: FileType | string;
  className?: string;
};

export function FileTypeIcon({ fileType, className }: Props) {
  const ft = (fileType in ICON ? fileType : "txt") as FileType;
  const Icon = ICON[ft];
  return (
    <span
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
        COLOR[ft],
        className,
      )}
    >
      <Icon className="h-4 w-4" aria-hidden />
    </span>
  );
}
