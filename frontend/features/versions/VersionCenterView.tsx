/**
 * =============================================================================
 * File: VersionCenterView.tsx
 * Module/Service: Document Ingestion Service (Web App)
 * Layer: UI
 * Purpose: Workspace page for document updates, version details, history, and rollback.
 * Responsibilities:
 *   - List every document version with status, checksum, uploader, and labels
 *   - Show the append-only edit history (upload, rollback, tags, metadata)
 *   - Let editors restore a ready version and save classification labels
 * Dependencies:
 *   - lib/api-client, components/ui/confirm-dialog, features/shell/AppShell
 * Public Exports:
 *   - VersionCenterView
 * Database/Table: document_versions, document_version_events
 * Related Modules: app/workspaces/[id]/versions/page.tsx, features/shell/Sidebar
 * Important Notes: Viewers can read. Rollback and label edits require editor.
 * =============================================================================
 */

"use client";

import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  History,
  RotateCcw,
  Search,
  Tag,
  Undo2,
  Upload,
  UploadCloud,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { FileTypeIcon } from "@/features/documents/FileTypeIcon";
import { UpdateDocumentDialog } from "@/features/versions/UpdateDocumentDialog";
import { AppShell } from "@/features/shell/AppShell";
import { useAuth } from "@/hooks/useAuth";
import {
  ApiClientError,
  listVersionHistory,
  listWorkspaceVersions,
  rollbackDocumentVersion,
  updateVersionClassification,
} from "@/lib/api-client";
import { canUploadDocuments } from "@/lib/rbac";
import { formatBytes } from "@/lib/upload-constraints";
import { cn } from "@/lib/utils";
import type { DocumentVersionStatus } from "@/types/documents";
import type { VersionCatalogItem, VersionEvent, VersionEventType } from "@/types/versions";

type Props = {
  workspaceId: string;
  initialDocumentId?: string | null;
};

type Tab = "catalog" | "history";
type MetaRow = { id: string; key: string; value: string };

const PAGE_SIZE = 20;

const STATUS_LABEL: Record<DocumentVersionStatus, string> = {
  ready: "Sẵn sàng",
  processing: "Đang xử lý",
  failed: "Thất bại",
};

const REPLACED_LABEL = "Đã thay thế";

function versionStatusLabel(item: { is_current: boolean; status: DocumentVersionStatus }): string {
  if (!item.is_current && item.status === "ready") return REPLACED_LABEL;
  return STATUS_LABEL[item.status];
}

const EVENT_LABEL: Record<VersionEventType, string> = {
  uploaded: "Tải lên",
  rolled_back: "Khôi phục",
  tags_updated: "Thẻ",
  metadata_updated: "Metadata",
};

function formatDateTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiClientError ? err.message : fallback;
}

function metaRowsFrom(item: VersionCatalogItem): MetaRow[] {
  return Object.entries(item.classification_metadata).map(([key, value], index) => ({
    id: `${item.id}-${index}-${key}`,
    key,
    value,
  }));
}

function EventIcon({ type }: { type: VersionEventType }) {
  const className = "h-4 w-4";
  if (type === "uploaded") return <Upload className={className} aria-hidden />;
  if (type === "rolled_back") return <Undo2 className={className} aria-hidden />;
  if (type === "tags_updated") return <Tag className={className} aria-hidden />;
  return <History className={className} aria-hidden />;
}

export function VersionCenterView({ workspaceId, initialDocumentId = null }: Props) {
  const router = useRouter();
  const { user } = useAuth();
  const canEdit = canUploadDocuments(user, workspaceId);

  const [tab, setTab] = useState<Tab>("catalog");
  const [documentId, setDocumentId] = useState<string | null>(initialDocumentId);
  const [draftQuery, setDraftQuery] = useState("");
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [historyPage, setHistoryPage] = useState(1);

  const [items, setItems] = useState<VersionCatalogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [events, setEvents] = useState<VersionEvent[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [tagDraft, setTagDraft] = useState("");
  const [metaRows, setMetaRows] = useState<MetaRow[]>([]);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const [rollbackTarget, setRollbackTarget] = useState<VersionCatalogItem | null>(null);
  const [rollingBack, setRollingBack] = useState(false);
  const [rollbackError, setRollbackError] = useState<string | null>(null);
  const [updateOpen, setUpdateOpen] = useState(false);
  const [updatePreset, setUpdatePreset] = useState<{
    id: string;
    title: string;
    file_type: VersionCatalogItem["file_type"];
  } | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const pendingSelectRef = useRef<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(draftQuery.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [draftQuery]);

  useEffect(() => {
    setPage(1);
    setHistoryPage(1);
  }, [query, tag, documentId]);

  const loadCatalog = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkspaceVersions(workspaceId, {
        page,
        pageSize: PAGE_SIZE,
        query,
        tag,
        documentId,
      });
      setItems(data.items);
      setTotal(data.total);
      setAvailableTags(data.available_tags);
    } catch (err) {
      setItems([]);
      setTotal(0);
      setError(errorMessage(err, "Không tải được danh sách phiên bản."));
    } finally {
      setLoading(false);
    }
  }, [workspaceId, page, query, tag, documentId, refreshTick]);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const data = await listVersionHistory(workspaceId, {
        page: historyPage,
        pageSize: PAGE_SIZE,
        query,
        documentId,
      });
      setEvents(data.items);
      setHistoryTotal(data.total);
    } catch (err) {
      setEvents([]);
      setHistoryTotal(0);
      setHistoryError(errorMessage(err, "Không tải được lịch sử chỉnh sửa."));
    } finally {
      setHistoryLoading(false);
    }
  }, [workspaceId, historyPage, query, documentId, refreshTick]);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    const pendingId = pendingSelectRef.current;
    if (pendingId) {
      if (items.some((item) => item.id === pendingId)) {
        setSelectedId(pendingId);
        pendingSelectRef.current = null;
      }
      return;
    }
    if (selectedId && items.some((item) => item.id === selectedId)) return;
    setSelectedId(items[0]?.id ?? null);
  }, [items, selectedId]);

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId],
  );

  useEffect(() => {
    if (!selected) return;
    setNote(selected.change_note ?? "");
    setTags(selected.tags);
    setMetaRows(metaRowsFrom(selected));
    setTagDraft("");
    setFormError(null);
  }, [selected]);

  function clearDocumentFilter() {
    setDocumentId(null);
    router.replace(`/workspaces/${workspaceId}/versions`);
  }

  function addTag(raw: string) {
    const next = raw.trim().toLocaleLowerCase("vi");
    if (!next || tags.includes(next)) return;
    setTags((current) => [...current, next]);
    setTagDraft("");
  }

  function addMetaRow() {
    setMetaRows((rows) => [...rows, { id: crypto.randomUUID(), key: "", value: "" }]);
  }

  async function saveClassification() {
    if (!selected) return;
    const metadata: Record<string, string> = {};
    for (const row of metaRows) {
      const key = row.key.trim();
      if (!key && !row.value.trim()) continue;
      if (!key) {
        setFormError("Mỗi metadata cần có tên trường.");
        return;
      }
      metadata[key] = row.value.trim();
    }
    setSaving(true);
    setFormError(null);
    try {
      await updateVersionClassification(workspaceId, selected.document_id, selected.id, {
        tags,
        classification_metadata: metadata,
        change_note: note.trim() ? note.trim() : null,
      });
      setBanner(`Đã lưu phân loại cho v${selected.version_number} · ${selected.document_title}.`);
      await Promise.all([loadCatalog(), loadHistory()]);
    } catch (err) {
      setFormError(errorMessage(err, "Không lưu được phân loại."));
    } finally {
      setSaving(false);
    }
  }

  async function confirmRollback() {
    if (!rollbackTarget) return;
    setRollingBack(true);
    setRollbackError(null);
    try {
      await rollbackDocumentVersion(
        workspaceId,
        rollbackTarget.document_id,
        rollbackTarget.id,
      );
      setBanner(
        `Đã khôi phục v${rollbackTarget.version_number} của “${rollbackTarget.document_title}” làm bản hiện hành.`,
      );
      setRollbackTarget(null);
      await Promise.all([loadCatalog(), loadHistory()]);
    } catch (err) {
      const message = errorMessage(err, "Không khôi phục được phiên bản.");
      setRollbackError(message);
    } finally {
      setRollingBack(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const historyPages = Math.max(1, Math.ceil(historyTotal / PAGE_SIZE));

  return (
    <AppShell active="versions" user={user} workspaceId={workspaceId}>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-caption font-medium text-accent-primary">Knowledge</p>
            <h1 className="text-h1 text-primary">Phiên bản</h1>
            <p className="mt-1 max-w-2xl text-body-sm text-secondary">
              Cập nhật tài liệu để tạo phiên bản mới, xem lịch sử chỉnh sửa, rồi khôi phục
              bản cũ khi cần. Thẻ và metadata dùng để phân loại từng phiên bản.
            </p>
          </div>
          {canEdit ? (
            <button
              type="button"
              onClick={() => {
                setUpdatePreset(null);
                setUpdateOpen(true);
              }}
              className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-accent-primary px-4 text-body-sm font-medium text-white hover:bg-accent-primary-hover"
            >
              <UploadCloud className="h-4 w-4" aria-hidden />
              Cập nhật tài liệu
            </button>
          ) : null}
        </header>

        {banner ? (
          <div className="flex items-start justify-between gap-3 rounded-md border border-border-default bg-success/10 px-4 py-3 text-body-sm text-primary">
            <p>{banner}</p>
            <button
              type="button"
              onClick={() => setBanner(null)}
              aria-label="Đóng thông báo"
              className="text-secondary hover:text-primary"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>
        ) : null}

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative max-w-md flex-1">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-tertiary"
                aria-hidden
              />
              <label htmlFor="version-search" className="sr-only">
                Tìm phiên bản
              </label>
              <input
                id="version-search"
                value={draftQuery}
                onChange={(event) => setDraftQuery(event.target.value)}
                placeholder="Tìm theo tên tài liệu, ghi chú hoặc thẻ…"
                className="h-10 w-full rounded-md border border-border-default bg-surface pr-3 pl-9 text-body-sm text-primary outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20"
              />
            </div>
            <div
              role="tablist"
              aria-label="Chế độ xem phiên bản"
              className="flex rounded-md border border-border-default bg-surface p-1"
            >
              {(
                [
                  ["catalog", "Phiên bản"],
                  ["history", "Lịch sử chỉnh sửa"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={tab === value}
                  onClick={() => setTab(value)}
                  className={cn(
                    "rounded px-3 py-1.5 text-body-sm font-medium",
                    tab === value
                      ? "bg-accent-primary-soft text-accent-primary"
                      : "text-secondary hover:text-primary",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {documentId ? (
            <div className="flex items-center justify-between gap-3 rounded-md border border-border-default bg-elevated/50 px-3 py-2 text-body-sm text-secondary">
              <span>Đang xem phiên bản của một tài liệu.</span>
              <button
                type="button"
                onClick={clearDocumentFilter}
                className="font-medium text-accent-primary hover:underline"
              >
                Xem tất cả
              </button>
            </div>
          ) : null}

          {tab === "catalog" && availableTags.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-caption font-medium text-tertiary">Thẻ</span>
              <button
                type="button"
                onClick={() => setTag(null)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-caption font-medium",
                  tag === null
                    ? "bg-accent-primary text-white"
                    : "bg-elevated text-secondary hover:text-primary",
                )}
              >
                Tất cả
              </button>
              {availableTags.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setTag(item)}
                  className={cn(
                    "rounded-full px-2.5 py-1 text-caption font-medium",
                    tag === item
                      ? "bg-accent-primary text-white"
                      : "bg-elevated text-secondary hover:text-primary",
                  )}
                >
                  {item}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        {tab === "history" ? (
          <HistoryPanel
            events={events}
            loading={historyLoading}
            error={historyError}
            page={historyPage}
            totalPages={historyPages}
            total={historyTotal}
            workspaceId={workspaceId}
            onRetry={() => void loadHistory()}
            onPage={setHistoryPage}
          />
        ) : error ? (
          <ErrorBanner message={error} onRetry={() => void loadCatalog()} />
        ) : (
          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
            <section className="overflow-hidden rounded-md border border-border-default bg-surface">
              <div className="flex items-center justify-between border-b border-border-default px-4 py-2.5">
                <p className="text-caption font-medium tracking-wide text-tertiary uppercase">
                  Danh sách phiên bản
                </p>
                <p className="text-caption text-tertiary">
                  {loading ? "Đang tải…" : `${total} phiên bản`}
                </p>
              </div>
              <ul className="divide-y divide-border-default">
                {loading ? (
                  Array.from({ length: 5 }).map((_, index) => (
                    <li key={index} className="px-4 py-3.5">
                      <div className="h-4 w-2/5 animate-pulse rounded bg-elevated" />
                      <div className="mt-2 h-3 w-1/3 animate-pulse rounded bg-elevated" />
                    </li>
                  ))
                ) : items.length === 0 ? (
                  <li className="px-4 py-12 text-center text-body-sm text-secondary">
                    Không có phiên bản nào khớp bộ lọc.
                  </li>
                ) : (
                  items.map((item) => {
                    const active = item.id === selectedId;
                    const replaced = !item.is_current;
                    return (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedId(item.id)}
                          className={cn(
                            "flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors",
                            replaced
                              ? "bg-elevated/30 text-tertiary opacity-60 grayscale hover:opacity-80"
                              : active
                                ? "bg-accent-primary-soft/60"
                                : "hover:bg-elevated/50",
                            replaced && active && "opacity-80 ring-1 ring-inset ring-border-default",
                          )}
                        >
                          <FileTypeIcon fileType={item.file_type} />
                          <span className="min-w-0 flex-1">
                            <span className="flex flex-wrap items-center gap-2">
                              <span
                                className={cn(
                                  "truncate text-body-sm font-medium",
                                  replaced ? "text-tertiary" : "text-primary",
                                )}
                              >
                                {item.document_title}
                              </span>
                              <span
                                className={cn(
                                  "text-caption font-semibold",
                                  replaced ? "text-tertiary" : "text-secondary",
                                )}
                              >
                                v{item.version_number}
                              </span>
                              {item.is_current ? (
                                <span className="rounded-full bg-accent-primary-soft px-2 py-0.5 text-caption font-semibold text-accent-primary">
                                  Bản hiện hành
                                </span>
                              ) : null}
                            </span>
                            <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-caption text-tertiary">
                              <span>{formatDateTime(item.created_at)}</span>
                              <span aria-hidden>·</span>
                              <span>{formatBytes(item.file_size_bytes)}</span>
                              <span aria-hidden>·</span>
                              <span>{versionStatusLabel(item)}</span>
                            </span>
                            {item.tags.length > 0 ? (
                              <span className="mt-2 flex flex-wrap gap-1">
                                {item.tags.map((itemTag) => (
                                  <span
                                    key={itemTag}
                                    className="rounded-full bg-elevated px-2 py-0.5 text-caption text-secondary"
                                  >
                                    {itemTag}
                                  </span>
                                ))}
                              </span>
                            ) : null}
                          </span>
                        </button>
                      </li>
                    );
                  })
                )}
              </ul>
              {!loading && totalPages > 1 ? (
                <Pager
                  page={page}
                  totalPages={totalPages}
                  onPage={setPage}
                />
              ) : null}
            </section>

            <VersionDetail
              item={selected}
              workspaceId={workspaceId}
              canEdit={canEdit}
              note={note}
              tags={tags}
              tagDraft={tagDraft}
              metaRows={metaRows}
              saving={saving}
              formError={formError}
              onNote={setNote}
              onTagDraft={setTagDraft}
              onAddTag={addTag}
              onRemoveTag={(value) => setTags((current) => current.filter((item) => item !== value))}
              onMetaRows={setMetaRows}
              onAddMeta={addMetaRow}
              onSave={() => void saveClassification()}
              onUpdate={() => {
                if (!selected) return;
                setUpdatePreset({
                  id: selected.document_id,
                  title: selected.document_title,
                  file_type: selected.file_type,
                });
                setUpdateOpen(true);
              }}
              onRollback={(item) => {
                setRollbackError(null);
                setRollbackTarget(item);
              }}
            />
          </div>
        )}
      </div>

      <UpdateDocumentDialog
        open={updateOpen}
        workspaceId={workspaceId}
        initialDocument={updatePreset}
        onClose={() => setUpdateOpen(false)}
        onUploaded={(version, documentTitle) => {
          pendingSelectRef.current = version.id;
          setPage(1);
          setHistoryPage(1);
          setTag(null);
          setUpdateOpen(false);
          setBanner(
            `Đã tạo v${version.version_number} cho “${documentTitle}”. Bản này là bản hiện hành — các bản cũ vẫn khôi phục được.`,
          );
          setRefreshTick((tick) => tick + 1);
        }}
      />

      <ConfirmDialog
        open={rollbackTarget !== null}
        variant="primary"
        title={
          rollbackTarget
            ? `Khôi phục v${rollbackTarget.version_number}?`
            : "Khôi phục phiên bản"
        }
        description="Bản này sẽ trở thành bản hiện hành. Chat và tìm kiếm sau đó dùng nội dung của phiên bản được khôi phục. Các phiên bản khác vẫn được giữ trong lịch sử."
        confirmLabel="Khôi phục"
        confirming={rollingBack}
        error={rollbackError}
        onConfirm={() => void confirmRollback()}
        onCancel={() => {
          if (!rollingBack) setRollbackTarget(null);
        }}
      />
    </AppShell>
  );
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-border-default bg-danger-soft px-4 py-3 text-body-sm text-danger"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="flex flex-col gap-2">
        <span>{message}</span>
        <button type="button" onClick={onRetry} className="w-fit font-medium underline">
          Thử lại
        </button>
      </div>
    </div>
  );
}

function Pager({
  page,
  totalPages,
  onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
}) {
  return (
    <div className="flex items-center justify-between border-t border-border-default px-4 py-3">
      <p className="text-caption text-tertiary">
        Trang {page} / {totalPages}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          className="flex h-9 items-center gap-1 rounded-md border border-border-default px-3 text-body-sm font-medium text-secondary hover:bg-elevated disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden />
          Trước
        </button>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPage(page + 1)}
          className="flex h-9 items-center gap-1 rounded-md border border-border-default px-3 text-body-sm font-medium text-secondary hover:bg-elevated disabled:cursor-not-allowed disabled:opacity-50"
        >
          Sau
          <ChevronRight className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </div>
  );
}

function HistoryPanel({
  events,
  loading,
  error,
  page,
  totalPages,
  total,
  workspaceId,
  onRetry,
  onPage,
}: {
  events: VersionEvent[];
  loading: boolean;
  error: string | null;
  page: number;
  totalPages: number;
  total: number;
  workspaceId: string;
  onRetry: () => void;
  onPage: (page: number) => void;
}) {
  if (error) return <ErrorBanner message={error} onRetry={onRetry} />;
  return (
    <section className="overflow-hidden rounded-md border border-border-default bg-surface">
      <div className="flex items-center justify-between border-b border-border-default px-4 py-2.5">
        <p className="text-caption font-medium tracking-wide text-tertiary uppercase">
          Lịch sử chỉnh sửa
        </p>
        <p className="text-caption text-tertiary">{loading ? "Đang tải…" : `${total} sự kiện`}</p>
      </div>
      <ol className="divide-y divide-border-default">
        {loading ? (
          Array.from({ length: 4 }).map((_, index) => (
            <li key={index} className="px-4 py-4">
              <div className="h-4 w-1/2 animate-pulse rounded bg-elevated" />
              <div className="mt-2 h-3 w-1/3 animate-pulse rounded bg-elevated" />
            </li>
          ))
        ) : events.length === 0 ? (
          <li className="px-4 py-12 text-center text-body-sm text-secondary">
            Chưa có lịch sử chỉnh sửa.
          </li>
        ) : (
          events.map((event) => (
            <li key={event.id} className="flex gap-3 px-4 py-4">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-elevated text-secondary">
                <EventIcon type={event.event_type} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-elevated px-2 py-0.5 text-caption font-medium text-secondary">
                    {EVENT_LABEL[event.event_type] ?? event.event_type}
                  </span>
                  <p className="text-body-sm font-medium text-primary">{event.summary}</p>
                </div>
                <p className="mt-1 text-caption text-tertiary">
                  <Link
                    href={`/workspaces/${workspaceId}/documents/${event.document_id}`}
                    className="font-medium text-secondary hover:text-accent-primary"
                  >
                    {event.document_title}
                  </Link>
                  <span aria-hidden> · </span>
                  v{event.version_number}
                  <span aria-hidden> · </span>
                  {event.actor_name ?? "Người dùng"}
                  <span aria-hidden> · </span>
                  {formatDateTime(event.created_at)}
                </p>
              </div>
            </li>
          ))
        )}
      </ol>
      {!loading && totalPages > 1 ? (
        <Pager page={page} totalPages={totalPages} onPage={onPage} />
      ) : null}
    </section>
  );
}

function VersionDetail({
  item,
  workspaceId,
  canEdit,
  note,
  tags,
  tagDraft,
  metaRows,
  saving,
  formError,
  onNote,
  onTagDraft,
  onAddTag,
  onRemoveTag,
  onMetaRows,
  onAddMeta,
  onSave,
  onUpdate,
  onRollback,
}: {
  item: VersionCatalogItem | null;
  workspaceId: string;
  canEdit: boolean;
  note: string;
  tags: string[];
  tagDraft: string;
  metaRows: MetaRow[];
  saving: boolean;
  formError: string | null;
  onNote: (value: string) => void;
  onTagDraft: (value: string) => void;
  onAddTag: (value: string) => void;
  onRemoveTag: (value: string) => void;
  onMetaRows: (rows: MetaRow[]) => void;
  onAddMeta: () => void;
  onSave: () => void;
  onUpdate: () => void;
  onRollback: (item: VersionCatalogItem) => void;
}) {
  if (!item) {
    return (
      <aside className="rounded-md border border-dashed border-border-default bg-surface px-4 py-10 text-center text-body-sm text-secondary">
        Chọn một phiên bản để xem checksum, người tải lên, thẻ và metadata.
      </aside>
    );
  }

  const replaced = !item.is_current;
  const canRollback = canEdit && replaced && item.status === "ready";
  const uploader = item.uploader_name || item.uploader_email || item.uploaded_by.slice(0, 8);

  return (
    <aside
      className={cn(
        "flex flex-col gap-4 rounded-md border border-border-default p-4",
        replaced ? "bg-elevated/40 text-tertiary" : "bg-surface",
      )}
    >
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-caption font-medium text-tertiary">v{item.version_number}</p>
          {item.is_current ? (
            <span className="rounded-full bg-accent-primary-soft px-2 py-0.5 text-caption font-semibold text-accent-primary">
              Bản hiện hành
            </span>
          ) : (
            <span className="rounded-full bg-elevated px-2 py-0.5 text-caption font-medium text-tertiary">
              {versionStatusLabel(item)}
            </span>
          )}
        </div>
        <h2 className={cn("mt-1 text-h3", replaced ? "text-tertiary" : "text-primary")}>
          {item.document_title}
        </h2>
        <Link
          href={`/workspaces/${workspaceId}/documents/${item.document_id}`}
          className="mt-1 inline-block text-caption font-medium text-accent-primary hover:underline"
        >
          Mở tài liệu
        </Link>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-caption">
        <div>
          <dt className="text-tertiary">Trạng thái</dt>
          <dd className={cn("mt-0.5 font-medium", replaced ? "text-tertiary" : "text-primary")}>
            {versionStatusLabel(item)}
          </dd>
        </div>
        <div>
          <dt className="text-tertiary">Kích thước</dt>
          <dd className="mt-0.5 font-medium text-primary">{formatBytes(item.file_size_bytes)}</dd>
        </div>
        <div>
          <dt className="text-tertiary">Số trang</dt>
          <dd className="mt-0.5 font-medium text-primary">{item.page_count ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-tertiary">Người tải lên</dt>
          <dd className="mt-0.5 truncate font-medium text-primary" title={uploader}>
            {uploader}
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="text-tertiary">Checksum SHA-256</dt>
          <dd className="mt-0.5 break-all font-mono text-[11px] text-secondary">
            {item.checksum_sha256}
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="text-tertiary">Tạo lúc</dt>
          <dd className="mt-0.5 font-medium text-primary">{formatDateTime(item.created_at)}</dd>
        </div>
      </dl>

      <label className="flex flex-col gap-1.5 text-caption font-medium text-secondary">
        Ghi chú thay đổi
        <textarea
          value={note}
          disabled={!canEdit}
          onChange={(event) => onNote(event.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="Mô tả ngắn những gì thay đổi ở phiên bản này"
          className="rounded-md border border-border-default bg-base px-3 py-2 text-body-sm font-normal text-primary outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20 disabled:opacity-60"
        />
      </label>

      <div>
        <p className="text-caption font-medium text-secondary">Thẻ phân loại</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {tags.map((value) => (
            <span
              key={value}
              className="inline-flex items-center gap-1 rounded-full bg-elevated px-2 py-1 text-caption text-primary"
            >
              {value}
              {canEdit ? (
                <button
                  type="button"
                  aria-label={`Xóa thẻ ${value}`}
                  onClick={() => onRemoveTag(value)}
                  className="text-tertiary hover:text-danger"
                >
                  <X className="h-3 w-3" aria-hidden />
                </button>
              ) : null}
            </span>
          ))}
        </div>
        {canEdit ? (
          <input
            value={tagDraft}
            onChange={(event) => onTagDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === ",") {
                event.preventDefault();
                onAddTag(tagDraft);
              }
            }}
            placeholder="Nhập thẻ rồi nhấn Enter"
            className="mt-2 h-9 w-full rounded-md border border-border-default bg-base px-3 text-body-sm text-primary outline-none focus:border-accent-primary focus:ring-2 focus:ring-accent-primary/20"
          />
        ) : null}
      </div>

      <div>
        <div className="flex items-center justify-between">
          <p className="text-caption font-medium text-secondary">Metadata</p>
          {canEdit ? (
            <button
              type="button"
              onClick={onAddMeta}
              className="text-caption font-medium text-accent-primary hover:underline"
            >
              Thêm trường
            </button>
          ) : null}
        </div>
        <div className="mt-2 flex flex-col gap-2">
          {metaRows.length === 0 ? (
            <p className="text-caption text-tertiary">Chưa có metadata phân loại.</p>
          ) : (
            metaRows.map((row) => (
              <div key={row.id} className="flex gap-2">
                <input
                  value={row.key}
                  disabled={!canEdit}
                  aria-label="Tên trường metadata"
                  onChange={(event) =>
                    onMetaRows(
                      metaRows.map((item) =>
                        item.id === row.id ? { ...item, key: event.target.value } : item,
                      ),
                    )
                  }
                  placeholder="Trường"
                  className="h-9 w-1/2 rounded-md border border-border-default bg-base px-2 text-caption text-primary outline-none focus:border-accent-primary disabled:opacity-60"
                />
                <input
                  value={row.value}
                  disabled={!canEdit}
                  aria-label="Giá trị metadata"
                  onChange={(event) =>
                    onMetaRows(
                      metaRows.map((item) =>
                        item.id === row.id ? { ...item, value: event.target.value } : item,
                      ),
                    )
                  }
                  placeholder="Giá trị"
                  className="h-9 min-w-0 flex-1 rounded-md border border-border-default bg-base px-2 text-caption text-primary outline-none focus:border-accent-primary disabled:opacity-60"
                />
              </div>
            ))
          )}
        </div>
      </div>

      {formError ? (
        <p role="alert" className="text-caption text-danger">
          {formError}
        </p>
      ) : null}

      {!canEdit ? (
        <p className="text-caption text-tertiary">
          Bạn cần quyền editor để cập nhật tài liệu, khôi phục phiên bản hoặc sửa phân loại.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={onUpdate}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-accent-primary/40 bg-accent-primary-soft px-4 text-body-sm font-medium text-accent-primary hover:bg-accent-primary/15"
          >
            <UploadCloud className="h-4 w-4" aria-hidden />
            Cập nhật tài liệu này
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="inline-flex h-10 items-center justify-center rounded-md bg-accent-primary px-4 text-body-sm font-medium text-white hover:bg-accent-primary-hover disabled:opacity-60"
          >
            {saving ? "Đang lưu…" : "Lưu phân loại"}
          </button>
          <button
            type="button"
            disabled={!canRollback}
            onClick={() => onRollback(item)}
            title={
              item.is_current
                ? "Đây đã là bản hiện hành"
                : item.status !== "ready"
                  ? "Chỉ khôi phục được phiên bản đã sẵn sàng"
                  : undefined
            }
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border-default px-4 text-body-sm font-medium text-secondary hover:bg-elevated hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCcw className="h-4 w-4" aria-hidden />
            Khôi phục phiên bản này
          </button>
        </div>
      )}
    </aside>
  );
}
