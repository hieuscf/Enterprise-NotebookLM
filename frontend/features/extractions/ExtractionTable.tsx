/**
 * =============================================================================
 * File: ExtractionTable.tsx
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Semantic HTML table for output_format=table (no Table lib in repo).
 * Responsibilities:
 *   - Render headers + rows; empty state; horizontal overflow
 * Dependencies:
 *   - extraction-format asTablePayload helpers
 * Public Exports:
 *   - ExtractionTable
 * Database/Table: N/A
 * Related Modules: ExtractionContent
 * Important Notes: Does not infer columns — uses API headers/rows only.
 * =============================================================================
 */

"use client";

import { isEmptyTable } from "@/features/extractions/extraction-format";
import { cn } from "@/lib/utils";
import type { TableResultPayload } from "@/types/extractions";

type Props = {
  payload: TableResultPayload;
  emptyMessage?: string;
  className?: string;
};

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ExtractionTable({
  payload,
  emptyMessage = "Không tìm thấy dữ liệu dạng bảng trong tài liệu.",
  className,
}: Props) {
  if (isEmptyTable(payload)) {
    return <p className="text-body-sm italic text-tertiary">{emptyMessage}</p>;
  }

  return (
    <div
      className={cn("overflow-x-auto rounded-md border border-border-default", className)}
    >
      <table className="min-w-full border-collapse text-left text-body-sm">
        <thead className="bg-elevated/60">
          <tr>
            {payload.headers.map((header) => (
              <th
                key={header}
                scope="col"
                className="whitespace-nowrap border-b border-border-default px-3 py-2 font-semibold text-primary"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {payload.rows.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              className="odd:bg-surface even:bg-elevated/20 hover:bg-elevated/40"
            >
              {payload.headers.map((header) => (
                <td
                  key={`${rowIdx}-${header}`}
                  className="max-w-xs truncate border-b border-border-default px-3 py-2 text-secondary"
                  title={cellText(row[header])}
                >
                  {cellText(row[header])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
