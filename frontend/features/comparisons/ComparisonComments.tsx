/**
 * =============================================================================
 * File: ComparisonComments.tsx
 * Module/Service: Comparison Service (Web App)
 * Layer: UI
 * Purpose: TASK-CMP-22 reviewer comments for a comparison context.
 * Responsibilities:
 *   - List, add, edit, and delete comments for a clause / diff / evidence target
 *   - Keep reviewer notes visually separate from system analysis
 * Dependencies:
 *   - comparison-comments helpers, useAuth, design tokens
 * Public Exports:
 *   - ComparisonComments
 * Database/Table: N/A
 * Related Modules: ComparisonSummaryView, ClauseComparisonView, ComparisonEvidencePanel
 * Important Notes: Does not change clause status, risk, evidence, or AI text.
 * =============================================================================
 */

"use client";

import { Loader2, MessageSquare, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";

import {
  commentCountLabel,
  commentsForTarget,
  formatCommentMeta,
  type CommentTargetType,
} from "@/features/comparisons/comparison-comments";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";
import type { ComparisonComment } from "@/types/comparisons";

type Props = {
  clauseId: string;
  comments: ComparisonComment[] | null | undefined;
  canEdit: boolean;
  saving?: boolean;
  targetType?: CommentTargetType;
  targetId?: string | null;
  compact?: boolean;
  onCreate: (body: string, targetType: CommentTargetType, targetId?: string | null) => void;
  onUpdate: (commentId: string, body: string) => void;
  onDelete: (commentId: string) => void;
};

export function ComparisonComments({
  clauseId,
  comments,
  canEdit,
  saving = false,
  targetType = "CLAUSE",
  targetId = null,
  compact = false,
  onCreate,
  onUpdate,
  onDelete,
}: Props) {
  const { user } = useAuth();
  const rows = commentsForTarget(comments, clauseId, targetType, targetId);
  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");

  function submitNew() {
    const text = draft.trim();
    if (!text || saving) return;
    onCreate(text, targetType, targetId);
    setDraft("");
  }

  function submitEdit() {
    const text = editDraft.trim();
    if (!editingId || !text || saving) return;
    onUpdate(editingId, text);
    setEditingId(null);
    setEditDraft("");
  }

  return (
    <section
      aria-labelledby={`comments-heading-${clauseId}-${targetType}-${targetId ?? "clause"}`}
      className={cn("flex flex-col gap-2", compact && "gap-1.5")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <MessageSquare className="h-3.5 w-3.5 text-tertiary" aria-hidden />
        <h3
          id={`comments-heading-${clauseId}-${targetType}-${targetId ?? "clause"}`}
          className="text-caption font-semibold uppercase tracking-wide text-tertiary"
        >
          Ghi chú rà soát
        </h3>
        <span className="text-caption text-tertiary">{commentCountLabel(rows.length)}</span>
      </div>
      {!compact ? (
        <p className="text-caption text-tertiary">
          Ghi chú của người rà soát — không thay đổi kết quả so sánh của hệ thống.
        </p>
      ) : null}

      {rows.length === 0 ? (
        <p className="text-caption text-tertiary">Chưa có ghi chú.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((comment) => {
            const isAuthor = Boolean(user?.id && comment.author_id === user.id);
            const editing = editingId === comment.id;
            const meta = formatCommentMeta(comment);
            return (
              <li
                key={comment.id}
                className="rounded-md border border-border-default bg-elevated/40 px-3 py-2"
              >
                {meta ? <p className="text-caption text-tertiary">{meta}</p> : null}
                {editing ? (
                  <div className="mt-1.5 flex flex-col gap-1.5">
                    <textarea
                      value={editDraft}
                      onChange={(event) => setEditDraft(event.target.value)}
                      rows={3}
                      maxLength={4000}
                      className={textareaClass}
                    />
                    <div className="flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        disabled={saving || !editDraft.trim()}
                        onClick={submitEdit}
                        className={primaryButtonClass}
                      >
                        {saving ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : null}
                        Lưu
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setEditingId(null);
                          setEditDraft("");
                        }}
                        className={ghostButtonClass}
                      >
                        Huỷ
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="mt-1 whitespace-pre-wrap text-body-sm text-secondary">{comment.body}</p>
                )}
                {canEdit && !editing ? (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {isAuthor ? (
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() => {
                          setEditingId(comment.id);
                          setEditDraft(comment.body);
                        }}
                        className={ghostButtonClass}
                      >
                        <Pencil className="h-3 w-3" aria-hidden />
                        Sửa
                      </button>
                    ) : null}
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => onDelete(comment.id)}
                      className={ghostButtonClass}
                    >
                      <Trash2 className="h-3 w-3" aria-hidden />
                      Xoá
                    </button>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {canEdit ? (
        <form
          className="flex flex-col gap-1.5"
          onSubmit={(event) => {
            event.preventDefault();
            submitNew();
          }}
        >
          <label className="sr-only" htmlFor={`comment-draft-${clauseId}-${targetType}-${targetId ?? "clause"}`}>
            Thêm ghi chú rà soát
          </label>
          <textarea
            id={`comment-draft-${clauseId}-${targetType}-${targetId ?? "clause"}`}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={compact ? 2 : 3}
            maxLength={4000}
            placeholder="Thêm quan sát, câu hỏi hoặc yêu cầu làm rõ…"
            className={textareaClass}
          />
          <button
            type="submit"
            disabled={saving || !draft.trim()}
            className={cn(primaryButtonClass, "self-start")}
          >
            {saving ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : null}
            Gửi ghi chú
          </button>
        </form>
      ) : (
        <p className="text-caption text-tertiary">Chỉ editor trở lên mới thêm ghi chú.</p>
      )}
    </section>
  );
}

const textareaClass = cn(
  "w-full rounded-md border border-border-default bg-surface px-2.5 py-2",
  "text-body-sm text-primary placeholder:text-tertiary",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
);

const primaryButtonClass = cn(
  "inline-flex h-8 items-center gap-1 rounded-md border border-accent-primary/40 bg-accent-primary/10",
  "px-2.5 text-caption font-medium text-primary",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
  "disabled:cursor-not-allowed disabled:opacity-50",
);

const ghostButtonClass = cn(
  "inline-flex h-7 items-center gap-1 rounded-md border border-border-default px-2",
  "text-caption font-medium text-secondary hover:bg-elevated hover:text-primary",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
  "disabled:cursor-not-allowed disabled:opacity-50",
);
