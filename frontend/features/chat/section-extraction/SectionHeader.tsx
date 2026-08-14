/**
 * =============================================================================
 * File: SectionHeader.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Root / parent heading for a section_extraction outline.
 * Responsibilities:
 *   - Render section number + title without ordered-list numbering
 * Dependencies:
 *   - formatSectionHeading
 * Public Exports:
 *   - SectionHeader
 * Database/Table: N/A
 * Related Modules: SectionExtractionAnswer
 * Important Notes: Section number is a document identifier, not a list index.
 * =============================================================================
 */

import { formatSectionHeading } from "@/features/chat/section-extraction/section-extraction-adapter";
import { cn } from "@/lib/utils";

type Props = {
  number: string | null;
  title: string;
  depth?: number;
  className?: string;
};

export function SectionHeader({ number, title, depth = 1, className }: Props) {
  const label = formatSectionHeading(number, title);
  if (!label) return null;

  const headingLevel = Math.min(2 + Math.max(depth, 1), 6);
  const HeadingTag = `h${headingLevel}` as "h3" | "h4" | "h5" | "h6";
  const numberLabel = number ? (number.includes(".") ? number : `${number}.`) : null;

  return (
    <HeadingTag
      className={cn(
        "section-heading m-0 font-semibold text-primary",
        depth <= 1 ? "text-h3" : depth === 2 ? "text-body" : "text-body-sm",
        className,
      )}
      data-section-number={number ?? undefined}
    >
      {numberLabel ? (
        <span className="section-number">{numberLabel}</span>
      ) : null}
      {title ? <span className="section-title">{title}</span> : null}
    </HeadingTag>
  );
}
