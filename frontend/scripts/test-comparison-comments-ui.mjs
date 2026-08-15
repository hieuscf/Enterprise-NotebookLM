/**
 * Node-side smoke checks for TASK-CMP-22 Comparison Annotation & Comments.
 * Mirrors features/comparisons/comparison-comments.ts.
 * Run: node scripts/test-comparison-comments-ui.mjs
 */

function asTargetType(raw) {
  const key = String(raw ?? "CLAUSE").toUpperCase();
  if (key === "FINDING" || key === "CLAUSE") return "CLAUSE";
  if (key === "EXACT_DIFFERENCE") return "EXACT_DIFFERENCE";
  if (key === "EVIDENCE") return "EVIDENCE";
  return "CLAUSE";
}

function normalizeComments(raw) {
  if (!Array.isArray(raw)) return [];
  const out = [];
  for (const item of raw) {
    const id = String(item?.id ?? "").trim();
    const clauseId = String(item?.clause_id ?? "").trim();
    const body = String(item?.body ?? "").trim();
    if (!id || !clauseId || !body) continue;
    const targetType = asTargetType(item.target_type);
    const targetId = String(item.target_id ?? "").trim() || null;
    out.push({
      id,
      clause_id: clauseId,
      target_type: targetType,
      target_id: targetType === "CLAUSE" ? null : targetId,
      body,
      author_id: item.author_id ?? null,
      author_name: item.author_name ?? null,
      created_at: item.created_at ?? null,
      updated_at: item.updated_at ?? null,
    });
  }
  return out;
}

function commentsForClause(comments, clauseId) {
  const wanted = String(clauseId);
  return normalizeComments(comments).filter((item) => item.clause_id === wanted);
}

function commentsForTarget(comments, clauseId, targetType = "CLAUSE", targetId) {
  const wantedId = String(targetId ?? "").trim() || null;
  return commentsForClause(comments, clauseId).filter((item) => {
    const type = asTargetType(item.target_type);
    if (type !== targetType) return false;
    if (targetType === "CLAUSE") return true;
    return String(item.target_id ?? "") === String(wantedId ?? "");
  });
}

function commentCount(comments, clauseId) {
  if (!clauseId) return normalizeComments(comments).length;
  return commentsForClause(comments, clauseId).length;
}

function commentBodiesForSearch(comments, clauseId) {
  return commentsForClause(comments, clauseId)
    .map((item) => item.body)
    .join(" ");
}

function exactDifferenceTargetId(index) {
  return String(index);
}

function formatCommentMeta(comment) {
  const name = (comment.author_name ?? "").trim();
  const edited = Boolean(comment.updated_at);
  if (name && edited) return `${name} · đã sửa`;
  if (name) return name;
  return null;
}

function assert(cond, msg) {
  if (!cond) {
    console.error(`FAIL: ${msg}`);
    process.exit(1);
  }
}

const finding = {
  clause_id: "CLAUSE:8.2",
  status: "MODIFIED",
  risk: { risk_level: "CRITICAL" },
  exact_differences: [{ old: { raw: "480,000,000" }, new: { raw: "600,000,000" } }],
};

const comments = [
  {
    id: "c1",
    clause_id: "CLAUSE:8.2",
    target_type: "CLAUSE",
    body: "Please confirm whether the new cap is acceptable under the current negotiation position.",
    author_name: "Lan Nguyen",
    created_at: "2026-08-15T10:00:00Z",
  },
  {
    id: "c2",
    clause_id: "CLAUSE:8.2",
    target_type: "EXACT_DIFFERENCE",
    target_id: "0",
    body: "Material increase.",
    author_name: "Lan Nguyen",
  },
  {
    id: "c3",
    clause_id: "CLAUSE:8.2",
    target_type: "EVIDENCE",
    target_id: "ev-1",
    body: "Check the V2 excerpt.",
  },
  {
    id: "c4",
    clause_id: "CLAUSE:3.1",
    target_type: "FINDING",
    body: "Other clause note.",
  },
];

const snapshot = JSON.stringify(finding);
const commentSnapshot = JSON.stringify(comments);

assert(normalizeComments(comments).length === 4, "normalize keeps valid comments");
assert(commentsForTarget(comments, "CLAUSE:8.2", "CLAUSE").length === 1, "clause-level thread");
assert(commentsForTarget(comments, "CLAUSE:8.2", "CLAUSE")[0].body.includes("new cap"), "comment is extra context");
assert(commentsForTarget(comments, "CLAUSE:8.2", "EXACT_DIFFERENCE", exactDifferenceTargetId(0)).length === 1, "diff target");
assert(commentsForTarget(comments, "CLAUSE:8.2", "EVIDENCE", "ev-1").length === 1, "evidence target");
assert(commentCount(comments, "CLAUSE:8.2") === 3, "clause comment count includes all targets");
assert(commentBodiesForSearch(comments, "CLAUSE:8.2").includes("acceptable"), "search haystack includes comments");
assert(asTargetType("FINDING") === "CLAUSE", "FINDING aliases CLAUSE");
assert(formatCommentMeta(comments[0]).includes("Lan Nguyen"), "author line");
assert(JSON.stringify(finding) === snapshot, "comments do not mutate the finding");
assert(finding.status === "MODIFIED", "system status unchanged");
assert(finding.risk.risk_level === "CRITICAL", "system risk unchanged");
assert(JSON.stringify(comments) === commentSnapshot, "helpers do not mutate comments");

console.log("test-comparison-comments-ui: ok");
