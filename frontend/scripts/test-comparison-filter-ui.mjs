/**
 * Node-side smoke checks for TASK-CMP-21 Comparison Filtering & Advanced Search.
 * Mirrors features/comparisons/comparison-filter.ts and its review/evidence helpers.
 * Run: node scripts/test-comparison-filter-ui.mjs
 */

function displayClauseId(id) {
  if (!id) return "—";
  return String(id).replace(/^(CLAUSE|ARTICLE|APPENDIX|SECTION):/i, "");
}

function clauseRiskLevel(clause) {
  const level = String(clause.risk?.risk_level ?? "").trim().toUpperCase();
  return level || null;
}

function evidenceState(clause) {
  const status = String(clause.verification?.status ?? "").toUpperCase();
  const evidence = clause.evidence ?? [];
  if (status === "VERIFIED") return "verified";
  if (status === "PARTIALLY_VERIFIED") return "partial";
  if (status === "INSUFFICIENT_EVIDENCE" || evidence.length === 0) return "unavailable";
  return "unverified";
}

function evidenceStateLabel(state) {
  switch (state) {
    case "verified":
      return "Đã xác minh";
    case "partial":
      return "Xác minh một phần";
    case "unavailable":
      return "Không có bằng chứng";
    default:
      return "Chưa xác minh";
  }
}

function explanationText(clause) {
  const text = String(clause.explanation?.output?.explanation ?? "").trim();
  return text || null;
}

function formatExactDifference(row) {
  return {
    label: String(row.value_type ?? row.change_type ?? "Giá trị"),
    oldDisplay: String(row.old?.raw ?? row.old?.value ?? "—"),
    newDisplay: String(row.new?.raw ?? row.new?.value ?? "—"),
    delta: row.delta ? String(row.delta) : null,
  };
}

function riskLevelLabel(level) {
  switch (String(level ?? "").toUpperCase()) {
    case "CRITICAL":
      return "Nghiêm trọng";
    case "HIGH":
      return "Cao";
    case "MEDIUM":
      return "Trung bình";
    case "LOW":
      return "Thấp";
    default:
      return "";
  }
}

function normalizeReviewMap(raw) {
  if (!raw || typeof raw !== "object") return {};
  const persisted = new Set(["REVIEWED", "NEEDS_ATTENTION", "ACKNOWLEDGED"]);
  const out = {};
  for (const [key, value] of Object.entries(raw)) {
    const status = String(value?.status ?? "").toUpperCase();
    if (!persisted.has(status)) continue;
    out[key] = {
      status,
      reviewer_id: value.reviewer_id ?? null,
      reviewer_name: value.reviewer_name ?? null,
      reviewed_at: value.reviewed_at ?? null,
    };
  }
  return out;
}

function reviewState(review, clauseId) {
  const status = String(normalizeReviewMap(review)[clauseId]?.status ?? "").toUpperCase();
  if (status === "REVIEWED") return "REVIEWED";
  if (status === "NEEDS_ATTENTION") return "NEEDS_ATTENTION";
  if (status === "ACKNOWLEDGED") return "ACKNOWLEDGED";
  return "OPEN";
}

function reviewStateLabel(status) {
  switch (String(status).toUpperCase()) {
    case "REVIEWED":
      return "Đã rà soát";
    case "NEEDS_ATTENTION":
      return "Cần chú ý";
    case "ACKNOWLEDGED":
      return "Đã ghi nhận";
    default:
      return "Chưa rà soát";
  }
}

function reviewDecision(review, clauseId) {
  return normalizeReviewMap(review)[clauseId] ?? null;
}

const EMPTY_COMPARISON_QUERY = {
  status: "all",
  risk: null,
  review: "all",
  evidence: "all",
  category: null,
  query: "",
};

const STATUS_FILTERS = ["all", "changed", "modified", "added", "removed", "unchanged"];
const REVIEW_FILTERS = ["all", "open", "reviewed", "needs_attention", "acknowledged"];
const EVIDENCE_FILTERS = ["all", "verified", "partial", "unverified", "unavailable"];
const RISK_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

function asFilter(value, allowed, fallback) {
  const key = String(value ?? "").trim().toLowerCase();
  return allowed.includes(key) ? key : fallback;
}

function normalizeComparisonQuery(raw) {
  const status = asFilter(raw?.status, STATUS_FILTERS, "all");
  const review = asFilter(raw?.review, REVIEW_FILTERS, "all");
  const evidence = asFilter(raw?.evidence, EVIDENCE_FILTERS, "all");
  const riskRaw = String(raw?.risk ?? "").trim().toUpperCase();
  const risk = RISK_LEVELS.includes(riskRaw) ? riskRaw : null;
  const category = String(raw?.category ?? "").trim() || null;
  const query = String(raw?.query ?? "");
  return { status, risk, review, evidence, category, query };
}

function isQueryActive(query) {
  const q = normalizeComparisonQuery(query);
  return (
    q.status !== "all" ||
    q.risk != null ||
    q.review !== "all" ||
    q.evidence !== "all" ||
    q.category != null ||
    q.query.trim() !== ""
  );
}

function statusFilterLabel(filter) {
  switch (filter) {
    case "changed":
      return "Có thay đổi";
    case "modified":
      return "Đã sửa";
    case "added":
      return "Thêm mới";
    case "removed":
      return "Đã xoá";
    case "unchanged":
      return "Không đổi";
    default:
      return "Tất cả";
  }
}

function reviewFilterLabel(filter) {
  switch (filter) {
    case "open":
      return "Chưa rà soát";
    case "reviewed":
      return "Đã rà soát";
    case "needs_attention":
      return "Cần chú ý";
    case "acknowledged":
      return "Đã ghi nhận";
    default:
      return "Mọi rà soát";
  }
}

function evidenceFilterLabel(filter) {
  if (filter === "all") return "Mọi bằng chứng";
  return evidenceStateLabel(filter);
}

function matchesStatusFilter(clause, filter) {
  if (filter === "all") return true;
  const status = String(clause.status).toUpperCase();
  if (filter === "changed") return ["MODIFIED", "ADDED", "REMOVED"].includes(status);
  if (filter === "modified") return status === "MODIFIED";
  if (filter === "added") return status === "ADDED";
  if (filter === "removed") return status === "REMOVED";
  if (filter === "unchanged") return status === "UNCHANGED";
  return true;
}

function matchesRiskFilter(clause, risk) {
  if (!risk) return true;
  return clauseRiskLevel(clause) === risk.toUpperCase();
}

function matchesReviewFilter(clause, review, filter) {
  if (filter === "all") return true;
  const wanted =
    filter === "open"
      ? "OPEN"
      : filter === "reviewed"
        ? "REVIEWED"
        : filter === "needs_attention"
          ? "NEEDS_ATTENTION"
          : "ACKNOWLEDGED";
  return reviewState(review, clause.clause_id) === wanted;
}

function matchesEvidenceFilter(clause, filter) {
  if (filter === "all") return true;
  return evidenceState(clause) === filter;
}

function matchesCategoryFilter(clause, category) {
  if (!category) return true;
  const actual = String(clause.risk?.risk_category ?? "").trim();
  if (!actual) return false;
  return actual.toLowerCase() === category.trim().toLowerCase();
}

function searchHaystack(clause, review) {
  const diffs = (clause.exact_differences ?? []).map((row) => {
    const formatted = formatExactDifference(row);
    return [formatted.label, formatted.oldDisplay, formatted.newDisplay, formatted.delta].join(" ");
  });
  const decision = reviewDecision(review, clause.clause_id);
  return [
    clause.clause_id,
    clause.v1_clause_id,
    clause.v2_clause_id,
    displayClauseId(clause.clause_id),
    clause.v1_text,
    clause.v2_text,
    clause.risk?.risk_category,
    clause.risk?.reason,
    explanationText(clause),
    reviewStateLabel(reviewState(review, clause.clause_id)),
    decision?.reviewer_name,
    ...diffs,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function matchesKeyword(clause, review, query) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return searchHaystack(clause, review).includes(q);
}

function matchesComparisonQuery(clause, review, rawQuery) {
  const q = normalizeComparisonQuery(rawQuery);
  return (
    matchesStatusFilter(clause, q.status) &&
    matchesRiskFilter(clause, q.risk) &&
    matchesReviewFilter(clause, review, q.review) &&
    matchesEvidenceFilter(clause, q.evidence) &&
    matchesCategoryFilter(clause, q.category) &&
    matchesKeyword(clause, review, q.query)
  );
}

function applyComparisonQuery(clauses, review, rawQuery) {
  const q = normalizeComparisonQuery(rawQuery);
  return clauses.filter((clause) => matchesComparisonQuery(clause, review, q));
}

function clauseCategories(clauses) {
  const seen = new Set();
  const rows = [];
  for (const clause of clauses) {
    const category = String(clause.risk?.risk_category ?? "").trim();
    if (!category) continue;
    const key = category.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push(category);
  }
  return rows.sort((a, b) => a.localeCompare(b, "vi"));
}

function activeQueryChips(query) {
  const q = normalizeComparisonQuery(query);
  const chips = [];
  if (q.status !== "all") chips.push({ id: "status", label: statusFilterLabel(q.status) });
  if (q.risk) chips.push({ id: "risk", label: riskLevelLabel(q.risk) || q.risk });
  if (q.review !== "all") chips.push({ id: "review", label: reviewFilterLabel(q.review) });
  if (q.evidence !== "all") chips.push({ id: "evidence", label: evidenceFilterLabel(q.evidence) });
  if (q.category) chips.push({ id: "category", label: q.category });
  const keyword = q.query.trim();
  if (keyword) chips.push({ id: "query", label: `“${keyword}”` });
  return chips;
}

function clearQueryDimension(query, id) {
  const next = { ...normalizeComparisonQuery(query) };
  if (id === "status") next.status = "all";
  else if (id === "risk") next.risk = null;
  else if (id === "review") next.review = "all";
  else if (id === "evidence") next.evidence = "all";
  else if (id === "category") next.category = null;
  else if (id === "query") next.query = "";
  return next;
}

function queryScopeLabel(query) {
  const chips = activeQueryChips(query);
  if (chips.length === 0) return "Tất cả";
  return chips.map((chip) => chip.label).join(" · ");
}

function queryResultCaption(visible, total, query) {
  if (!isQueryActive(query)) return `${total} điều khoản`;
  return `${visible} / ${total} điều khoản khớp bộ lọc`;
}

function clauseNav(visible, currentId) {
  const total = visible.length;
  if (!currentId || total === 0) return { index: -1, total, prevId: null, nextId: null };
  const index = visible.findIndex((clause) => clause.clause_id === currentId);
  if (index < 0) return { index: -1, total, prevId: null, nextId: null };
  return {
    index,
    total,
    prevId: index > 0 ? visible[index - 1].clause_id : null,
    nextId: index < total - 1 ? visible[index + 1].clause_id : null,
  };
}

function assert(cond, msg) {
  if (!cond) {
    console.error(`FAIL: ${msg}`);
    process.exit(1);
  }
}

const clauses = [
  {
    clause_id: "CLAUSE:8.2",
    status: "MODIFIED",
    v1_text: "Liability cap is 1x fees.",
    v2_text: "Liability cap is 2x fees.",
    risk: { risk_level: "CRITICAL", risk_category: "Liability", reason: "Cap doubled" },
    verification: { status: "VERIFIED" },
    evidence: [{ evidence_id: "e1", page_number: 4 }],
    explanation: { output: { explanation: "The cap increased from 1x to 2x." } },
    exact_differences: [{ value_type: "MULTIPLIER", old: { raw: "1x" }, new: { raw: "2x" } }],
  },
  {
    clause_id: "CLAUSE:3.1",
    status: "MODIFIED",
    v1_text: "Payment in 30 days.",
    v2_text: "Payment in 45 days.",
    risk: { risk_level: "HIGH", risk_category: "Payment", reason: "Longer payment window" },
    verification: { status: "UNVERIFIED" },
    evidence: [{ evidence_id: "e2", page_number: 12, display_text: "Net 45" }],
  },
  {
    clause_id: "CLAUSE:9.0",
    status: "ADDED",
    v2_text: "New audit right.",
    risk: { risk_level: "MEDIUM", risk_category: "Audit" },
    verification: { status: "PARTIALLY_VERIFIED" },
    evidence: [{ evidence_id: "e3" }],
  },
  {
    clause_id: "CLAUSE:2.4",
    status: "REMOVED",
    v1_text: "Legacy termination for convenience.",
    risk: { risk_level: "LOW", risk_category: "Termination" },
    verification: { status: "INSUFFICIENT_EVIDENCE" },
    evidence: [],
  },
  {
    clause_id: "CLAUSE:1.1",
    status: "UNCHANGED",
    v1_text: "Definitions remain the same.",
    v2_text: "Definitions remain the same.",
    evidence: [{ evidence_id: "e4", page_number: 1 }],
  },
];

const review = {
  "CLAUSE:8.2": {
    status: "NEEDS_ATTENTION",
    reviewer_id: "u1",
    reviewer_name: "Lan Nguyen",
    reviewed_at: "2026-08-15T10:00:00Z",
  },
  "CLAUSE:3.1": {
    status: "REVIEWED",
    reviewer_id: "u2",
    reviewer_name: "Minh",
    reviewed_at: "2026-08-15T11:00:00Z",
  },
  "CLAUSE:9.0": { status: "OPEN" },
};

const snapshot = JSON.stringify(clauses);
const reviewSnapshot = JSON.stringify(review);

const combined = applyComparisonQuery(clauses, review, {
  status: "modified",
  risk: "CRITICAL",
  review: "needs_attention",
});
assert(combined.length === 1 && combined[0].clause_id === "CLAUSE:8.2", "AND Critical + Modified + Needs Attention");

assert(applyComparisonQuery(clauses, review, { status: "changed" }).length === 4, "changed = modified+added+removed");
assert(applyComparisonQuery(clauses, review, { status: "unchanged" }).length === 1, "unchanged only");
assert(applyComparisonQuery(clauses, review, { risk: "HIGH" })[0].clause_id === "CLAUSE:3.1", "risk HIGH");
assert(applyComparisonQuery(clauses, review, { review: "open" }).map((c) => c.clause_id).includes("CLAUSE:1.1"), "open includes missing map entries");
assert(applyComparisonQuery(clauses, review, { review: "open" }).every((c) => reviewState(review, c.clause_id) === "OPEN"), "open is OPEN only");

const verified = applyComparisonQuery(clauses, review, { evidence: "verified" });
assert(verified.length === 1 && verified[0].clause_id === "CLAUSE:8.2", "verified uses verification.status");

const pageButUnverified = applyComparisonQuery(clauses, review, { evidence: "verified" }).some(
  (c) => c.clause_id === "CLAUSE:3.1",
);
assert(!pageButUnverified, "page_number does not imply verified");
assert(
  applyComparisonQuery(clauses, review, { evidence: "unverified" }).some((c) => c.clause_id === "CLAUSE:3.1"),
  "UNVERIFIED with evidence is unverified",
);
assert(
  applyComparisonQuery(clauses, review, { evidence: "unavailable" }).some((c) => c.clause_id === "CLAUSE:2.4"),
  "INSUFFICIENT_EVIDENCE is unavailable",
);
assert(
  applyComparisonQuery(clauses, review, { evidence: "unverified" }).some((c) => c.clause_id === "CLAUSE:1.1"),
  "missing verification.status with evidence is unverified, not verified",
);

assert(applyComparisonQuery(clauses, review, { category: "Payment" }).length === 1, "category Payment");
assert(applyComparisonQuery(clauses, review, { category: "payment" }).length === 1, "category is case-insensitive");
assert(applyComparisonQuery(clauses, review, { query: "8.2" })[0].clause_id === "CLAUSE:8.2", "keyword clause id");
assert(applyComparisonQuery(clauses, review, { query: "Liability cap" }).length === 1, "keyword clause text");
assert(applyComparisonQuery(clauses, review, { query: "Lan Nguyen" }).length === 1, "keyword reviewer name");
assert(applyComparisonQuery(clauses, review, { query: "2x" }).length === 1, "keyword exact difference");

assert(JSON.stringify(clauses) === snapshot, "filtering does not mutate clauses");
assert(JSON.stringify(review) === reviewSnapshot, "filtering does not mutate review");
assert(combined[0] === clauses[0], "result rows are the same objects");

const categories = clauseCategories(clauses);
assert(categories.includes("Liability") && categories.includes("Payment"), "unique categories");
assert(categories.filter((c) => c.toLowerCase() === "liability").length === 1, "dedupe categories");

const chips = activeQueryChips({
  status: "modified",
  risk: "CRITICAL",
  review: "needs_attention",
  evidence: "all",
  category: null,
  query: "",
});
assert(chips.map((c) => c.id).join(",") === "status,risk,review", "active chips for combined query");
assert(queryScopeLabel(chips.length ? {
  status: "modified",
  risk: "CRITICAL",
  review: "needs_attention",
  evidence: "all",
  category: null,
  query: "",
} : EMPTY_COMPARISON_QUERY) === "Đã sửa · Nghiêm trọng · Cần chú ý", "scope label for clause nav");

const cleared = clearQueryDimension(
  { status: "modified", risk: "CRITICAL", review: "needs_attention", evidence: "all", category: null, query: "" },
  "risk",
);
assert(cleared.risk == null && cleared.status === "modified", "clear one dimension keeps others");
assert(!isQueryActive(EMPTY_COMPARISON_QUERY), "empty query is inactive");
assert(queryResultCaption(1, 5, { status: "modified", risk: "CRITICAL", review: "needs_attention", evidence: "all", category: null, query: "" }) === "1 / 5 điều khoản khớp bộ lọc", "result caption when filtered");
assert(queryResultCaption(5, 5, EMPTY_COMPARISON_QUERY) === "5 điều khoản", "result caption when idle");

const visible = applyComparisonQuery(clauses, review, { status: "changed" });
const nav = clauseNav(visible, "CLAUSE:8.2");
assert(nav.total === 4 && nav.nextId === "CLAUSE:3.1", "prev/next stays on filtered list");

const bogus = normalizeComparisonQuery({ status: "hacked", risk: "ULTRA", review: "queued", evidence: "has-page" });
assert(bogus.status === "all" && bogus.risk == null && bogus.review === "all" && bogus.evidence === "all", "unknown filters fall back");

console.log("test-comparison-filter-ui: ok");
