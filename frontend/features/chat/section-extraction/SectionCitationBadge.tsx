/**
 * =============================================================================
 * File: SectionCitationBadge.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Compact per-section citation control (page label + hover details).
 * Responsibilities:
 *   - Show "Trang N ↗" (or location label) without a bulky verified row
 *   - Keep popover + document open behaviour of CitationChip
 * Dependencies:
 *   - CitationChip, formatContentLocationLabel
 * Public Exports:
 *   - SectionCitationBadge
 * Database/Table: N/A
 * Related Modules: SectionItem, CitationChip
 * Important Notes: Click still opens the source chunk/page via existing citation flow.
 * =============================================================================
 */

"use client";

import { CitationChip } from "@/features/chat/citation/CitationChip";
import type { CitationViewModel } from "@/features/chat/citation/citation-types";

type Props = {
  workspaceId: string;
  citations: CitationViewModel[];
};

export function SectionCitationBadge({ workspaceId, citations }: Props) {
  if (citations.length === 0) return null;

  return (
    <span className="inline-flex flex-wrap items-center justify-end gap-1">
      {citations.map((citation) => (
        <CitationChip
          key={citation.id}
          workspaceId={workspaceId}
          citation={citation}
          variant="page"
        />
      ))}
    </span>
  );
}
