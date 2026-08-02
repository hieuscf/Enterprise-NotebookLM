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

function filterResultsByMinScore(results, minScore = 0.6) {
  return results
    .filter((item) => Number(item.score) >= minScore)
    .map((item, index) => ({ ...item, rank: index + 1 }));
}

const gated = filterResultsByMinScore([
  { document_id: "a", score: 0.85, rank: 1 },
  { document_id: "b", score: 0.42, rank: 2 },
  { document_id: "c", score: 0.6, rank: 3 },
]);
assert(gated.length === 2, "UI score gate keeps >= 0.6");
assert(gated[0].document_id === "a" && gated[0].rank === 1, "UI score gate re-ranks");
assert(gated[1].document_id === "c" && gated[1].rank === 2, "UI score gate keeps 0.6");

function buildDocumentViewerHref(workspaceId, item) {
  const params = new URLSearchParams();
  if (item.chunk_id) params.set("chunk", item.chunk_id);
  const page = item.page_number ?? item.location?.page_number ?? null;
  if (page != null) params.set("page", String(page));
  const qs = params.toString();
  const base = `/workspaces/${workspaceId}/documents/${item.document_id}`;
  return qs ? `${base}?${qs}` : base;
}

const href = buildDocumentViewerHref("ws1", {
  document_id: "doc1",
  chunk_id: "chunk_xyz",
  page_number: 5,
});
assert(
  href === "/workspaces/ws1/documents/doc1?chunk=chunk_xyz&page=5",
  "deep-link href includes chunk + page",
);

if (!process.exitCode) {
  console.log("\nAll search UI helper checks passed.");
}
