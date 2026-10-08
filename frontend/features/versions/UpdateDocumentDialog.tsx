/**
 * =============================================================================
 * File: UpdateDocumentDialog.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Pick a document by name, then upload a newer file as its next version.
 * Responsibilities:
 *   - Search the workspace document list without using the version catalog
 *   - Require an explicit document choice before the file and confirm step
 *   - Upload that file and keep older versions available for rollback
 * Dependencies:
 *   - lib/api-client.listDocuments, uploadDocumentVersionXhr
 *   - lib/upload-constraints
 * Public Exports:
 *   - UpdateDocumentDialog
 * Database/Table: documents, document_versions, document_version_events
 * Related Modules: features/versions/VersionCenterView
 * Important Notes: Does not create a new document. The new version becomes current.
 * =============================================================================
 */

"use client";

import { Search, UploadCloud, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { FileTypeIcon } from "@/features/documents/FileTypeIcon";
import { ApiClientError, listDocuments, uploadDocumentVersionXhr } from "@/lib/api-client";
import { FILE_VALIDATION_MESSAGE, validateFile } from "@/lib/upload-constraints";
import { cn } from "@/lib/utils";
import type { Document, DocumentVersion, FileType } from "@/types/documents";

export type UpdateDocumentTarget = {
  id: string;
  title: string;
  file_type: FileType;
};

type Props = {
  open: boolean;
  workspaceId: string;
  /** Optional shortcut when the dialog is opened from one version row. */
  initialDocument?: UpdateDocumentTarget | null;
  onClose: () => void;
  onUploaded: (version: DocumentVersion, documentTitle: string) => void;
};

export function UpdateDocumentDialog({
  open,
  workspaceId,
  initialDocument = null,
  onClose,
  onUploaded,
}: Props) {
  const titleId = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<UpdateDocumentTarget | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !uploading) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, uploading]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      setTotal(0);
      setChosen(null);
      setFile(null);
      setNote("");
      setError(null);
      setListError(null);
      setProgress(null);
      setUploading(false);
      return;
    }
    setChosen(initialDocument);
  }, [open, initialDocument]);

  useEffect(() => {
    if (!open) return;
    const handle = window.setTimeout(() => {
      setLoadingDocs(true);
      setListError(null);
      void listDocuments(workspaceId, { page: 1, pageSize: 20, query })
        .then((data) => {
          setResults(data.items);
          setTotal(data.total);
        })
        .catch((err: unknown) => {
          setResults([]);
          setTotal(0);
          setListError(
            err instanceof ApiClientError ? err.message : "Không tải được danh sách tài liệu.",
          );
        })
        .finally(() => setLoadingDocs(false));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [open, workspaceId, query]);

  if (!open) return null;

  const expectedExt = chosen ? `.${chosen.file_type}` : "";

  function choose(document: Document) {
    if (uploading) return;
    setChosen({ id: document.id, title: document.title, file_type: document.file_type });
    setFile(null);
    setError(null);
  }

  async function submit() {
    if (!chosen || !file || uploading) return;
    const validation = validateFile(file);
    if (validation) {
      setError(FILE_VALIDATION_MESSAGE[validation]);
      return;
    }
    if (!file.name.toLowerCase().endsWith(expectedExt)) {
      setError(
        `Tài liệu này là ${chosen.file_type.toUpperCase()}. Hãy chọn file ${expectedExt}.`,
      );
      return;
    }
    setUploading(true);
    setError(null);
    setProgress(0);
    try {
      const version = await uploadDocumentVersionXhr(
        workspaceId,
        chosen.id,
        file,
        setProgress,
        note,
      ).promise;
      onUploaded(version, chosen.title);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Không cập nhật được tài liệu.");
      setUploading(false);
      setProgress(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Đóng hộp thoại"
        className="absolute inset-0 bg-slate-950/40"
        onClick={() => {
          if (!uploading) onClose();
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 flex max-h-[min(40rem,calc(100svh-2rem))] w-full max-w-lg flex-col rounded-lg border border-border-default bg-surface p-6 shadow-lg"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id={titleId} className="text-h3 text-primary">
              Cập nhật tài liệu
            </h2>
            <p className="mt-1 text-body-sm text-secondary">
              Chọn tài liệu cần cập nhật, rồi xác nhận file mới. Bản mới trở thành bản hiện
              hành. Các phiên bản cũ vẫn được giữ để khôi phục.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={uploading}
            className="rounded-md p-1 text-tertiary hover:bg-elevated hover:text-primary disabled:opacity-50"
            aria-label="Đóng"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>

        <div className="mt-5 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
          <div>
            <label htmlFor="update-doc-search" className="text-caption font-medium text-secondary">
              Tài liệu
            </label>
            <div className="relative mt-1.5">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-tertiary"
                aria-hidden
              />
              <input
                id="update-doc-search"
                value={query}
                disabled={uploading}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Gõ tên tài liệu để tìm…"
                className="h-10 w-full rounded-md border border-border-default bg-base pr-3 pl-9 text-body-sm text-primary outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20 disabled:opacity-60"
              />
            </div>
            <div className="mt-2 max-h-44 overflow-y-auto rounded-md border border-border-default">
              {listError ? (
                <p className="px-3 py-4 text-body-sm text-danger">{listError}</p>
              ) : loadingDocs ? (
                <p className="px-3 py-4 text-body-sm text-tertiary">Đang tìm…</p>
              ) : results.length === 0 ? (
                <p className="px-3 py-4 text-body-sm text-secondary">Không có tài liệu khớp.</p>
              ) : (
                <ul>
                  {results.map((document) => {
                    const active = chosen?.id === document.id;
                    return (
                      <li key={document.id}>
                        <button
                          type="button"
                          disabled={uploading}
                          onClick={() => choose(document)}
                          className={cn(
                            "flex w-full items-center gap-2 px-3 py-2 text-left",
                            active ? "bg-accent-primary-soft" : "hover:bg-elevated/70",
                          )}
                        >
                          <FileTypeIcon fileType={document.file_type} className="h-8 w-8" />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-body-sm font-medium text-primary">
                              {document.title}
                            </span>
                            <span className="text-caption text-tertiary uppercase">
                              {document.file_type}
                            </span>
                          </span>
                          {active ? (
                            <span className="shrink-0 text-caption font-semibold text-accent-primary">
                              Đã chọn
                            </span>
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            <p className="mt-1 text-caption text-tertiary">
              {query.trim()
                ? `${total} tài liệu khớp`
                : total > results.length
                  ? `${total} tài liệu — gõ tên để tìm, không cần lần trong danh sách phiên bản`
                  : `${total} tài liệu`}
            </p>
          </div>

          <label className="flex flex-col gap-1.5 text-caption font-medium text-secondary">
            {chosen ? `File mới (${chosen.file_type.toUpperCase()})` : "File mới"}
            <input
              type="file"
              accept={expectedExt || undefined}
              disabled={uploading || !chosen}
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setError(null);
              }}
              className="text-body-sm font-normal text-primary file:mr-3 file:rounded-md file:border-0 file:bg-elevated file:px-3 file:py-2 file:text-caption file:font-medium file:text-primary disabled:opacity-60"
            />
          </label>

          <label className="flex flex-col gap-1.5 text-caption font-medium text-secondary">
            Ghi chú thay đổi
            <textarea
              value={note}
              disabled={uploading || !chosen}
              onChange={(event) => setNote(event.target.value)}
              rows={3}
              maxLength={2000}
              placeholder="Ví dụ: Sửa điều 3, bổ sung phụ lục"
              className="rounded-md border border-border-default bg-base px-3 py-2 text-body-sm font-normal text-primary outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20 disabled:opacity-60"
            />
          </label>

          {progress !== null ? (
            <div>
              <div className="h-1.5 overflow-hidden rounded-full bg-elevated">
                <div
                  className="h-full bg-accent-primary transition-[width]"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="mt-1 text-caption text-tertiary">
                {progress >= 100 ? "Đang lưu phiên bản…" : `Đang tải ${progress}%`}
              </p>
            </div>
          ) : null}

          {error ? (
            <p role="alert" className="text-body-sm text-danger">
              {error}
            </p>
          ) : null}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={uploading}
            className="h-10 rounded-md border border-border-default px-4 text-body-sm font-medium text-secondary hover:bg-elevated disabled:opacity-50"
          >
            Hủy
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!chosen || !file || uploading}
            className={cn(
              "inline-flex h-10 items-center gap-2 rounded-md bg-accent-primary px-4",
              "text-body-sm font-medium text-white hover:bg-accent-primary-hover",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            <UploadCloud className="h-4 w-4" aria-hidden />
            {uploading ? "Đang cập nhật…" : "Xác nhận"}
          </button>
        </div>
      </div>
    </div>
  );
}
