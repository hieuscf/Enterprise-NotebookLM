/**
 * =============================================================================
 * File: chat-format.ts
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Pure formatting helpers for the Chat UI (no JSX, no business logic).
 * Responsibilities:
 *   - Relative "updated_at" label for the session sidebar
 *   - Session title fallback when title is NULL (contract has no preview)
 *   - Document deep-link for a Chat citation (document-level only — Chat's
 *     Citation schema carries no chunk_id/location, unlike Search results)
 * Dependencies:
 *   - types/chat, types/citations
 * Public Exports:
 *   - formatRelativeTime, sessionTitleLabel, buildChatCitationHref
 * Database/Table: N/A
 * Related Modules: features/chat/SessionSidebar, CitationSection
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

/**
 * Chat's Citation has no chunk_id/location (unlike Search results), so we can
 * only deep-link to the document itself, not a specific page/chunk.
 */
export function buildChatCitationHref(
  workspaceId: string,
  citation: Pick<Citation, "document_id">,
): string | null {
  if (!citation.document_id) return null;
  return `/workspaces/${workspaceId}/documents/${citation.document_id}`;
}
