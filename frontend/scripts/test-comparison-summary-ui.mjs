/**
 * Node-side smoke checks for TASK-CMP-17 Comparison Summary UI helpers.
 * Mirrors features/comparisons/comparison-summary.ts.
 * Run: node scripts/test-comparison-summary-ui.mjs
 */

function asRecord(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value;
}

function asString(value) {
  if (value == null) return null;
  const text = String(value).trim();
  return text ? text : null;
}

function asNumber(value, fallback = 0) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function asClauseArray(value) {
  if (!Array.isArray(value)) return [];
  return value.filter((item) => item && asString(item.clause_id) && asString(item.status));
}

function unwrapContractComparison(raw) {
  const rec = asRecord(raw);
  if (!rec) return null;
  const nested = asRecord(rec.comparison);
  if (nested && (nested.summary || nested.clauses || nested.metadata)) return nested;
  if (rec.summary || rec.clauses || rec.metadata) return rec;
  return null;
}

function normalizeContractComparison(raw) {
  const rec = unwrapContractComparison(raw);
  if (!rec) return null;
  const summaryRec = asRecord(rec.summary);
  const summary = summaryRec
    ? {
        total_clauses: asNumber(summaryRec.total_clauses),
        unchanged: asNumber(summaryRec.unchanged),
        modified: asNumber(summaryRec.modified),
        added: asNumber(summaryRec.added),
        removed: asNumber(summaryRec.removed),
      }
    : null;
  const clausesRec = asRecord(rec.clauses);
  const clauses = clausesRec
    ? {
        unchanged: asClauseArray(clausesRec.unchanged),
        modified: asClauseArray(clausesRec.modified),
        added: asClauseArray(clausesRec.added),
        removed: asClauseArray(clausesRec.removed),
        unresolved: asClauseArray(clausesRec.unresolved),
      }
    : null;
  if (!summary && !clauses) return null;
  return {
    metadata: asRecord(rec.metadata),
    summary,
    statistics: asRecord(rec.statistics),
    clauses,
  };
}

function flattenClauses(report) {
  if (!report?.clauses) return [];
  return [
    ...(report.clauses.modified ?? []),
    ...(report.clauses.added ?? []),
    ...(report.clauses.removed ?? []),
    ...(report.clauses.unchanged ?? []),
    ...(report.clauses.unresolved ?? []),
  ];
}

function comparisonUiStatus(comparison, report) {
  if (comparison.status === "processing") return "processing";
  if (comparison.status === "failed") return "failed";
  const quality = String(report?.metadata?.quality_status ?? "").toUpperCase();
  const incomplete = Boolean(report?.metadata?.explanation_incomplete);
  if (quality === "FAIL" || quality === "PASS_WITH_WARNINGS" || incomplete) {
    return "warning";
  }
  return "completed";
}

function statusBannerLabel(uiStatus) {
  switch (uiStatus) {
    case "processing":
      return "Đang so sánh tài liệu…";
    case "failed":
      return "So sánh thất bại";
    case "warning":
      return "So sánh hoàn tất kèm cảnh báo";
    default:
      return "So sánh hoàn tất";
  }
}

function clauseStatusLabel(status) {
  switch (String(status).toUpperCase()) {
    case "UNCHANGED":
      return "Không đổi";
    case "MODIFIED":
      return "Đã sửa";
    case "ADDED":
      return "Thêm mới";
    case "REMOVED":
      return "Đã xoá";
    default:
      return String(status);
  }
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

function displayClauseId(id) {
  if (!id) return "—";
  return id.replace(/^(CLAUSE|ARTICLE|APPENDIX|SECTION):/i, "");
}

const RISK_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

function riskRank(level) {
  return RISK_RANK[String(level ?? "").toUpperCase()] ?? 4;
}

function clauseRiskLevel(clause) {
  const level = asString(clause.risk?.risk_level);
  return level ? level.toUpperCase() : null;
}

function priorityClauses(clauses) {
  const candidates = clauses.filter((clause) => {
    const status = String(clause.status).toUpperCase();
    return status === "MODIFIED" || status === "ADDED" || status === "REMOVED";
  });
  return [...candidates].sort(
    (a, b) => riskRank(clauseRiskLevel(a)) - riskRank(clauseRiskLevel(b)),
  );
}

function filterClauses(clauses, filter, query, riskFilter = null) {
  const q = query.trim().toLowerCase();
  const risk = riskFilter ? riskFilter.toUpperCase() : null;
  return clauses.filter((clause) => {
    const status = String(clause.status).toUpperCase();
    if (filter === "modified" && status !== "MODIFIED") return false;
    if (filter === "added" && status !== "ADDED") return false;
    if (filter === "removed" && status !== "REMOVED") return false;
    if (filter === "unchanged" && status !== "UNCHANGED") return false;
    if (risk && clauseRiskLevel(clause) !== risk) return false;
    if (!q) return true;
    const haystack = [
      clause.clause_id,
      clause.v1_clause_id,
      clause.v2_clause_id,
      displayClauseId(clause.clause_id),
      clause.v1_text,
      clause.v2_text,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}

function hasMaterialChanges(summary) {
  if (!summary) return false;
  return summary.modified + summary.added + summary.removed > 0;
}

function riskCountsFromReport(report) {
  const raw = report?.statistics?.risk_counts ?? {};
  return {
    critical: asNumber(raw.critical),
    high: asNumber(raw.high),
    medium: asNumber(raw.medium),
    low: asNumber(raw.low),
  };
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

function evidenceForSide(clause, side) {
  const rows = clause.citations?.length ? clause.citations : clause.evidence ?? [];
  return rows.filter((item) => String(item.side ?? "").toUpperCase() === side);
}

function formatExactDifference(row) {
  const valueType = asString(row.value_type) ?? asString(row.change_type) ?? "Giá trị";
  const oldRaw = asString(row.old?.raw) ?? asString(row.old?.value);
  const newRaw = asString(row.new?.raw) ?? asString(row.new?.value);
  return {
    label: valueType,
    oldDisplay: oldRaw ?? "—",
    newDisplay: newRaw ?? "—",
    delta: asString(row.delta),
    percent: asString(row.relative_change_percent)
      ? `${asString(row.relative_change_percent)}%`
      : null,
  };
}

function evidenceViewerHref(workspaceId, evidence, fallbackDocumentId, fallbackVersionId) {
  const documentId = asString(evidence.document_id) ?? asString(fallbackDocumentId);
  if (!documentId) return null;
  const params = new URLSearchParams();
  const page = evidence.page_number;
  if (typeof page === "number" && page > 0) {
    params.set("page", String(page));
    params.set("view", "original");
  } else {
    params.set("view", "knowledge");
  }
  const chunkId = asString(evidence.chunk_id);
  if (chunkId) params.set("chunk", chunkId);
  const versionId = asString(evidence.document_version_id) ?? asString(fallbackVersionId);
  if (versionId) params.set("version", versionId);
  return `/workspaces/${workspaceId}/documents/${documentId}?${params.toString()}`;
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

function clause(id, status, extra = {}) {
  return { clause_id: id, status, ...extra };
}

const scenario1 = normalizeContractComparison({
  metadata: {
    document_v1: { document_id: "d1", title: "MSA V1" },
    document_v2: { document_id: "d2", title: "MSA V2" },
    quality_status: "PASS",
  },
  summary: { total_clauses: 12, unchanged: 8, modified: 3, added: 1, removed: 0 },
  statistics: { risk_counts: { critical: 1, high: 1, medium: 0, low: 1 } },
  clauses: {
    unchanged: Array.from({ length: 8 }, (_, i) => clause(`CLAUSE:${i + 1}`, "UNCHANGED")),
    modified: [
      clause("CLAUSE:8.2", "MODIFIED", {
        risk: { risk_level: "CRITICAL", risk_category: "LIABILITY" },
        v1_text: "Liability cap 480,000,000",
        v2_text: "Liability cap 600,000,000",
        exact_differences: [
          {
            value_type: "MONEY",
            old: { raw: "480,000,000" },
            new: { raw: "600,000,000" },
            delta: "120000000",
            relative_change_percent: "25",
          },
        ],
        evidence: [
          { side: "OLD", document_id: "d1", page_number: 14, clause_id: "CLAUSE:8.2" },
          { side: "NEW", document_id: "d2", page_number: 15, clause_id: "CLAUSE:8.2" },
        ],
        verification: { status: "VERIFIED" },
        explanation: { output: { explanation: "Liability cap increased." } },
      }),
      clause("CLAUSE:3", "MODIFIED", { risk: { risk_level: "HIGH" } }),
      clause("CLAUSE:11", "MODIFIED", { risk: { risk_level: "LOW" } }),
    ],
    added: [clause("CLAUSE:8.3", "ADDED", { v2_text: "New subclause", evidence: [{ side: "NEW", page_number: 16, document_id: "d2" }] })],
    removed: [],
  },
});

assert(scenario1.summary.total_clauses === 12, "scenario 1 total");
assert(scenario1.summary.unchanged === 8, "scenario 1 unchanged");
assert(scenario1.summary.modified === 3, "scenario 1 modified");
assert(scenario1.summary.added === 1, "scenario 1 added");
assert(scenario1.summary.removed === 0, "scenario 1 removed");
assert(hasMaterialChanges(scenario1.summary), "scenario 1 has material changes");

const s1Clauses = flattenClauses(scenario1);
assert(s1Clauses.length === 12, "flatten uses API buckets, not recounting UI rows as authority");
assert(filterClauses(s1Clauses, "modified", "").length === 3, "filter modified");
assert(filterClauses(s1Clauses, "added", "").length === 1, "filter added");
assert(filterClauses(s1Clauses, "removed", "").length === 0, "filter removed");
assert(filterClauses(s1Clauses, "unchanged", "").length === 8, "filter unchanged");
assert(filterClauses(s1Clauses, "all", "8.2").map((c) => c.clause_id).includes("CLAUSE:8.2"), "search clause number");
assert(filterClauses(s1Clauses, "all", "Liability cap").length === 1, "search clause text");

const ranked = priorityClauses(s1Clauses);
assert(ranked[0].clause_id === "CLAUSE:8.2", "priority: CRITICAL first");
assert(ranked[1].risk.risk_level === "HIGH", "priority: HIGH second");
assert(clauseStatusLabel("MODIFIED") === "Đã sửa", "status badge text for modified");
assert(clauseStatusLabel("UNCHANGED") === "Không đổi", "status badge text for unchanged");
assert(riskLevelLabel("CRITICAL") === "Nghiêm trọng", "risk uses text, not color only");

const critical = s1Clauses.find((c) => c.clause_id === "CLAUSE:8.2");
assert(evidenceState(critical) === "verified", "verified evidence state");
assert(evidenceStateLabel("verified") === "Đã xác minh", "verified label");
assert(evidenceForSide(critical, "OLD")[0].page_number === 14, "V1 evidence page");
assert(evidenceForSide(critical, "NEW")[0].page_number === 15, "V2 evidence page");
const href = evidenceViewerHref("ws1", evidenceForSide(critical, "OLD")[0]);
assert(href.includes("/workspaces/ws1/documents/d1"), "viewer document");
assert(href.includes("page=14"), "viewer page");
assert(href.includes("view=original"), "viewer original for page evidence");
const exact = formatExactDifference(critical.exact_differences[0]);
assert(exact.oldDisplay === "480,000,000" && exact.newDisplay === "600,000,000", "exact diff from backend");
assert(exact.delta === "120000000" && exact.percent === "25%", "delta/percent not recalculated");
assert(displayClauseId("CLAUSE:8.2") === "8.2", "display clause id strips prefix");

const scenario2 = normalizeContractComparison({
  summary: { total_clauses: 12, unchanged: 12, modified: 0, added: 0, removed: 0 },
  statistics: { risk_counts: { critical: 0, high: 0, medium: 0, low: 0 } },
  clauses: {
    unchanged: Array.from({ length: 12 }, (_, i) => clause(`CLAUSE:${i + 1}`, "UNCHANGED")),
    modified: [],
    added: [],
    removed: [],
  },
});
assert(!hasMaterialChanges(scenario2.summary), "scenario 2 no material changes");
assert(scenario2.summary.unchanged === 12, "scenario 2 all unchanged");
assert(priorityClauses(flattenClauses(scenario2)).length === 0, "scenario 2 no priority changes");

const scenario3 = normalizeContractComparison({
  summary: { total_clauses: 2, unchanged: 0, modified: 2, added: 0, removed: 0 },
  statistics: { risk_counts: { critical: 2, high: 0, medium: 0, low: 0 } },
  clauses: {
    modified: [
      clause("CLAUSE:8", "MODIFIED", { risk: { risk_level: "CRITICAL" } }),
      clause("CLAUSE:9", "MODIFIED", { risk: { risk_level: "CRITICAL" } }),
    ],
    unchanged: [],
    added: [],
    removed: [],
  },
});
const r3 = riskCountsFromReport(scenario3);
assert(r3.critical === 2 && r3.high === 0, "scenario 3 critical risk counts from API");
assert(filterClauses(flattenClauses(scenario3), "all", "", "CRITICAL").length === 2, "optional risk filter");

const scenario4 = normalizeContractComparison({
  summary: { total_clauses: 4, unchanged: 2, modified: 0, added: 1, removed: 1 },
  clauses: {
    unchanged: [clause("CLAUSE:1", "UNCHANGED"), clause("CLAUSE:2", "UNCHANGED")],
    modified: [],
    added: [
      clause("CLAUSE:8.3", "ADDED", {
        evidence: [{ side: "NEW", document_id: "d2", page_number: 20 }],
      }),
    ],
    removed: [
      clause("CLAUSE:9.9", "REMOVED", {
        evidence: [{ side: "OLD", document_id: "d1", page_number: 9 }],
      }),
    ],
  },
});
const added = flattenClauses(scenario4).find((c) => c.status === "ADDED");
const removed = flattenClauses(scenario4).find((c) => c.status === "REMOVED");
assert(evidenceForSide(added, "NEW").length === 1, "added shows V2 evidence");
assert(evidenceForSide(added, "OLD").length === 0, "added does not invent V1 evidence");
assert(evidenceForSide(removed, "OLD").length === 1, "removed shows V1 evidence");
assert(evidenceForSide(removed, "NEW").length === 0, "removed does not invent V2 evidence");
assert(scenario4.summary.added === 1 && scenario4.summary.removed === 1, "scenario 4 counts from summary");

const scenario5 = normalizeContractComparison({
  metadata: { quality_status: "PASS_WITH_WARNINGS", explanation_incomplete: true },
  summary: { total_clauses: 1, unchanged: 0, modified: 1, added: 0, removed: 0 },
  clauses: {
    modified: [
      clause("CLAUSE:4", "MODIFIED", {
        evidence: [{ side: "OLD", page_number: 2, document_id: "d1" }],
        verification: { status: "UNVERIFIED" },
      }),
    ],
  },
});
assert(
  comparisonUiStatus({ status: "completed" }, scenario5) === "warning",
  "scenario 5 warning status from quality_status",
);
assert(statusBannerLabel("warning") === "So sánh hoàn tất kèm cảnh báo", "warning banner copy");
assert(evidenceState(flattenClauses(scenario5)[0]) === "unverified", "unverified distinguishable");
assert(evidenceStateLabel("unverified") === "Chưa xác minh", "unverified label");
assert(evidenceState({ evidence: [], verification: { status: "INSUFFICIENT_EVIDENCE" } }) === "unavailable", "unavailable evidence");

assert(comparisonUiStatus({ status: "failed" }, null) === "failed", "scenario 6 failed job");
assert(statusBannerLabel("failed") === "So sánh thất bại", "failed banner copy");
assert(statusBannerLabel("processing") === "Đang so sánh tài liệu…", "loading copy");
assert(comparisonUiStatus({ status: "processing" }, null) === "processing", "processing status");

assert(normalizeContractComparison(null) === null, "missing report → null, no fake clauses");
assert(normalizeContractComparison({ similarities: ["a"] }) === null, "FR8-only payload is not a clause report");
assert(
  unwrapContractComparison({ comparison: { summary: { total_clauses: 1, unchanged: 1, modified: 0, added: 0, removed: 0 } } }).summary.total_clauses === 1,
  "unwrap nested as_dict comparison key",
);

const keyboardContract = {
  filters: ["all", "modified", "added", "removed", "unchanged"],
  interactive: ["clause-row-button", "priority-card-button", "evidence-link"],
};
assert(keyboardContract.filters.length === 5, "filter bar is a compact status set");
assert(clauseStatusLabel("MODIFIED") !== clauseStatusLabel("UNCHANGED"), "badges distinguishable by label");
assert(riskLevelLabel("CRITICAL") && riskLevelLabel("LOW"), "risk always has text");

if (!process.exitCode) {
  console.log("\nAll comparison summary UI smoke checks passed.");
}
