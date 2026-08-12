/**
 * =============================================================================
 * File: chat-format.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Pure formatting helpers for the Chat UI (no JSX, no business logic).
 * Responsibilities:
 *   - Relative "updated_at" label for the session sidebar
 *   - Session title fallback when title is NULL (contract has no preview)
 *   - Document deep-link for a Chat citation (page + citation focus when known)
 *   - Conversation date grouping labels
 * Dependencies:
 *   - types/chat, types/citations
 * Public Exports:
 *   - formatRelativeTime, sessionTitleLabel, buildChatCitationHref
 *   - citationDisplayIndex, stripLeakedCitationUuids, conversationDayLabel
 * Database/Table: N/A
 * Related Modules: features/chat/SessionSidebar, CitationChip, SourcePanel
 * Important Notes: Kept dependency-free and pure so scripts/test-chat-ui.mjs
 *   can re-implement/exercise the same logic without a bundler.
 * =============================================================================
 */

import type { ChatSession } from "@/types/chat";
import type { Citation } from "@/types/citations";

/** "Vài giây trước" / "5 phút trước" / "3 giờ trước" / "12 ngày trước" / date. */
export function formatRelativeTime(isoDate: string): string {
  const target = new Date(isoDate).getTime();
  if (Number.isNaN(target)) return "";
  const diffMs = Date.now() - target;
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec < 5) return "Vừa xong";
  if (diffSec < 60) return `${diffSec} giây trước`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} phút trước`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour} giờ trước`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return `${diffDay} ngày trước`;
  return new Date(isoDate).toLocaleDateString("vi-VN");
}

/** Sidebar title — backend title is nullable until Part 2 auto-titling ships. */
export function sessionTitleLabel(session: Pick<ChatSession, "title">): string {
  const trimmed = (session.title ?? "").trim();
  return trimmed || "Cuộc trò chuyện mới";
}

export type ChatCitationHrefInput = Pick<Citation, "document_id"> & {
  page?: number | null;
  citationId?: string | null;
};

/**
 * Deep-link to the document viewer. Optional page + citation id enable
 * highlight via sessionStorage payload (see citation-session.ts).
 */
export function buildChatCitationHref(
  workspaceId: string,
  citation: ChatCitationHrefInput,
): string | null {
  if (!citation.document_id) return null;
  const params = new URLSearchParams();
  if (citation.page != null && citation.page > 0) {
    params.set("page", String(citation.page));
  }
  if (citation.citationId) {
    params.set("citation", citation.citationId);
  }
  const qs = params.toString();
  const base = `/workspaces/${workspaceId}/documents/${citation.document_id}`;
  return qs ? `${base}?${qs}` : base;
}

/** 1-based presentation index from order_index (stable across sorts). */
export function citationDisplayIndex(citation: Pick<Citation, "order_index">): number {
  return Math.max(1, Number(citation.order_index) + 1);
}

/**
 * Defense-in-depth: strip any leftover bracketed UUIDs from answer prose
 * (backend should already rewrite/remove these before persist/stream).
 */
export function stripLeakedCitationUuids(content: string): string {
  return content.replace(
    /\[\s*[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\s*\]/g,
    "",
  );
}

/** Local calendar day key YYYY-MM-DD for grouping sessions. */
export function conversationDayKey(isoDate: string, now = new Date()): string {
  const d = new Date(isoDate);
  if (Number.isNaN(d.getTime())) return "unknown";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  void now;
  return `${y}-${m}-${day}`;
}

export function conversationDayLabel(isoDate: string, now = new Date()): string {
  const d = new Date(isoDate);
  if (Number.isNaN(d.getTime())) return "Trước đây";

  const startOf = (date: Date) =>
    new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const dayMs = 24 * 60 * 60 * 1000;
  const diffDays = Math.round((startOf(now) - startOf(d)) / dayMs);

  if (diffDays === 0) return "Hôm nay";
  if (diffDays === 1) return "Hôm qua";
  if (diffDays < 7) return "Tuần này";
  return d.toLocaleDateString("vi-VN", { day: "numeric", month: "short", year: "numeric" });
}

export type SessionDayGroup = {
  key: string;
  label: string;
  sessions: ChatSession[];
};

/** Group sessions by local day while preserving input order within each group. */
export function groupSessionsByDay(
  sessions: ChatSession[],
  now = new Date(),
): SessionDayGroup[] {
  const groups: SessionDayGroup[] = [];
  const indexByKey = new Map<string, number>();

  for (const session of sessions) {
    const key = conversationDayKey(session.updated_at, now);
    const existing = indexByKey.get(key);
    if (existing == null) {
      indexByKey.set(key, groups.length);
      groups.push({
        key,
        label: conversationDayLabel(session.updated_at, now),
        sessions: [session],
      });
    } else {
      groups[existing].sessions.push(session);
    }
  }
  return groups;
}
