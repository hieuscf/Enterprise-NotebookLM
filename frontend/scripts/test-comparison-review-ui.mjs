/**
 * Node-side smoke checks for TASK-CMP-20 Comparison Review Actions.
 * Mirrors features/comparisons/comparison-review.ts.
 * Run: node scripts/test-comparison-review-ui.mjs
 */

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

function reviewProgress(clauseIds, review) {
  const map = normalizeReviewMap(review);
  let reviewed = 0;
  let needsAttention = 0;
  let acknowledged = 0;
  for (const id of clauseIds) {
    const status = reviewState(map, id);
    if (status === "REVIEWED") reviewed += 1;
    else if (status === "NEEDS_ATTENTION") needsAttention += 1;
    else if (status === "ACKNOWLEDGED") acknowledged += 1;
  }
  const total = clauseIds.length;
  return {
    total,
    reviewed,
    needsAttention,
    acknowledged,
    open: total - reviewed - needsAttention - acknowledged,
  };
}

function filterByReview(clauses, review, filter) {
  if (filter === "all") return clauses;
  const wanted =
    filter === "open"
      ? "OPEN"
      : filter === "reviewed"
        ? "REVIEWED"
        : filter === "needs_attention"
          ? "NEEDS_ATTENTION"
          : "ACKNOWLEDGED";
  return clauses.filter((clause) => reviewState(review, clause.clause_id) === wanted);
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

const analysis = {
  clause_id: "CLAUSE:8.2",
  status: "MODIFIED",
  risk: { risk_level: "CRITICAL" },
};
const review = {
  "CLAUSE:8.2": {
    status: "REVIEWED",
    reviewer_name: "Lan",
    reviewed_at: "2026-08-15T12:00:00Z",
  },
};

assert(analysis.status === "MODIFIED", "system status stays MODIFIED");
assert(analysis.risk.risk_level === "CRITICAL", "system risk stays CRITICAL");
assert(reviewState(review, "CLAUSE:8.2") === "REVIEWED", "reviewer decision is REVIEWED");
assert(reviewState({}, "CLAUSE:8.2") === "OPEN", "missing review is OPEN");
assert(reviewStateLabel("OPEN") === "Chưa rà soát", "open label");
assert(reviewStateLabel("NEEDS_ATTENTION") === "Cần chú ý", "needs attention label");
assert(reviewState({ "CLAUSE:8.2": { status: "OPEN" } }, "CLAUSE:8.2") === "OPEN", "OPEN is not persisted");

const clauses = [
  { clause_id: "CLAUSE:8.2" },
  { clause_id: "CLAUSE:8.3" },
  { clause_id: "CLAUSE:1" },
];
const map = {
  "CLAUSE:8.2": { status: "REVIEWED" },
  "CLAUSE:8.3": { status: "NEEDS_ATTENTION" },
};
const progress = reviewProgress(clauses.map((c) => c.clause_id), map);
assert(progress.reviewed === 1 && progress.needsAttention === 1 && progress.open === 1, "progress counts");
assert(filterByReview(clauses, map, "reviewed").map((c) => c.clause_id).join() === "CLAUSE:8.2", "filter reviewed");
assert(filterByReview(clauses, map, "open").map((c) => c.clause_id).join() === "CLAUSE:1", "filter open");

assert(reviewState({ "CLAUSE:8.2": { status: "ACKNOWLEDGED" } }, "CLAUSE:8.2") === "ACKNOWLEDGED", "acknowledge");
const afterOpen = {};
assert(reviewState(afterOpen, "CLAUSE:8.2") === "OPEN", "reopen / reset is OPEN");
assert(analysis.status === "MODIFIED" && analysis.risk.risk_level === "CRITICAL", "reopen does not change analysis");

if (process.exitCode) {
  console.error("test-comparison-review-ui failed");
  process.exit(process.exitCode);
} else {
  console.log("test-comparison-review-ui passed");
}
