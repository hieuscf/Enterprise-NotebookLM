/**
 * =============================================================================
 * File: SectionTitle.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Subsection heading row (number + title + compact citation).
 * Responsibilities:
 *   - Keep section number as semantic text, never wrap in <ol>/<li>
 * Dependencies:
 *   - SectionHeader
 * Public Exports:
 *   - SectionTitle
 * Database/Table: N/A
 * Related Modules: SectionItem
 * Important Notes: Do not use CSS counters or list-style-type decimal here.
 * =============================================================================
 */

import { SectionHeader } from "@/features/chat/section-extraction/SectionHeader";
import type { ReactNode } from "react";

type Props = {
  number: string | null;
  title: string;
  depth: number;
  trailing?: ReactNode;
};

export function SectionTitle({ number, title, depth, trailing }: Props) {
  return (
    <div
      className="flex items-start justify-between gap-3"
      data-section-number={number ?? undefined}
    >
      <SectionHeader number={number} title={title} depth={depth} className="min-w-0 flex-1" />
      {trailing ? <div className="shrink-0 pt-0.5">{trailing}</div> : null}
    </div>
  );
}
