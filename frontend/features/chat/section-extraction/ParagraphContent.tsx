/**
 * =============================================================================
 * File: ParagraphContent.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Body paragraph inside a section_extraction outline.
 * Responsibilities:
 *   - Render normalized text (not markdown lists / raw HTML)
 * Dependencies:
 *   - N/A
 * Public Exports:
 *   - ParagraphContent
 * Database/Table: N/A
 * Related Modules: SectionItem
 * Important Notes: Markdown is not used here — headings already live in SectionTitle.
 * =============================================================================
 */

type Props = {
  text: string;
};

export function ParagraphContent({ text }: Props) {
  if (!text.trim()) return null;
  return (
    <p className="text-body-sm leading-relaxed text-primary">{text}</p>
  );
}
