/**
 * =============================================================================
 * File: SourcePanel.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Right-hand Sources panel — group by document + active snippet preview.
 * Responsibilities:
 *   - Desktop column / tablet-mobile drawer; sync with hovered/active citation
 * Dependencies:
 *   - SourceDocumentCard, SourceSnippet, ChatCitationContext, citation-session
 * Public Exports:
 *   - SourcePanel
 * Database/Table: N/A
 * Related Modules: ChatLayout
 * Important Notes: Lazy — only mounts PDF navigation when user opens document.
 * =============================================================================
 */

"use client";

import { useRouter } from "next/navigation";
import { useMemo } from "react";
import { PanelRightClose, X } from "lucide-react";

import { useChatCitationUi } from "@/features/chat/ChatCitationContext";
import { groupCitationsByDocument } from "@/features/chat/citation/citation-mapper";
import { saveCitationFocus } from "@/features/chat/citation/citation-session";
import type { CitationViewModel } from "@/features/chat/citation/citation-types";
import { buildChatCitationHref } from "@/features/chat/chat-format";
import { SourceDocumentCard } from "@/features/chat/source/SourceDocumentCard";
import { SourceSnippet } from "@/features/chat/source/SourceSnippet";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  /** Fallback citations when panel set is empty (e.g. latest assistant message). */
  fallbackCitations?: CitationViewModel[];
  className?: string;
};

export function SourcePanel({ workspaceId, fallbackCitations = [], className }: Props) {
  const router = useRouter();
  const ui = useChatCitationUi();

  const citations =
    ui.panelCitations.length > 0 ? ui.panelCitations : fallbackCitations;

  const groups = useMemo(() => groupCitationsByDocument(citations), [citations]);

  const activeCitation = useMemo(() => {
    const id = ui.highlightedCitationId ?? ui.activeCitationId;
    if (!id) return citations[0] ?? null;
    return citations.find((c) => c.id === id) ?? citations[0] ?? null;
  }, [citations, ui.highlightedCitationId, ui.activeCitationId]);

  const openDocument = (citation: CitationViewModel) => {
    if (!citation.documentId || citation.documentMissing) return;
    saveCitationFocus(workspaceId, {
      citationId: citation.id,
      documentId: citation.documentId,
      textSnippet: citation.textSnippet,
      page: citation.page ?? null,
      chunkId: citation.chunkId ?? null,
      versionId: citation.documentVersionId ?? null,
      verified: citation.verified,
      documentTitle: citation.documentTitle,
      locator: citation.locator ?? null,
    });
    const href = buildChatCitationHref(workspaceId, {
      document_id: citation.documentId,
      page: citation.page,
      citationId: citation.id,
      chunkId: citation.chunkId,
      versionId: citation.documentVersionId,
    });
    if (href) router.push(href);
  };

  const panelBody = (
    <>
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border-default px-3 py-2.5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-tertiary">
            Sources
          </p>
          <p className="text-caption text-secondary">
            {citations.length > 0
              ? `${citations.length} nguồn · ${groups.length} tài liệu`
              : "Chưa có nguồn"}
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            ui.setSourcePanelOpen(false);
            ui.setSourcePanelMobileOpen(false);
          }}
          aria-label="Đóng bảng nguồn"
          className="flex h-8 w-8 items-center justify-center rounded-md text-secondary hover:bg-elevated hover:text-primary"
        >
          <PanelRightClose className="hidden h-4 w-4 lg:block" aria-hidden />
          <X className="h-4 w-4 lg:hidden" aria-hidden />
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
        {citations.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border-default p-4">
            <p className="text-body-sm text-secondary">
              Không tìm thấy nguồn xác thực trong tài liệu.
            </p>
            <p className="mt-1 text-caption text-tertiary">
              Câu trả lời sẽ gắn citation khi pipeline xác minh được đoạn nguồn.
            </p>
          </div>
        ) : (
          <>
            <SourceSnippet citation={activeCitation} onOpenDocument={openDocument} />
            <div className="flex flex-col gap-2">
              {groups.map((group) => (
                <SourceDocumentCard
                  key={group.documentId || group.documentTitle}
                  group={group}
                  activeCitationId={ui.activeCitationId}
                  highlightedCitationId={ui.highlightedCitationId}
                  onSelectCitation={(c) => ui.activateCitation(c, { openPanel: true })}
                  onHoverCitation={ui.setHoveredCitationId}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );

  return (
    <>
      {/* Desktop / large tablet column */}
      {ui.sourcePanelOpen ? (
        <aside
          aria-label="Bảng nguồn trích dẫn"
          className={cn(
            "hidden min-h-0 w-[min(100%,22rem)] shrink-0 flex-col border-l border-border-default bg-surface xl:flex",
            className,
          )}
        >
          {panelBody}
        </aside>
      ) : null}

      {/* Mobile / tablet drawer */}
      {ui.sourcePanelMobileOpen ? (
        <>
          <div
            aria-hidden
            className="fixed inset-0 z-40 bg-slate-950/40 xl:hidden"
            onClick={() => ui.setSourcePanelMobileOpen(false)}
          />
          <aside
            aria-label="Bảng nguồn trích dẫn"
            className={cn(
              "fixed inset-y-0 right-0 z-50 flex w-[min(100%,22rem)] flex-col bg-surface shadow-lg xl:hidden",
              className,
            )}
          >
            {panelBody}
          </aside>
        </>
      ) : null}
    </>
  );
}
