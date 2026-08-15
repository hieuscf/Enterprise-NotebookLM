/**
 * Node-side smoke checks for TASK-CMP-23 Comparison Audit Trail.
 * Mirrors features/comparisons/comparison-audit.ts.
 * Run: node scripts/test-comparison-audit-ui.mjs
 */

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

function auditActionLabel(action) {
  switch (String(action).toUpperCase()) {
    case "CLAUSE_OPENED":
      return "Mở điều khoản";
    case "REVIEW_STATUS_CHANGED":
      return "Đổi trạng thái rà soát";
    case "COMMENT_ADDED":
      return "Thêm ghi chú";
    case "COMMENT_EDITED":
      return "Sửa ghi chú";
    case "COMMENT_DELETED":
      return "Xoá ghi chú";
    default:
      return String(action);
  }
}

function excerpt(value, limit = 80) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}…`;
}

function snapshotField(snapshot, key) {
  if (!snapshot || typeof snapshot !== "object") return null;
  return snapshot[key];
}

function auditChangeText(event) {
  const action = String(event.action ?? "").toUpperCase();
  if (action === "REVIEW_STATUS_CHANGED") {
    const from = reviewStateLabel(snapshotField(event.before, "status"));
    const to = reviewStateLabel(snapshotField(event.after, "status"));
    return `${from} → ${to}`;
  }
  if (action === "COMMENT_ADDED") {
    return excerpt(snapshotField(event.after, "body")) || null;
  }
  if (action === "COMMENT_EDITED") {
    const before = excerpt(snapshotField(event.before, "body"));
    const after = excerpt(snapshotField(event.after, "body"));
    if (before && after) return `${before} → ${after}`;
    return after || before || null;
  }
  if (action === "COMMENT_DELETED") {
    return excerpt(snapshotField(event.before, "body")) || null;
  }
  return null;
}

function eventsForClause(events, clauseId) {
  const rows = Array.isArray(events) ? events : [];
  if (!clauseId) return rows;
  return rows.filter((item) => String(item.clause_id ?? "") === clauseId);
}

function newestFirst(events) {
  const rows = Array.isArray(events) ? [...events] : [];
  return rows.reverse();
}

function assert(cond, msg) {
  if (!cond) {
    console.error(`FAIL: ${msg}`);
    process.exit(1);
  }
}

const trail = [
  {
    id: "1",
    action: "CLAUSE_OPENED",
    clause_id: "CLAUSE:8.2",
    actor_name: "Alex",
    occurred_at: "2026-08-15T10:00:00Z",
  },
  {
    id: "2",
    action: "REVIEW_STATUS_CHANGED",
    clause_id: "CLAUSE:8.2",
    actor_name: "Alex",
    occurred_at: "2026-08-15T10:01:00Z",
    before: { status: "OPEN" },
    after: { status: "REVIEWED" },
  },
  {
    id: "3",
    action: "COMMENT_ADDED",
    clause_id: "CLAUSE:9.1",
    actor_name: "Alex",
    occurred_at: "2026-08-15T10:02:00Z",
    after: { body: "Need to confirm the cap." },
  },
];

assert(auditActionLabel("CLAUSE_OPENED") === "Mở điều khoản", "open label");
assert(
  auditChangeText(trail[1]) === "Chưa rà soát → Đã rà soát",
  "review change text",
);
assert(auditChangeText(trail[2]) === "Need to confirm the cap.", "comment body");
assert(eventsForClause(trail, "CLAUSE:8.2").length === 2, "clause filter");
assert(eventsForClause(trail, "CLAUSE:8.2")[0].id === "1", "filter keeps order");
assert(newestFirst(trail)[0].id === "3", "newest first is display-only reverse");
assert(newestFirst(trail)[2].id === "1", "oldest remains last after reverse");
assert(auditChangeText(trail[0]) === null, "open has no before/after text");
assert(
  auditActionLabel("COMMENT_DELETED") === "Xoá ghi chú",
  "delete is not a chat resolve action",
);

console.log("test-comparison-audit-ui: ok");
