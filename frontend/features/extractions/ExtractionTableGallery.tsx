/**
 * =============================================================================
 * File: ExtractionTableGallery.tsx
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Gallery of original document tables from extraction_type=table.
 * Responsibilities:
 *   - List each recovered table with title / page metadata
 *   - Render each table via ExtractionTable
 * Public Exports:
 *   - ExtractionTableGallery
 * Database/Table: N/A
 * Related Modules: ExtractionContent, ExtractionTable
 * Important Notes: Does not invent columns — uses API tables[] only.
 * =============================================================================
 */

"use client";

import { ExtractionTable } from "@/features/extractions/ExtractionTable";
import { cn } from "@/lib/utils";
import type { DocumentTableItem } from "@/types/extractions";

type Props = {
  tables: DocumentTableItem[];
  className?: string;
};

function metaLine(table: DocumentTableItem): string | null {
  const bits: string[] = [];
  if (table.page_number != null) bits.push(`Trang ${table.page_number}`);
  if (table.heading_path) bits.push(table.heading_path);
  return bits.length ? bits.join(" · ") : null;
}

export function ExtractionTableGallery({ tables, className }: Props) {
  if (tables.length === 0) {
    return (
      <p className="text-body-sm italic text-tertiary">
        Không tìm thấy bảng gốc trong tài liệu.
      </p>
    );
  }

  return (
    <div className={cn("flex flex-col gap-5", className)} aria-label="Danh sách bảng gốc">
      {tables.map((table, index) => {
        const meta = metaLine(table);
        return (
          <article
            key={table.id || `table-${index}`}
            className="flex flex-col gap-2 rounded-lg border border-border-default p-3"
          >
            <header className="flex flex-col gap-0.5">
              <h3 className="text-body-sm font-semibold text-primary">{table.title}</h3>
              {meta ? <p className="text-caption text-tertiary">{meta}</p> : null}
              <p className="text-caption text-tertiary">
                {table.headers.length} cột · {table.rows.length} dòng
              </p>
            </header>
            <ExtractionTable
              payload={{ headers: table.headers, rows: table.rows }}
              emptyMessage="Bảng này không có dòng dữ liệu."
            />
          </article>
        );
      })}
    </div>
  );
}
