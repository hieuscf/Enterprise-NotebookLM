/**
 * =============================================================================
 * File: ComparisonPicker.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: Select ≥2 workspace documents + optional focus for UC7 compare.
 * Responsibilities:
 *   - Checkbox list from workspace documents; disable Compare when <2 selected
 *   - Optional focus text field; emit selection on submit
 * Dependencies:
 *   - FileTypeIcon, useDocuments, lucide-react
 * Public Exports:
 *   - ComparisonPicker
 * Database/Table: N/A
 * Related Modules: ComparisonsView
 * Important Notes: Reuses document list API; compare gated by canEdit.
 * =============================================================================
 */

"use client";

import { GitCompare, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";

import { FileTypeIcon } from "@/features/documents/FileTypeIcon";
import { useDocuments } from "@/hooks/useDocuments";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  canEdit: boolean;
  submitting?: boolean;
  onCompare: (documentIds: string[], focus: string) => void;
};

export function ComparisonPicker({
  workspaceId,
  canEdit,
  submitting = false,
  onCompare,
}: Props) {
  const { items, total, loading, error, reload } = useDocuments(workspaceId, {
    page: 1,
    pageSize: 100,
    fileType: null,
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [focus, setFocus] = useState("");

  const selectedCount = selected.size;
  const canSubmit = canEdit && selectedCount >= 2 && !submitting && !loading;

  const selectedTitles = useMemo(() => {
    const map = new Map(items.map((d) => [d.id, d.title]));
    return [...selected].map((id) => map.get(id) ?? id.slice(0, 8));
  }, [items, selected]);

  function toggle(documentId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(documentId)) next.delete(documentId);
      else next.add(documentId);
      return next;
    });
  }

  function handleSubmit() {
    if (!canSubmit) return;
    onCompare([...selected], focus.trim());
  }

  return (
    <section
      aria-labelledby="comparison-picker-heading"
      className="flex flex-col gap-4 rounded-lg border border-border-default bg-surface p-4 sm:p-5"
    >
      <div>
        <h2 id="comparison-picker-heading" className="text-h3 text-primary">
          Chọn tài liệu
        </h2>
        <p className="mt-1 text-body-sm text-secondary">
          Chọn ít nhất 2 tài liệu trong workspace để so sánh.
          {selectedCount > 0
            ? ` Đã chọn ${selectedCount}: ${selectedTitles.slice(0, 3).join(", ")}${selectedTitles.length > 3 ? "…" : ""}.`
            : null}
        </p>
      </div>

      <div>
        <label
          htmlFor="comparison-focus"
          className="text-body-sm font-medium text-secondary"
        >
          Chủ đề trọng tâm <span className="font-normal text-tertiary">(tuỳ chọn)</span>
        </label>
        <input
          id="comparison-focus"
          type="text"
          value={focus}
          onChange={(e) => setFocus(e.target.value)}
          placeholder="Ví dụ: chính sách nghỉ phép, ngân sách FY25…"
          disabled={submitting}
          className={cn(
            "mt-1.5 h-10 w-full rounded-md border border-border-default bg-base px-3",
            "text-body-sm text-primary placeholder:text-tertiary",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
            "disabled:opacity-60",
          )}
        />
      </div>

      {error ? (
        <div
          role="alert"
          className="flex items-start justify-between gap-3 rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-body-sm text-danger"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void reload()}
            className="shrink-0 font-medium underline"
          >
            Thử lại
          </button>
        </div>
      ) : null}

      <div className="max-h-72 overflow-y-auto rounded-md border border-border-default">
        {loading ? (
          <div className="flex items-center gap-2 px-4 py-6 text-body-sm text-secondary">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            Đang tải danh sách tài liệu…
          </div>
        ) : items.length === 0 ? (
          <p className="px-4 py-6 text-body-sm text-tertiary">
            Workspace chưa có tài liệu để so sánh.
          </p>
        ) : (
          <ul className="divide-y divide-border-default" aria-label="Danh sách tài liệu">
            {items.map((doc) => {
              const checked = selected.has(doc.id);
              return (
                <li key={doc.id}>
                  <label
                    className={cn(
                      "flex cursor-pointer items-center gap-3 px-3 py-2.5 transition-colors",
                      checked ? "bg-accent-primary/5" : "hover:bg-elevated",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(doc.id)}
                      disabled={submitting || !canEdit}
                      className="h-4 w-4 rounded border-border-default text-accent-primary focus:ring-accent-primary/40"
                    />
                    <FileTypeIcon fileType={doc.file_type} className="h-8 w-8 shrink-0" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-body-sm font-medium text-primary">
                        {doc.title}
                      </span>
                      <span className="block text-caption uppercase text-tertiary">
                        {doc.file_type}
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {total > items.length ? (
        <p className="text-caption text-tertiary">
          Đang hiển thị {items.length}/{total} tài liệu (tối đa 100 trên trang chọn).
        </p>
      ) : null}

      {!canEdit ? (
        <p className="text-caption text-tertiary">
          Bạn cần quyền editor trở lên để tạo so sánh mới.
        </p>
      ) : null}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!canSubmit}
          aria-disabled={!canSubmit}
          className={cn(
            "inline-flex h-10 items-center justify-center gap-2 rounded-md px-4",
            "text-body-sm font-medium text-white shadow-sm transition-colors",
            canSubmit
              ? "bg-accent-primary hover:bg-accent-primary-hover"
              : "cursor-not-allowed bg-accent-primary/40",
          )}
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <GitCompare className="h-4 w-4" aria-hidden />
          )}
          {submitting ? "Đang gửi…" : "So sánh"}
        </button>
      </div>
    </section>
  );
}
