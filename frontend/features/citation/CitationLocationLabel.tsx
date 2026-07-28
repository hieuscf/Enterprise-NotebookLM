/**
 * =============================================================================
 * File: CitationLocationLabel.tsx
 * Module/Service: Citation UI (FR5)
 * Layer: UI
 * Purpose: Render citation position as "Trang X" or "Mục X" without mixing.
 * Responsibilities:
 *   - Read location.page_number / location.section_index per FR5 convention
 *   - Hide label when both locators are null (snippet + document title only)
 * Dependencies:
 *   - lib/content-location
 * Public Exports:
 *   - CitationLocationLabel
 * Database/Table: N/A
 * Related Modules: OpenAPI ContentLocation; chat citation list
 * Important Notes: DOCX must never render as "Trang X".
 * =============================================================================
 */

import {
  formatContentLocationLabel,
  type ContentLocation,
} from "@/lib/content-location";

type Props = {
  location?: ContentLocation | null;
  className?: string;
};

export function CitationLocationLabel({ location, className }: Props) {
  const label = formatContentLocationLabel(location);
  if (!label) return null;
  return (
    <span className={className ?? "text-sm text-citation"} data-testid="citation-location">
      {label}
    </span>
  );
}
