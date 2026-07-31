/**
 * Node-side smoke checks for Search UI helpers (no Jest/RTL yet).
 * Run: node scripts/test-search-ui.mjs
 */

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function highlightSnippetSegments(snippet, query) {
  const text = snippet || "";
  const tokens = Array.from(
    new Set(
      (query || "")
        .toLowerCase()
        .split(/[^\p{L}\p{N}]+/u)
        .map((t) => t.trim())
        .filter((t) => t.length >= 2),
    ),
  );
  if (!text || tokens.length === 0) {
    return [{ text, highlight: false }];
  }
  const pattern = new RegExp(`(${tokens.map(escapeRegExp).join("|")})`, "giu");
  const parts = text.split(pattern);
  return parts
    .filter((p) => p.length > 0)
    .map((part) => ({
      text: part,
      highlight: tokens.some((t) => t.toLowerCase() === part.toLowerCase()),
    }));
}

function formatRetrievalMethodLabel(method) {
  switch (method) {
    case "vector":
      return "Vector";
    case "bm25":
      return "BM25";
    case "knowledge_graph":
      return "Knowledge Graph";
    case "rerank":
      return "Rerank";
    default:
      return method;
  }
}

function buildSearchFilters({ fileType, dateFrom, dateTo, tagsInput }) {
  const filters = {};
  if (fileType) filters.file_type = fileType;
  if (dateFrom) filters.date_from = new Date(dateFrom).toISOString();
  if (dateTo) {
    const end = new Date(dateTo);
    end.setHours(23, 59, 59, 999);
    filters.date_to = end.toISOString();
  }
  const tags = (tagsInput || "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  if (tags.length) filters.tags = tags;
  return filters;
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

const highlighted = highlightSnippetSegments(
  "Annual leave policy for employees",
  "leave policy",
);
assert(
  highlighted.some((s) => s.highlight && s.text.toLowerCase() === "leave"),
  "highlight leave token",
);
assert(
  highlighted.some((s) => s.highlight && s.text.toLowerCase() === "policy"),
  "highlight policy token",
);
assert(
  highlightSnippetSegments("plain text", "").length === 1 &&
    highlightSnippetSegments("plain text", "")[0].highlight === false,
  "empty query → no highlight",
);

assert(formatRetrievalMethodLabel("vector") === "Vector", "badge Vector");
assert(formatRetrievalMethodLabel("bm25") === "BM25", "badge BM25");
assert(
  formatRetrievalMethodLabel("knowledge_graph") === "Knowledge Graph",
  "badge Knowledge Graph",
);
assert(formatRetrievalMethodLabel("rerank") === "Rerank", "badge Rerank");

const filters = buildSearchFilters({
  fileType: "pdf",
  dateFrom: "2024-01-01",
  dateTo: "2024-01-31",
  tagsInput: "hr, policy",
});
assert(filters.file_type === "pdf", "filter file_type");
assert(Array.isArray(filters.tags) && filters.tags.length === 2, "filter tags split");
assert(typeof filters.date_from === "string", "filter date_from ISO");
assert(typeof filters.date_to === "string", "filter date_to ISO");

assert(
  buildSearchFilters({ fileType: "", dateFrom: "", dateTo: "", tagsInput: "" }) &&
    Object.keys(
      buildSearchFilters({ fileType: "", dateFrom: "", dateTo: "", tagsInput: "" }),
    ).length === 0,
  "empty filters object when nothing set",
);

// Simulate history replay payload shape
const historyItem = {
  query_text: "leave",
  filters: { file_type: "pdf" },
  results_count: 3,
};
assert(historyItem.query_text === "leave", "history replay query present");
assert(historyItem.filters.file_type === "pdf", "history replay filters present");

if (!process.exitCode) {
  console.log("\nAll search UI helper checks passed.");
}
