/**
 * =============================================================================
 * File: test-comparison-report-preview-ui.mjs
 * Module/Service: Report Service (Web App)
 * Layer: UI
 * Purpose: Node smoke checks for TASK-CMP-25 Comparison Report Preview helpers.
 * Responsibilities:
 *   - Mirror comparison-report-preview.ts: status, stats, filter, search,
 *     evidence href policy, export availability, V1/V2 regression invariants
 * Dependencies:
 *   - N/A (self-contained mirror of pure helpers)
 * Public Exports:
 *   - N/A
 * Database/Table: N/A
 * Related Modules: features/reports/comparison-report-preview.ts
 * Important Notes: Do not recount backend statistics. Do not infer ADDED/REMOVED.
 * =============================================================================
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

function asInt(value, fallback = 0) {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value);
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return Math.trunc(parsed);
  }
  return fallback;
}

function displayClauseId(id) {
  if (!id) return "—";
  return String(id).replace(/^(CLAUSE|ARTICLE|APPENDIX|SECTION):/i, "");
}

function unwrapComparisonReport(preview) {
  if (!preview || typeof preview !== "object") return null;
  const report = preview.comparison_report;
  if (!report || typeof report !== "object") return null;
  return report;
}

function executiveCounts(report) {
  const exec = asRecord(report?.executive_summary) ?? {};
  const rawCounts = asRecord(exec.risk_counts) ?? {};
  return {
    total: asInt(exec.total_clauses),
    unchanged: asInt(exec.unchanged),
    modified: asInt(exec.modified),
    added: asInt(exec.added),
    removed: asInt(exec.removed),
    risk_counts: {
      CRITICAL: asInt(rawCounts.CRITICAL),
      HIGH: asInt(rawCounts.HIGH),
      MEDIUM: asInt(rawCounts.MEDIUM),
      LOW: asInt(rawCounts.LOW),
    },
  };
}

function reportNavSections(report) {
  if (!report) return [];
  const sections = [{ id: "overview", label: "Tổng quan" }];
  if ((report.documents ?? []).some((item) => item.title || item.document_id)) {
    sections.push({ id: "documents", label: "Tài liệu" });
  }
  sections.push({ id: "statistics", label: "Thống kê" });
  const riskItems = report.risk_summary?.items ?? [];
  const riskLevels = report.risk_summary?.by_level ?? [];
  if (riskItems.length > 0 || riskLevels.some((row) => asInt(row.count) > 0)) {
    sections.push({ id: "risks", label: "Rủi ro" });
  }
  if ((report.changed_clauses ?? []).length > 0) {
    sections.push({ id: "changed", label: "Điều khoản đã sửa" });
  }
  if ((report.added_clauses ?? []).length > 0) {
    sections.push({ id: "added", label: "Điều khoản thêm mới" });
  }
  if ((report.removed_clauses ?? []).length > 0) {
    sections.push({ id: "removed", label: "Điều khoản đã xoá" });
  }
  const unchangedCount = asInt(report.unchanged_clauses?.count);
  if (unchangedCount > 0 || (report.unchanged_clauses?.clause_ids ?? []).length > 0) {
    sections.push({ id: "unchanged", label: "Không đổi" });
  }
  return sections;
}

function clauseStatusKey(status) {
  return String(status ?? "").toUpperCase();
}

function clauseMatchesQuery(clause, query, documents = []) {
  const token = query.trim().toLowerCase();
  if (!token) return true;
  const names = documents.map((item) => asString(item.title)).filter(Boolean).join(" ");
  const haystack = [
    clause.clause_id,
    clause.display_id,
    displayClauseId(clause.clause_id),
    clause.status,
    clause.risk_level,
    clause.risk_category,
    clause.change,
    names,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(token);
}

function filterReportClauses(clauses, filters, documents = []) {
  return clauses.filter((clause) => {
    const key = clauseStatusKey(clause.status);
    if (filters.status === "modified" && key !== "MODIFIED") return false;
    if (filters.status === "added" && key !== "ADDED") return false;
    if (filters.status === "removed" && key !== "REMOVED") return false;
    if (filters.status === "unchanged" && key !== "UNCHANGED") return false;
    if (
      filters.risk !== "all" &&
      String(clause.risk_level ?? "").toUpperCase() !== filters.risk
    ) {
      return false;
    }
    return clauseMatchesQuery(clause, filters.query, documents);
  });
}

function findClauseId(clauses, param) {
  const raw = asString(param);
  if (!raw) return null;
  const upper = raw.toUpperCase();
  const stripped = displayClauseId(raw).toUpperCase();
  for (const clause of clauses) {
    const id = asString(clause.clause_id);
    const display = asString(clause.display_id) ?? (id ? displayClauseId(id) : null);
    const candidates = [id, display].filter(Boolean).map((value) => String(value));
    if (candidates.some((value) => value === raw || value.toUpperCase() === upper)) {
      return id ?? display;
    }
    if (display && display.toUpperCase() === stripped) return id ?? display;
  }
  return null;
}

function exportEnabled(status) {
  return String(status ?? "").toLowerCase() === "ready";
}

function exactSourceHref(workspaceId, evidence) {
  const documentId = asString(evidence.document_id);
  if (!workspaceId || !documentId) return null;
  const page = evidence.page_number;
  const hasPage = typeof page === "number" && Number.isFinite(page) && page > 0;
  const chunkId = asString(evidence.chunk_id);
  if (!hasPage && !chunkId) return null;
  const params = new URLSearchParams();
  params.set("view", "original");
  if (hasPage) params.set("page", String(Math.trunc(page)));
  if (chunkId) params.set("chunk", chunkId);
  return `/workspaces/${workspaceId}/documents/${documentId}?${params.toString()}`;
}

function evidenceVerificationLabel(state) {
  switch (String(state ?? "").toLowerCase()) {
    case "verified":
      return "Bằng chứng đã xác minh";
    case "partial":
      return "Bằng chứng xác minh một phần";
    default:
      return "Bằng chứng cần xác minh";
  }
}

function isVerifiedEvidence(state) {
  return String(state ?? "").toLowerCase() === "verified";
}

function reportHttpMessage(status, rawMessage) {
  if (status === 403) return "Bạn không có quyền xem báo cáo này.";
  if (status === 404) return "Không tìm thấy báo cáo.";
  if (status === 409) return "Báo cáo chưa sẵn sàng.";
  if (status === 422) return "Dữ liệu báo cáo không hợp lệ.";
  if (status >= 500) return "Không tải được báo cáo. Vui lòng thử lại.";
  const text = asString(rawMessage);
  if (text && !/traceback|sqlalchemy|exception|\.py\b/i.test(text)) return text;
  return "Không tải được báo cáo.";
}

function emptyClauseMessage(kind) {
  if (kind === "search") return "Không có kết quả khớp bộ lọc hoặc từ khoá.";
  if (kind === "risks") return "Không phát hiện thay đổi rủi ro cao.";
  if (kind === "added") return "Không có điều khoản được đánh dấu thêm mới.";
  if (kind === "removed") return "Không có điều khoản được đánh dấu đã xoá.";
  return "Không có điều khoản đã sửa trong báo cáo này.";
}

function assert(cond, msg) {
  if (!cond) {
    console.error(`FAIL: ${msg}`);
    process.exit(1);
  }
}

const preview = {
  comparison_id: "cmp-1",
  comparison_ready: true,
  has_contract_report: true,
  comparison_report: {
    metadata: { title: "Contract Comparison Report", generated_at: "2026-08-16T00:00:00Z" },
    executive_summary: {
      total_clauses: 12,
      unchanged: 8,
      modified: 4,
      added: 2,
      removed: 0,
      risk_counts: { CRITICAL: 2, HIGH: 1, MEDIUM: 0, LOW: 0 },
    },
    documents: [
      { side: "V1", title: "Hop_dong_mau_Ra_soat_Phap_ly_V1.pdf", document_id: "d1" },
      { side: "V2", title: "Hop_dong_mau_Ra_soat_Phap_ly_V2.pdf", document_id: "d2" },
    ],
    risk_summary: {
      by_level: [
        { level: "CRITICAL", count: 2 },
        { level: "HIGH", count: 1 },
        { level: "MEDIUM", count: 0 },
        { level: "LOW", count: 0 },
      ],
      items: [
        { clause_id: "CLAUSE:8.2", risk_level: "CRITICAL", risk_category: "LIABILITY" },
      ],
    },
    changed_clauses: [
      { clause_id: "CLAUSE:2.1", display_id: "2.1", status: "MODIFIED", change: "Scope" },
      { clause_id: "CLAUSE:3.1", display_id: "3.1", status: "MODIFIED", change: "Payment" },
      {
        clause_id: "CLAUSE:8.2",
        display_id: "8.2",
        status: "MODIFIED",
        risk_level: "CRITICAL",
        risk_category: "LIABILITY",
        change: "Liability cap",
      },
      {
        clause_id: "CLAUSE:11.2",
        display_id: "11.2",
        status: "MODIFIED",
        risk_level: "HIGH",
        change: "Negotiation period",
      },
    ],
    added_clauses: [
      { clause_id: "CLAUSE:8.3", display_id: "8.3", status: "ADDED" },
      { clause_id: "CLAUSE:9.3", display_id: "9.3", status: "ADDED" },
    ],
    removed_clauses: [],
    unchanged_clauses: {
      count: 8,
      clause_ids: ["CLAUSE:1.1", "CLAUSE:4.1", "CLAUSE:5.1"],
    },
    detailed_clause_comparisons: [
      {
        clause_id: "CLAUSE:8.2",
        display_id: "8.2",
        status: "MODIFIED",
        evidence: [
          {
            side: "V1",
            document_id: "d1",
            page_number: 12,
            clause_id: "CLAUSE:8.2",
            verification_state: "verified",
          },
          {
            side: "V2",
            document_id: "d2",
            page_number: 0,
            verification_state: "unverified",
          },
        ],
      },
    ],
  },
};

const report = unwrapComparisonReport(preview);
assert(report !== null, "unwrap comparison report");

const counts = executiveCounts(report);
assert(counts.total === 12, "backend total");
assert(counts.unchanged === 8, "backend unchanged");
assert(counts.modified === 4, "backend modified — do not recount cards");
assert(counts.added === 2, "backend added");
assert(counts.removed === 0, "backend removed");
assert(counts.risk_counts.CRITICAL === 2, "risk critical from payload");

const addedIds = (report.added_clauses ?? []).map((row) => row.clause_id);
assert(!addedIds.includes("CLAUSE:1.2"), "1.2 is not ADDED");
assert(!addedIds.includes("CLAUSE:1.3"), "1.3 is not ADDED");
assert(addedIds.includes("CLAUSE:8.3"), "8.3 ADDED from backend");
assert((report.removed_clauses ?? []).length === 0, "no false REMOVED");

const nav = reportNavSections(report);
assert(nav.some((item) => item.id === "changed"), "nav changed");
assert(nav.some((item) => item.id === "added"), "nav added");
assert(!nav.some((item) => item.id === "removed"), "no removed nav when empty");
assert(nav.some((item) => item.id === "risks"), "nav risks");

const critical = filterReportClauses(report.changed_clauses, {
  status: "all",
  risk: "CRITICAL",
  query: "",
});
assert(critical.length === 1 && critical[0].clause_id === "CLAUSE:8.2", "risk filter");

const searched = filterReportClauses(report.changed_clauses, {
  status: "all",
  risk: "all",
  query: "liability",
});
assert(searched.length === 1, "search change summary");

const byDoc = filterReportClauses(report.changed_clauses, {
  status: "all",
  risk: "all",
  query: "Hop_dong_mau_Ra_soat_Phap_ly_V1",
}, report.documents);
assert(byDoc.length === report.changed_clauses.length, "search document name");

const none = filterReportClauses(report.changed_clauses, {
  status: "removed",
  risk: "all",
  query: "",
});
assert(none.length === 0, "status filter empty");
assert(emptyClauseMessage("search").includes("Không có kết quả"), "empty search copy");

assert(findClauseId(report.changed_clauses, "8.2") === "CLAUSE:8.2", "deep link 8.2");
assert(findClauseId(report.changed_clauses, "CLAUSE:11.2") === "CLAUSE:11.2", "deep link id");
assert(findClauseId(report.changed_clauses, "missing") === null, "unknown clause");

assert(exportEnabled("ready") === true, "export ready");
assert(exportEnabled("pending") === false, "export pending disabled");
assert(exportEnabled("failed") === false, "export failed disabled");

const verifiedHref = exactSourceHref("ws", report.detailed_clause_comparisons[0].evidence[0]);
assert(
  verifiedHref === "/workspaces/ws/documents/d1?view=original&page=12",
  "exact page navigation",
);
const noGuess = exactSourceHref("ws", report.detailed_clause_comparisons[0].evidence[1]);
assert(noGuess === null, "do not open page 1 without exact location");
assert(exactSourceHref("ws", { document_id: "d1" }) === null, "document only is not enough");

assert(isVerifiedEvidence("verified") === true, "verified flag");
assert(isVerifiedEvidence("unverified") === false, "unverified flag");
assert(
  evidenceVerificationLabel("verified") !== evidenceVerificationLabel("unverified"),
  "distinct verification labels",
);

assert(reportHttpMessage(403) === "Bạn không có quyền xem báo cáo này.", "403 copy");
assert(reportHttpMessage(404) === "Không tìm thấy báo cáo.", "404 copy");
assert(reportHttpMessage(409) === "Báo cáo chưa sẵn sàng.", "409 copy");
assert(
  reportHttpMessage(500, "Traceback (most recent call last)"),
  "500 hides traceback",
);
assert(
  reportHttpMessage(500, "Traceback (most recent call last)") ===
    "Không tải được báo cáo. Vui lòng thử lại.",
  "unsafe message stripped",
);

assert(unwrapComparisonReport({ has_contract_report: false }) === null, "no preview model");

console.log("test-comparison-report-preview-ui: ok");
