/**
 * =============================================================================
 * File: SearchForm.tsx
 * Module/Service: Search Service (Web App)
 * Layer: UI
 * Purpose: Search query + filters form (FR3 / UC3).
 * Responsibilities:
 *   - Query input, file type, date range, tags; Enter-to-submit; loading disable
 * Dependencies:
 *   - types/search, types/documents, lucide-react
 * Public Exports:
 *   - SearchForm, SearchFormValues
 * Database/Table: N/A
 * Related Modules: features/search/SearchView.tsx
 * Important Notes: Controlled by parent; does not call API directly.
 * =============================================================================
 */

"use client";

import { Search, Loader2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { cn } from "@/lib/utils";
import type { FileType } from "@/types/documents";
import type { SearchFilters } from "@/types/search";

export type SearchFormValues = {
  queryText: string;
  filters: SearchFilters;
};

type Props = {
  initialQuery?: string;
  loading?: boolean;
  onSubmit: (values: SearchFormValues) => void;
};

const FILE_TYPE_OPTIONS: { value: FileType | ""; label: string }[] = [
  { value: "", label: "Tất cả định dạng" },
  { value: "pdf", label: "PDF" },
  { value: "docx", label: "DOCX" },
  { value: "xlsx", label: "XLSX" },
  { value: "pptx", label: "PPTX" },
  { value: "txt", label: "TXT" },
];

export function SearchForm({ initialQuery = "", loading = false, onSubmit }: Props) {
  const [queryText, setQueryText] = useState(initialQuery);
  const [fileType, setFileType] = useState<FileType | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [tagsInput, setTagsInput] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const tags = tagsInput
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const filters: SearchFilters = {};
    if (fileType) filters.file_type = fileType;
    if (dateFrom) filters.date_from = new Date(dateFrom).toISOString();
    if (dateTo) {
      const end = new Date(dateTo);
      end.setHours(23, 59, 59, 999);
      filters.date_to = end.toISOString();
    }
    if (tags.length) filters.tags = tags;
    onSubmit({ queryText, filters });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-lg border border-border-default bg-surface p-4"
    >
      <div className="flex flex-col gap-2 sm:flex-row">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">Từ khóa tìm kiếm</span>
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-tertiary"
            aria-hidden
          />
          <input
            type="search"
            value={queryText}
            onChange={(e) => setQueryText(e.target.value)}
            placeholder="Tìm trong tài liệu workspace…"
            disabled={loading}
            className={cn(
              "h-11 w-full rounded-md border border-border-default bg-base pl-9 pr-3 text-body-sm text-primary",
              "placeholder:text-tertiary focus:border-accent-primary focus:outline-none focus:ring-2 focus:ring-accent-primary/20",
              "disabled:cursor-not-allowed disabled:opacity-60",
            )}
          />
        </label>
        <button
          type="submit"
          disabled={loading || !queryText.trim()}
          className={cn(
            "inline-flex h-11 items-center justify-center gap-2 rounded-md px-5 text-body-sm font-medium",
            "bg-accent-primary text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
          Tìm kiếm
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className="text-caption font-medium text-secondary">Định dạng</span>
          <select
            value={fileType}
            onChange={(e) => setFileType(e.target.value as FileType | "")}
            disabled={loading}
            className="h-10 rounded-md border border-border-default bg-base px-3 text-body-sm text-primary"
          >
            {FILE_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value || "all"} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-caption font-medium text-secondary">Từ ngày</span>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            disabled={loading}
            className="h-10 rounded-md border border-border-default bg-base px-3 text-body-sm text-primary"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-caption font-medium text-secondary">Đến ngày</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            disabled={loading}
            className="h-10 rounded-md border border-border-default bg-base px-3 text-body-sm text-primary"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-caption font-medium text-secondary">Tags</span>
          <input
            type="text"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            disabled={loading}
            placeholder="tag1, tag2"
            title="Tags được lưu trong lịch sử; schema hiện chưa hỗ trợ lọc theo tag"
            className="h-10 rounded-md border border-border-default bg-base px-3 text-body-sm text-primary placeholder:text-tertiary"
          />
        </label>
      </div>
    </form>
  );
}

/** Remount-friendly form that accepts a forced query from history clicks. */
export function SearchFormWithQuery({
  queryKey,
  loading,
  onSubmit,
}: {
  queryKey: string;
  loading?: boolean;
  onSubmit: (values: SearchFormValues) => void;
}) {
  return (
    <SearchForm key={queryKey} initialQuery={queryKey} loading={loading} onSubmit={onSubmit} />
  );
}
