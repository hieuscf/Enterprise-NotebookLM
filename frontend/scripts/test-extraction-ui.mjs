/**
 * Node-side smoke checks for Extraction UI pure helpers (no Jest/RTL yet).
 * Mirrors features/extractions/extraction-format.ts + lib/download.ts.
 * Run: node scripts/test-extraction-ui.mjs
 */

function typeLabel(type) {
  const map = {
    table: "Bảng",
    figures: "Số liệu",
    entities: "Thực thể",
    timeline: "Mốc thời gian",
  };
  return map[type] ?? type;
}

function formatLabel(format) {
  const map = { json: "JSON", table: "Bảng" };
  return map[format] ?? format;
}

function isOldVersion(extraction, currentVersionId) {
  if (!currentVersionId) return false;
  return extraction.source_version_id !== currentVersionId;
}

function getCurrentExtraction(
  extractions,
  currentVersionId,
  extractionType,
  outputFormat,
  selectedLanguage = "vi",
) {
  if (!currentVersionId) return null;
  const matches = extractions.filter(
    (e) =>
      e.status === "completed" &&
      e.extraction_type === extractionType &&
      e.output_format === outputFormat &&
      (e.target_language ?? "vi") === selectedLanguage &&
      e.source_version_id === currentVersionId,
  );
  if (matches.length === 0) return null;
  return [...matches].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0];
}

function escapeCsvCell(value) {
  if (value === null || value === undefined) return "";
  const text = typeof value === "string" ? value : String(value);
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function serializeToCsv(headers, rows) {
  const lines = [headers.map(escapeCsvCell).join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => escapeCsvCell(row[h])).join(","));
  }
  return lines.join("\r\n");
}

function asTablePayload(result) {
  if (!result || typeof result !== "object") return null;
  if (!Array.isArray(result.headers) || !Array.isArray(result.rows)) return null;
  return {
    headers: result.headers.map((h) => String(h)),
    rows: result.rows,
  };
}

function asTableGalleryPayload(result) {
  if (!result || typeof result !== "object") return null;
  if (Array.isArray(result.tables)) {
    return { tables: result.tables };
  }
  const legacy = asTablePayload(result);
  if (!legacy) return null;
  return {
    tables: [
      {
        id: "legacy",
        title: "Bảng 1",
        source_chunk_id: "",
        headers: legacy.headers,
        rows: legacy.rows,
      },
    ],
  };
}

function buildCopyText(extraction) {
  if (extraction.result == null) return "";
  if (extraction.extraction_type === "table") {
    const gallery = asTableGalleryPayload(extraction.result);
    if (!gallery) return JSON.stringify(extraction.result, null, 2);
    if (extraction.output_format === "json") {
      return JSON.stringify(extraction.result, null, 2);
    }
    const blocks = [];
    for (const table of gallery.tables) {
      const lines = [`# ${table.title}`, table.headers.join("\t")];
      for (const row of table.rows) {
        lines.push(table.headers.map((h) => String(row[h] ?? "")).join("\t"));
      }
      blocks.push(lines.join("\n"));
    }
    return blocks.join("\n\n");
  }
  if (extraction.output_format === "table") {
    const table = asTablePayload(extraction.result);
    if (!table) return JSON.stringify(extraction.result, null, 2);
    const lines = [table.headers.join("\t")];
    for (const row of table.rows) {
      lines.push(table.headers.map((h) => String(row[h] ?? "")).join("\t"));
    }
    return lines.join("\n");
  }
  return JSON.stringify(extraction.result, null, 2);
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

// --- labels ----------------------------------------------------------------
assert(typeLabel("table") === "Bảng", "table type label");
assert(typeLabel("figures") === "Số liệu", "figures type label");
assert(typeLabel("entities") === "Thực thể", "entities type label");
assert(typeLabel("timeline") === "Mốc thời gian", "timeline type label");
assert(formatLabel("json") === "JSON", "json format label");
assert(formatLabel("table") === "Bảng", "table format label");

// --- current-version reuse (mandatory) -------------------------------------
const V1 = "v1";
const V2 = "v2";
const extractions = [
  {
    id: "old-table",
    extraction_type: "table",
    output_format: "table",
    status: "completed",
    source_version_id: V1,
    target_language: "vi",
    created_at: "2026-08-01T10:00:00Z",
    result: {
      tables: [
        {
          id: "t1",
          title: "Bảng 1",
          source_chunk_id: "c1",
          headers: ["A"],
          rows: [{ A: 1 }],
        },
      ],
    },
  },
  {
    id: "cur-table",
    extraction_type: "table",
    output_format: "table",
    status: "completed",
    source_version_id: V2,
    target_language: "vi",
    created_at: "2026-08-02T10:00:00Z",
    result: {
      tables: [
        {
          id: "t2",
          title: "Bảng 1",
          source_chunk_id: "c2",
          headers: ["A"],
          rows: [{ A: 2 }],
        },
      ],
    },
  },
  {
    id: "cur-table-newer",
    extraction_type: "table",
    output_format: "table",
    status: "completed",
    source_version_id: V2,
    target_language: "vi",
    created_at: "2026-08-03T10:00:00Z",
    result: {
      tables: [
        {
          id: "t3",
          title: "Bảng 1",
          source_chunk_id: "c3",
          headers: ["A"],
          rows: [{ A: 3 }],
        },
      ],
    },
  },
  {
    id: "cur-table-en",
    extraction_type: "table",
    output_format: "table",
    status: "completed",
    source_version_id: V2,
    target_language: "en",
    created_at: "2026-08-03T11:00:00Z",
    result: {
      tables: [
        {
          id: "t4",
          title: "Table 1",
          source_chunk_id: "c4",
          headers: ["A"],
          rows: [{ A: 9 }],
        },
      ],
    },
  },
  {
    id: "cur-figures-json",
    extraction_type: "figures",
    output_format: "json",
    status: "completed",
    source_version_id: V2,
    target_language: "vi",
    created_at: "2026-08-04T10:00:00Z",
    result: { figures: [{ metric: "Revenue", value: 10 }] },
  },
  {
    id: "cur-entities-table",
    extraction_type: "entities",
    output_format: "table",
    status: "completed",
    source_version_id: V2,
    target_language: "vi",
    created_at: "2026-08-05T10:00:00Z",
    result: {
      headers: ["name", "type"],
      rows: [{ name: "Acme", type: "ORG" }],
    },
  },
];

assert(
  getCurrentExtraction(extractions, V2, "table", "table")?.id === "cur-table-newer",
  "Picks newest completed table+table for V2 (no POST needed)",
);
assert(
  getCurrentExtraction(extractions, V2, "table", "table", "en")?.id === "cur-table-en",
  "Language is part of extraction reuse key",
);
assert(
  getCurrentExtraction(extractions, V2, "figures", "json")?.id === "cur-figures-json",
  "figures+json current reuse",
);
assert(
  getCurrentExtraction(extractions, V2, "entities", "table")?.id === "cur-entities-table",
  "entities+table current reuse",
);
assert(
  getCurrentExtraction(extractions, V2, "timeline", "json") === null,
  "Missing timeline on V2 → null (no auto old-version)",
);
assert(
  getCurrentExtraction(extractions, V2, "table", "json") === null,
  "table+json missing on V2 → null even if table+table exists",
);

// --- historical result -----------------------------------------------------
assert(isOldVersion({ source_version_id: V1 }, V2) === true, "V1 is old vs V2");
assert(isOldVersion({ source_version_id: V2 }, V2) === false, "V2 is current");
assert(
  getCurrentExtraction(extractions, V2, "table", "table")?.source_version_id === V2,
  "Current selection never returns V1",
);

// --- version change --------------------------------------------------------
assert(
  getCurrentExtraction(extractions, V1, "table", "table")?.id === "old-table",
  "At V1, old-table is current",
);
assert(
  getCurrentExtraction(extractions, "v3", "table", "table") === null,
  "After version change to V3 with no match → null (show Tạo trích xuất)",
);

// --- CSV export (structured, not DOM) --------------------------------------
const csv = serializeToCsv(
  ["Year", "Note"],
  [
    { Year: 2024, Note: 'hello, "world"' },
    { Year: 2025, Note: "line\nbreak" },
  ],
);
assert(csv.includes("Year,Note"), "CSV includes headers");
assert(csv.includes("2024"), "CSV includes row value");
assert(csv.includes('"hello, ""world"""'), "CSV escapes commas and quotes");
assert(csv.includes('"line\nbreak"') || csv.includes('"line\r\nbreak"') || csv.includes('"line\nbreak"'), "CSV escapes newlines");

const tablePayload = asTablePayload({
  headers: ["metric", "value"],
  rows: [{ metric: "Revenue", value: 1200 }],
});
assert(tablePayload?.headers[0] === "metric", "asTablePayload reads headers");
assert(asTablePayload({ figures: [] }) === null, "asTablePayload rejects non-table json");

// --- JSON / copy -----------------------------------------------------------
const jsonExtraction = {
  output_format: "json",
  result: { figures: [{ metric: "X", value: 1, unit: null, context: "FY" }] },
};
const copied = buildCopyText(jsonExtraction);
assert(copied.includes('"figures"'), "JSON copy uses canonical result");
assert(!copied.includes("[object Object]"), "JSON copy is not [object Object]");

const tableCopy = buildCopyText({
  extraction_type: "figures",
  output_format: "table",
  result: { headers: ["A", "B"], rows: [{ A: 1, B: "x" }] },
});
assert(tableCopy === "A\tB\n1\tx", "table copy is TSV from structured rows");

const galleryCopy = buildCopyText({
  extraction_type: "table",
  output_format: "table",
  result: {
    tables: [
      {
        id: "t1",
        title: "Revenue",
        source_chunk_id: "c1",
        headers: ["Year", "Amt"],
        rows: [{ Year: "2024", Amt: "10" }],
      },
    ],
  },
});
assert(galleryCopy.includes("# Revenue"), "gallery copy includes table title");
assert(galleryCopy.includes("Year\tAmt"), "gallery copy includes headers");
assert(
  asTableGalleryPayload({ tables: [] })?.tables.length === 0,
  "empty gallery narrows",
);
assert(
  asTableGalleryPayload({ headers: ["A"], rows: [{ A: 1 }] })?.tables[0]?.headers[0] === "A",
  "gallery wraps legacy flat table",
);

// --- empty table detection -------------------------------------------------
assert(
  asTablePayload({ headers: [], rows: [] })?.headers.length === 0,
  "empty headers allowed in payload narrow",
);

if (process.exitCode) {
  console.error("\nSome extraction-ui checks failed");
  process.exit(1);
}
console.log("\nAll extraction-ui checks passed");
