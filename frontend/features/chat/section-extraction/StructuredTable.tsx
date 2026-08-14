/**
 * =============================================================================
 * File: StructuredTable.tsx
 * Module/Service: Chat Service (Web App)
 * Layer: UI
 * Purpose: Render parser HTML/GFM tables as a real HTML table in chat answers.
 * Responsibilities:
 *   - Display headers + rows from SectionTable; never echo <tr>/<td> as text
 * Dependencies:
 *   - SectionTable
 * Public Exports:
 *   - StructuredTable
 * Database/Table: N/A
 * Related Modules: SectionItem, knowledge-table CSS
 * Important Notes: Reuses Knowledge View table tokens for a document-like feel.
 * =============================================================================
 */

import type { SectionTable } from "@/features/chat/section-extraction/section-extraction-adapter";

type Props = {
  table: SectionTable;
};

export function StructuredTable({ table }: Props) {
  const hasHeader = table.headers.some((h) => h.trim().length > 0);

  return (
    <div className="knowledge-table-scroll my-2">
      <table className="knowledge-table">
        {hasHeader ? (
          <thead>
            <tr>
              {table.headers.map((header, index) => (
                <th key={`h-${index}`}>{header || "\u00a0"}</th>
              ))}
            </tr>
          </thead>
        ) : null}
        <tbody>
          {table.rows.map((row, r) => (
            <tr key={`r-${r}`}>
              {row.map((cell, c) => (
                <td key={`c-${r}-${c}`}>{cell || "\u00a0"}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
