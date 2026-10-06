/**
 * =============================================================================
 * File: ExtractionContent.tsx
 * Module/Service: Extraction Service (Web App)
 * Layer: UI
 * Purpose: Render completed Extraction by type / output_format.
 * Responsibilities:
 *   - Table gallery for extraction_type=table
 *   - Single ExtractionTable for other types with output_format=table
 *   - JsonViewer for output_format=json
 * Dependencies:
 *   - ExtractionTable, ExtractionTableGallery, JsonViewer, extraction-format
 * Public Exports:
 *   - ExtractionContent
 * Database/Table: N/A
 * Related Modules: ExtractionSection
 * Important Notes: No FE semantic extraction / timeline reordering / column inference.
 * =============================================================================
 */

"use client";

import { ExtractionTable } from "@/features/extractions/ExtractionTable";
import { ExtractionTableGallery } from "@/features/extractions/ExtractionTableGallery";
import { JsonViewer } from "@/features/extractions/JsonViewer";
import {
  asTableGalleryPayload,
  asTablePayload,
} from "@/features/extractions/extraction-format";
import { cn } from "@/lib/utils";
import type { Extraction } from "@/types/extractions";

type Props = {
  extraction: Extraction;
  className?: string;
};

export function ExtractionContent({ extraction, className }: Props) {
  if (extraction.status !== "completed" || extraction.result == null) {
    return (
      <p className="text-body-sm italic text-tertiary">Không có kết quả để hiển thị.</p>
    );
  }

  if (extraction.extraction_type === "table") {
    const gallery = asTableGalleryPayload(extraction.result);
    if (!gallery) {
      return (
        <p className="text-body-sm text-danger" role="alert">
          Kết quả bảng không hợp lệ (thiếu danh sách tables).
        </p>
      );
    }
    if (extraction.output_format === "json") {
      return (
        <div className={cn(className)}>
          <JsonViewer value={extraction.result} />
        </div>
      );
    }
    return (
      <div className={cn(className)}>
        <ExtractionTableGallery tables={gallery.tables} />
      </div>
    );
  }

  if (extraction.output_format === "table") {
    const table = asTablePayload(extraction.result);
    if (!table) {
      return (
        <p className="text-body-sm text-danger" role="alert">
          Kết quả bảng không hợp lệ (thiếu headers/rows).
        </p>
      );
    }
    return (
      <div className={cn(className)}>
        <ExtractionTable payload={table} />
      </div>
    );
  }

  return (
    <div className={cn(className)}>
      <JsonViewer value={extraction.result} />
    </div>
  );
}
