/**
 * =============================================================================
 * File: DocumentUploadDropzone.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Drag-drop / click-to-browse file picker with per-file title editing
 *          and client-side validation, staged before submit (FR2 / UC2).
 *          `mode="replace"` (Part 2) restricts to a single file and hides the
 *          title input — POST .../versions keeps the document's existing title.
 * Responsibilities:
 *   - Accept .pdf/.docx/.xlsx/.pptx/.txt via drag-drop or <input type=file>
 *   - Validate each file (extension, empty, > MAX_FILE_SIZE_BYTES) and show
 *     inline errors without blocking the other staged files
 *   - Let the user edit each file's title (defaults to filename) before submit
 *     — skipped entirely in "replace" mode
 *   - Emit only the valid staged files to the parent on submit
 * Dependencies:
 *   - lib/upload-constraints, lib/utils, lucide-react
 * Public Exports:
 *   - DocumentUploadDropzone
 * Database/Table: N/A (staging only — parent calls the upload queue hook)
 * Related Modules: hooks/useDocumentUploadQueue, features/documents/DocumentUploadView,
 *   features/documents/DocumentVersionHistory (mode="replace")
 * Important Notes: idle / dragging-over / (staged list) states live here;
 *   "uploading" / "queued" progress states live in UploadJobCard once submitted.
 * =============================================================================
 */

"use client";

import { AlertCircle, UploadCloud, X } from "lucide-react";
import { useId, useRef, useState } from "react";

import {
  ACCEPT_ATTRIBUTE,
  FILE_VALIDATION_MESSAGE,
  formatBytes,
  titleFromFilename,
  validateFile,
  type FileValidationError,
} from "@/lib/upload-constraints";
import { cn } from "@/lib/utils";
import type { StagedFile } from "@/hooks/useDocumentUploadQueue";

type StagedItem = {
  id: string;
  file: File;
  title: string;
  error: FileValidationError | null;
};

type Props = {
  mode?: "new" | "replace";
  disabled?: boolean;
  disabledReason?: string;
  onSubmit: (staged: StagedFile[]) => void;
};

let stagedIdCounter = 0;

export function DocumentUploadDropzone({
  mode = "new",
  disabled = false,
  disabledReason,
  onSubmit,
}: Props) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [staged, setStaged] = useState<StagedItem[]>([]);
  const isReplace = mode === "replace";

  function addFiles(files: FileList | File[]) {
    const items: StagedItem[] = Array.from(files).map((file) => {
      stagedIdCounter += 1;
      return {
        id: `staged-${stagedIdCounter}`,
        file,
        title: titleFromFilename(file.name),
        error: validateFile(file),
      };
    });
    if (items.length === 0) return;
    // Replace mode: one file replaces the pending slot, it doesn't accumulate.
    setStaged((prev) => (isReplace ? items.slice(0, 1) : [...prev, ...items]));
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    if (disabled) return;
    if (event.dataTransfer.files.length > 0) addFiles(event.dataTransfer.files);
  }

  function handlePick(event: React.ChangeEvent<HTMLInputElement>) {
    if (event.target.files && event.target.files.length > 0) addFiles(event.target.files);
    event.target.value = "";
  }

  function updateTitle(id: string, title: string) {
    setStaged((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
  }

  function removeStaged(id: string) {
    setStaged((prev) => prev.filter((s) => s.id !== id));
  }

  const validStaged = staged.filter((s) => s.error === null);
  const hasValid = validStaged.length > 0;

  function handleSubmit() {
    if (!hasValid) return;
    onSubmit(
      validStaged.map((s) => ({
        file: s.file,
        title: s.title.trim() || titleFromFilename(s.file.name),
      })),
    );
    setStaged((prev) => prev.filter((s) => s.error !== null));
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => {
          if (!disabled) inputRef.current?.click();
        }}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) inputRef.current?.click();
        }}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors",
          disabled
            ? "cursor-not-allowed border-border-default bg-elevated/40 opacity-60"
            : "cursor-pointer border-border-strong hover:border-accent-primary hover:bg-accent-primary-soft",
          dragOver && !disabled ? "border-accent-primary bg-accent-primary-soft" : "bg-surface",
        )}
      >
        <span
          className={cn(
            "flex h-12 w-12 items-center justify-center rounded-full",
            dragOver ? "bg-accent-primary-soft" : "bg-elevated",
          )}
        >
          <UploadCloud
            className={cn("h-6 w-6", dragOver ? "text-accent-primary" : "text-tertiary")}
            aria-hidden
          />
        </span>
        <p className="text-body font-medium text-primary">
          {dragOver
            ? "Thả file để tải lên"
            : isReplace
              ? "Kéo-thả file thay thế vào đây, hoặc bấm để chọn"
              : "Kéo-thả file vào đây, hoặc bấm để chọn"}
        </p>
        <p className="text-caption text-tertiary">
          {isReplace
            ? `Cùng định dạng với tài liệu hiện tại — tối đa ${formatBytes(50 * 1024 * 1024)}`
            : `Hỗ trợ PDF, DOCX, XLSX, PPTX, TXT — tối đa ${formatBytes(50 * 1024 * 1024)}/file`}
        </p>
        {disabled && disabledReason ? (
          <p className="text-caption text-tertiary">{disabledReason}</p>
        ) : null}
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          multiple={!isReplace}
          accept={ACCEPT_ATTRIBUTE}
          disabled={disabled}
          onChange={handlePick}
          className="sr-only"
        />
      </div>

      {staged.length > 0 ? (
        <div className="flex flex-col gap-2 rounded-lg border border-border-default bg-surface p-3">
          <p className="text-caption font-medium uppercase tracking-wider text-tertiary">
            Sẵn sàng tải lên ({validStaged.length}/{staged.length})
          </p>
          <ul className="flex flex-col gap-2">
            {staged.map((item) => (
              <li
                key={item.id}
                className={cn(
                  "flex items-center gap-3 rounded-md border px-3 py-2",
                  item.error ? "border-danger/30 bg-danger-soft" : "border-border-default bg-base",
                )}
              >
                <div className="min-w-0 flex-1">
                  {item.error ? (
                    <div className="flex items-center gap-1.5 text-body-sm text-danger">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden />
                      <span className="truncate font-medium">{item.file.name}</span>
                    </div>
                  ) : isReplace ? (
                    <p className="truncate text-body-sm font-medium text-primary">
                      {item.file.name}
                    </p>
                  ) : (
                    <input
                      value={item.title}
                      onChange={(e) => updateTitle(item.id, e.target.value)}
                      placeholder={titleFromFilename(item.file.name)}
                      className="h-8 w-full rounded-md border border-transparent bg-transparent px-1 text-body-sm font-medium text-primary outline-none focus:border-accent-primary focus:bg-surface focus:ring-1 focus:ring-accent-primary/20"
                    />
                  )}
                  <p className="mt-0.5 truncate text-caption text-tertiary">
                    {item.error
                      ? FILE_VALIDATION_MESSAGE[item.error]
                      : `${item.file.name} · ${formatBytes(item.file.size)}`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => removeStaged(item.id)}
                  aria-label={`Bỏ ${item.file.name}`}
                  className="shrink-0 rounded-md p-1 text-tertiary hover:bg-elevated hover:text-primary"
                >
                  <X className="h-4 w-4" aria-hidden />
                </button>
              </li>
            ))}
          </ul>

          <div className="mt-1 flex justify-end">
            <button
              type="button"
              disabled={disabled || !hasValid}
              onClick={handleSubmit}
              className={cn(
                "flex h-10 items-center gap-2 rounded-md bg-accent-primary px-4",
                "text-body-sm font-medium text-white",
                "hover:bg-accent-primary-hover disabled:cursor-not-allowed disabled:opacity-60",
              )}
            >
              {isReplace ? "Tải lên version mới" : `Tải lên ${hasValid ? `${validStaged.length} tệp` : ""}`}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
