/**
 * =============================================================================
 * File: CitationSection.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Compatibility re-export — citation list UX moved to SourceSummary/Panel.
 * Responsibilities:
 *   - Keep old import path from breaking; prefer SourceSummary for new UI
 * Dependencies:
 *   - SourceSummary, citation-mapper
 * Public Exports:
 *   - CitationSection
 * Database/Table: N/A
 * Related Modules: SourceSummary, SourcePanel
 * Important Notes: Deprecated for new code — Research Workspace uses inline chips.
 * =============================================================================
 */

"use client";

import { SourceSummary } from "@/features/chat/citation/SourceSummary";
import { mapCitations } from "@/features/chat/citation/citation-mapper";
import type { Citation } from "@/types/citations";

type Props = {
  workspaceId: string;
  citations: Citation[];
};

/** @deprecated Prefer AnswerContent + SourceSummary + SourcePanel. */
export function CitationSection({ workspaceId: _workspaceId, citations }: Props) {
  void _workspaceId;
  const mapped = mapCitations(citations, new Map());
  return <SourceSummary citations={mapped} emptyHint={false} />;
}
