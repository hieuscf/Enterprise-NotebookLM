/**
 * =============================================================================
 * File: CitationChip.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Interactive inline citation marker [n] with hover preview + click.
 * Responsibilities:
 *   - Keyboard accessible chip; hover/focus popover; activate source panel
 * Dependencies:
 *   - CitationPopover, ChatCitationContext, citation-session, chat-format
 * Public Exports:
 *   - CitationChip
 * Database/Table: N/A
 * Related Modules: AnswerContent, SourcePanel
 * Important Notes: Compact [n] in prose; popover shows full source context.
 * =============================================================================
 */

"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { useChatCitationUiOptional } from "@/features/chat/ChatCitationContext";
import { CitationPopover } from "@/features/chat/citation/CitationPopover";
import type { CitationViewModel } from "@/features/chat/citation/citation-types";
import { saveCitationFocus } from "@/features/chat/citation/citation-session";
import { buildChatCitationHref } from "@/features/chat/chat-format";
import { formatContentLocationLabel } from "@/lib/content-location";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  citation: CitationViewModel;
  compact?: boolean;
};

export function CitationChip({ workspaceId, citation, compact = true }: Props) {
  const router = useRouter();
  const ui = useChatCitationUiOptional();
  const popoverId = useId();
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<number | null>(null);

  const isActive = ui?.highlightedCitationId === citation.id;
  const locationLabel = formatContentLocationLabel(citation.location);

  const ariaLabel = [
    `Nguồn ${citation.displayIndex}`,
    citation.documentMissing ? "Tài liệu không còn khả dụng" : citation.documentTitle,
    locationLabel,
    citation.verified ? "đã xác thực" : "chưa xác thực",
  ]
    .filter(Boolean)
    .join(", ");

  const clearCloseTimer = () => {
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  const scheduleClose = () => {
    clearCloseTimer();
    closeTimer.current = window.setTimeout(() => {
      setOpen(false);
      ui?.setHoveredCitationId(null);
    }, 140);
  };

  const handleOpenPreview = () => {
    clearCloseTimer();
    setOpen(true);
    ui?.setHoveredCitationId(citation.id);
    if (ui) {
      ui.setPanelCitations(
        ui.panelCitations.some((c) => c.id === citation.id)
          ? ui.panelCitations
          : [...ui.panelCitations.filter((c) => c.messageId === citation.messageId), citation],
      );
    }
  };

  const openDocument = useCallback(() => {
    if (!citation.documentId || citation.documentMissing) return;
    saveCitationFocus(workspaceId, {
      citationId: citation.id,
      documentId: citation.documentId,
      textSnippet: citation.textSnippet,
      page: citation.page ?? null,
      verified: citation.verified,
      documentTitle: citation.documentTitle,
    });
    const href = buildChatCitationHref(workspaceId, {
      document_id: citation.documentId,
      page: citation.page,
      citationId: citation.id,
    });
    if (href) router.push(href);
  }, [citation, router, workspaceId]);

  const handleActivate = () => {
    ui?.activateCitation(citation, { openPanel: true });
    setOpen(false);
  };

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        ui?.setHoveredCitationId(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, ui]);

  useEffect(() => () => clearCloseTimer(), []);

  return (
    <span
      ref={wrapRef}
      className="relative inline-flex align-super"
      onMouseEnter={handleOpenPreview}
      onMouseLeave={scheduleClose}
    >
      <button
        type="button"
        aria-label={ariaLabel}
        aria-describedby={open ? popoverId : undefined}
        aria-expanded={open}
        onClick={handleActivate}
        onFocus={handleOpenPreview}
        onBlur={scheduleClose}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            handleActivate();
          }
        }}
        className={cn(
          "mx-0.5 inline-flex cursor-pointer items-center gap-0.5 rounded px-1 py-px",
          "align-super text-[11px] font-semibold leading-none transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary/40",
          citation.verified
            ? "bg-citation-soft text-citation"
            : "bg-elevated text-secondary",
          isActive && "ring-2 ring-accent-primary/35",
          "hover:bg-accent-primary-soft hover:text-accent-primary",
        )}
      >
        [{citation.displayIndex}]
        {!compact && citation.documentTitle ? (
          <span className="hidden max-w-[8rem] truncate font-medium sm:inline">
            {citation.documentTitle}
            {citation.page ? ` · p.${citation.page}` : ""}
          </span>
        ) : null}
        {citation.verified ? (
          <span className="text-[9px] text-success" aria-hidden>
            ✓
          </span>
        ) : null}
      </button>

      {open ? (
        <span
          id={popoverId}
          className="absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2"
          onMouseEnter={handleOpenPreview}
          onMouseLeave={scheduleClose}
        >
          <CitationPopover citation={citation} onOpenDocument={openDocument} />
        </span>
      ) : null}
    </span>
  );
}
