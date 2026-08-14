/**
 * =============================================================================
 * File: BulletList.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Unordered body list inside a section — never used for section numbers.
 * Responsibilities:
 *   - Render genuine bullet content as <ul>, not document outline headings
 * Dependencies:
 *   - N/A
 * Public Exports:
 *   - BulletList
 * Database/Table: N/A
 * Related Modules: SectionItem
 * Important Notes: Do not pass "4.1 Title" as a list item.
 * =============================================================================
 */

type Props = {
  items: string[];
};

export function BulletList({ items }: Props) {
  if (items.length === 0) return null;
  return (
    <ul className="list-disc space-y-1 pl-5 text-body-sm leading-relaxed text-primary">
      {items.map((item, index) => (
        <li key={`${index}-${item.slice(0, 24)}`}>{item}</li>
      ))}
    </ul>
  );
}
