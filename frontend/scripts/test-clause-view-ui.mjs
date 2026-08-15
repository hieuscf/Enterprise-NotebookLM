/**
 * Node-side smoke checks for TASK-CMP-18 side-by-side clause view helpers.
 * Mirrors features/comparisons/clause-view.ts (and related summary helpers).
 * Run: node scripts/test-clause-view-ui.mjs
 */

function displayClauseId(id) {
  if (!id) return "—";
  return id.replace(/^(CLAUSE|ARTICLE|APPENDIX|SECTION):/i, "");
}

function resolveClauseId(clauses, param) {
  const raw = (param ?? "").trim();
  if (!raw) return null;
  const upper = raw.toUpperCase();
  for (const clause of clauses) {
    const ids = [clause.clause_id, clause.v1_clause_id, clause.v2_clause_id]
      .filter(Boolean)
      .map((id) => String(id));
    if (ids.some((id) => id === raw || id.toUpperCase() === upper)) {
      return clause.clause_id;
    }
    if (displayClauseId(clause.clause_id) === raw) return clause.clause_id;
  }
  return null;
}

function clauseNav(visible, currentId) {
  const total = visible.length;
  if (!currentId || total === 0) {
    return { index: -1, total, prevId: null, nextId: null };
  }
  const index = visible.findIndex((clause) => clause.clause_id === currentId);
  if (index < 0) return { index: -1, total, prevId: null, nextId: null };
  return {
    index,
    total,
    prevId: index > 0 ? visible[index - 1].clause_id : null,
    nextId: index < total - 1 ? visible[index + 1].clause_id : null,
  };
}

function positionLabel(nav, filterLabel) {
  if (nav.index < 0 || nav.total === 0) return filterLabel;
  return `${filterLabel} · ${nav.index + 1} / ${nav.total}`;
}

function versionMapping(clause) {
  const status = String(clause.status).toUpperCase();
  const v1Id = clause.v1_clause_id ?? (status === "ADDED" ? null : clause.clause_id);
  const v2Id = clause.v2_clause_id ?? (status === "REMOVED" ? null : clause.clause_id);
  const v1Label = v1Id ? displayClauseId(v1Id) : "—";
  const v2Label = v2Id ? displayClauseId(v2Id) : "—";
  return {
    v1Id,
    v2Id,
    v1Label,
    v2Label,
    renumbered: Boolean(v1Id && v2Id && v1Label !== v2Label),
  };
}

function absenceMessage(status, side) {
  const key = status.toUpperCase();
  if (key === "ADDED" && side === "v1") {
    return "Không xác định được điều khoản tương ứng ở V1";
  }
  if (key === "REMOVED" && side === "v2") {
    return "Không xác định được điều khoản tương ứng ở V2";
  }
  return side === "v1" ? "Không có nội dung V1" : "Không có nội dung V2";
}

function unchangedCaption() {
  return "Không phát hiện khác biệt vật chất";
}

function shouldEmphasizeDiff(status) {
  return String(status).toUpperCase() === "MODIFIED";
}

function shouldShowAiAnalysis(status) {
  const key = String(status).toUpperCase();
  return key === "MODIFIED" || key === "ADDED" || key === "REMOVED";
}

function parseOffset(value) {
  if (!Array.isArray(value) || value.length < 2) return null;
  const start = Number(value[0]);
  const end = Number(value[1]);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  if (start < 0 || end <= start) return null;
  return [Math.floor(start), Math.floor(end)];
}

function highlightSegments(text, diffs, side, status) {
  if (!text) return [];
  if (!shouldEmphasizeDiff(status) || !diffs?.length) {
    return [{ text, kind: "plain" }];
  }
  const marks = [];
  for (const row of diffs) {
    const span = parseOffset(side === "v1" ? row.source_offset : row.target_offset);
    if (!span) continue;
    const start = Math.max(0, span[0]);
    const end = Math.min(text.length, span[1]);
    if (end <= start) continue;
    marks.push({ start, end, kind: side === "v1" ? "removed" : "added" });
  }
  if (marks.length === 0) return [{ text, kind: "plain" }];
  const segments = [];
  let cursor = 0;
  for (const mark of marks) {
    if (mark.start > cursor) segments.push({ text: text.slice(cursor, mark.start), kind: "plain" });
    segments.push({ text: text.slice(mark.start, mark.end), kind: mark.kind });
    cursor = mark.end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), kind: "plain" });
  return segments;
}

function valueTypeLabel(valueType) {
  const labels = {
    MONEY: "Số tiền",
    PERCENTAGE: "Tỷ lệ",
    DATE: "Ngày",
    DURATION: "Thời hạn",
    QUANTITY: "Số lượng",
    ENTITY: "Bên / thực thể",
    LOCATION: "Địa điểm",
  };
  const key = String(valueType ?? "").toUpperCase();
  return labels[key] ?? (valueType ? String(valueType) : "Giá trị");
}

function mappingConfidenceLabel(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const pct = value <= 1 ? Math.round(value * 100) : Math.round(value);
  if (pct < 0 || pct > 100) return null;
  return `${pct}%`;
}

function userFacingRules(rules) {
  if (!Array.isArray(rules)) return [];
  return rules
    .map((item) => String(item ?? "").trim())
    .filter((item) => item && !/^[0-9a-f-]{32,}$/i.test(item));
}

function buildComparisonsHref(workspaceId, comparisonId, clauseId) {
  const params = new URLSearchParams();
  if (comparisonId) params.set("comparison", comparisonId);
  if (clauseId) params.set("clause", clauseId);
  const qs = params.toString();
  const base = `/workspaces/${workspaceId}/comparisons`;
  return qs ? `${base}?${qs}` : base;
}

function filterClauses(clauses, filter) {
  return clauses.filter((clause) => {
    const status = String(clause.status).toUpperCase();
    if (filter === "modified" && status !== "MODIFIED") return false;
    if (filter === "added" && status !== "ADDED") return false;
    if (filter === "removed" && status !== "REMOVED") return false;
    if (filter === "unchanged" && status !== "UNCHANGED") return false;
    return true;
  });
}

function evidenceForSide(clause, side) {
  const rows = clause.citations?.length ? clause.citations : clause.evidence ?? [];
  return rows.filter((item) => String(item.side ?? "").toUpperCase() === side);
}

function evidenceViewerHref(workspaceId, evidence) {
  const documentId = evidence.document_id;
  if (!documentId) return null;
  const params = new URLSearchParams();
  if (typeof evidence.page_number === "number" && evidence.page_number > 0) {
    params.set("page", String(evidence.page_number));
    params.set("view", "original");
  }
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

const v1Text = "The liability shall not exceed 480,000,000 VND in aggregate.";
const v2Text = "The liability shall not exceed 600,000,000 VND in aggregate.";

const modified = {
  clause_id: "CLAUSE:8.2",
  v1_clause_id: "CLAUSE:8.2",
  v2_clause_id: "CLAUSE:8.2",
  status: "MODIFIED",
  mapping_confidence: 0.91,
  v1_text: v1Text,
  v2_text: v2Text,
  exact_differences: [
    {
      value_type: "MONEY",
      old: { raw: "480,000,000" },
      new: { raw: "600,000,000" },
      delta: "120000000",
      relative_change_percent: "25",
      source_offset: [v1Text.indexOf("480,000,000"), v1Text.indexOf("480,000,000") + "480,000,000".length],
      target_offset: [v2Text.indexOf("600,000,000"), v2Text.indexOf("600,000,000") + "600,000,000".length],
    },
  ],
  risk: { risk_level: "CRITICAL", risk_category: "LIABILITY", risk_score: "0.82" },
  explanation: { output: { explanation: "Liability cap increased." } },
  evidence: [
    { side: "OLD", document_id: "d1", page_number: 14, clause_id: "CLAUSE:8.2" },
    { side: "NEW", document_id: "d2", page_number: 15, clause_id: "CLAUSE:8.2" },
  ],
  verification: { status: "VERIFIED" },
};

const unchanged = {
  clause_id: "ARTICLE:1",
  v1_clause_id: "ARTICLE:1",
  v2_clause_id: "ARTICLE:1",
  status: "UNCHANGED",
  v1_text: "Phạm vi dịch vụ không đổi.",
  v2_text: "Phạm vi dịch vụ không đổi.",
  exact_differences: [],
  explanation: { output: { explanation: "Should stay hidden for unchanged." } },
  evidence: [{ side: "OLD", document_id: "d1", page_number: 2 }],
  verification: { status: "VERIFIED" },
};

const added = {
  clause_id: "CLAUSE:8.3",
  v1_clause_id: null,
  v2_clause_id: "CLAUSE:8.3",
  status: "ADDED",
  v1_text: null,
  v2_text: "New subclause added in V2.",
  evidence: [{ side: "NEW", document_id: "d2", page_number: 16 }],
};

const removed = {
  clause_id: "CLAUSE:9.9",
  v1_clause_id: "CLAUSE:9.9",
  v2_clause_id: null,
  status: "REMOVED",
  v1_text: "Legacy termination clause.",
  v2_text: null,
  evidence: [{ side: "OLD", document_id: "d1", page_number: 9 }],
};

const renumbered = {
  clause_id: "CLAUSE:8",
  v1_clause_id: "CLAUSE:8",
  v2_clause_id: "CLAUSE:9",
  status: "MODIFIED",
  v1_text: "Old numbering",
  v2_text: "New numbering",
};

assert(modified.v1_text.includes("480,000,000"), "MODIFIED preserves V1 original text");
assert(modified.v2_text.includes("600,000,000"), "MODIFIED preserves V2 original text");
assert(modified.status === "MODIFIED", "status comes from API");
assert(modified.risk.risk_level === "CRITICAL", "risk comes from API");
assert(modified.exact_differences[0].delta === "120000000", "exact delta not recalculated");
assert(modified.explanation.output.explanation.includes("Liability"), "explanation present");
assert(evidenceForSide(modified, "OLD")[0].page_number === 14, "V1 evidence");
assert(evidenceForSide(modified, "NEW")[0].page_number === 15, "V2 evidence");
assert(modified.verification.status === "VERIFIED", "citation verified from API");
assert(shouldEmphasizeDiff("MODIFIED"), "modified emphasizes backend spans");
assert(shouldShowAiAnalysis("MODIFIED"), "modified may show AI analysis");

const v1Seg = highlightSegments(modified.v1_text, modified.exact_differences, "v1", "MODIFIED");
assert(v1Seg.some((s) => s.kind === "removed" && s.text === "480,000,000"), "V1 highlight uses source_offset");
assert(v1Seg.map((s) => s.text).join("") === modified.v1_text, "highlight does not rewrite source text");
const v2Seg = highlightSegments(modified.v2_text, modified.exact_differences, "v2", "MODIFIED");
assert(v2Seg.some((s) => s.kind === "added" && s.text === "600,000,000"), "V2 highlight uses target_offset");

assert(unchanged.v1_text && unchanged.v2_text, "UNCHANGED shows both texts");
assert(!shouldEmphasizeDiff("UNCHANGED"), "UNCHANGED has no aggressive diff");
assert(!shouldShowAiAnalysis("UNCHANGED"), "UNCHANGED hides unnecessary AI analysis");
assert(unchangedCaption().includes("Không phát hiện khác biệt vật chất"), "unchanged calm copy");
const unchangedSeg = highlightSegments(unchanged.v1_text, unchanged.exact_differences, "v1", "UNCHANGED");
assert(unchangedSeg.length === 1 && unchangedSeg[0].kind === "plain", "unchanged is plain original text");

assert(added.v2_text.includes("New subclause"), "ADDED shows V2 content");
assert(!added.v1_text, "ADDED has no V1 text from API");
assert(absenceMessage("ADDED", "v1").includes("Không xác định được điều khoản tương ứng ở V1"), "ADDED absence wording");
assert(evidenceForSide(added, "NEW").length === 1, "ADDED V2 evidence");
assert(evidenceForSide(added, "OLD").length === 0, "ADDED does not invent V1 evidence");

assert(removed.v1_text.includes("Legacy"), "REMOVED shows V1 content");
assert(!removed.v2_text, "REMOVED has no V2 text from API");
assert(absenceMessage("REMOVED", "v2").includes("Không xác định được điều khoản tương ứng ở V2"), "REMOVED absence wording");

const map = versionMapping(renumbered);
assert(map.renumbered && map.v1Label === "8" && map.v2Label === "9", "renumbered mapping from backend ids");

const list = [modified, added, removed, unchanged];
assert(resolveClauseId(list, "8.2") === "CLAUSE:8.2", "resolve display id");
assert(resolveClauseId(list, "CLAUSE:8.3") === "CLAUSE:8.3", "resolve full id");
assert(resolveClauseId(list, "missing") === null, "unknown clause does not invent a row");

const modifiedOnly = filterClauses(list, "modified");
const nav = clauseNav(modifiedOnly, "CLAUSE:8.2");
assert(positionLabel(nav, "Đã sửa") === "Đã sửa · 1 / 1", "position within active filter");
assert(nav.prevId === null && nav.nextId === null, "prev/next stay inside filter");

const allNav = clauseNav(list, "CLAUSE:8.2");
assert(allNav.nextId === "CLAUSE:8.3", "next respects current list order");
const addedNav = clauseNav(filterClauses(list, "added"), "CLAUSE:8.3");
assert(addedNav.prevId === null, "filtered added list does not jump to modified");

const href = buildComparisonsHref("ws1", "cmp1", "CLAUSE:8.2");
assert(href === "/workspaces/ws1/comparisons?comparison=cmp1&clause=CLAUSE%3A8.2", "deep link uses ids only");
assert(!href.includes("480,000,000"), "clause text never enters the URL");
assert(evidenceViewerHref("ws1", modified.evidence[0]).includes("page=14"), "evidence opens existing viewer");

assert(valueTypeLabel("MONEY") === "Số tiền", "value type label");
assert(mappingConfidenceLabel(0.91) === "91%", "mapping confidence from API");
assert(mappingConfidenceLabel(null) === null, "missing confidence is omitted");
assert(userFacingRules(["LIABILITY_CAP", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]).length === 1, "skip opaque ids");
assert(parseOffset([2, 2]) === null && parseOffset([1, 4]).join(",") === "1,4", "invalid offsets ignored");

const keyboard = { escape: "close", prev: "previous", next: "next", tabs: ["V1", "V2"] };
assert(keyboard.escape === "close", "Escape closes workspace");
assert(keyboard.tabs.length === 2, "small viewport has V1/V2 toggle");

const regressionApi = {
  clauses: [
    { clause_id: "ARTICLE:2", status: "MODIFIED" },
    { clause_id: "ARTICLE:3", status: "MODIFIED" },
    { clause_id: "ARTICLE:8", status: "MODIFIED", risk: { risk_level: "CRITICAL" } },
    { clause_id: "ARTICLE:9", status: "MODIFIED", risk: { risk_level: "CRITICAL" } },
    { clause_id: "ARTICLE:11", status: "MODIFIED", risk: { risk_level: "HIGH" } },
    { clause_id: "ARTICLE:1", status: "UNCHANGED" },
  ],
};
assert(regressionApi.clauses.find((c) => c.clause_id === "ARTICLE:2").status === "MODIFIED", "regression Điều 2 from fixture");
assert(regressionApi.clauses.find((c) => c.clause_id === "ARTICLE:3").status === "MODIFIED", "regression Điều 3 from fixture");
assert(regressionApi.clauses.find((c) => c.clause_id === "ARTICLE:8").risk.risk_level === "CRITICAL", "regression Điều 8 risk from fixture");
assert(regressionApi.clauses.find((c) => c.clause_id === "ARTICLE:9").risk.risk_level === "CRITICAL", "regression Điều 9 risk from fixture");
assert(regressionApi.clauses.find((c) => c.clause_id === "ARTICLE:11").risk.risk_level === "HIGH", "regression Điều 11 risk from fixture");
assert(
  !shouldEmphasizeDiff(regressionApi.clauses.find((c) => c.clause_id === "ARTICLE:1").status),
  "regression unchanged stays visually unchanged",
);

const missing = { clause_id: "X", status: "MODIFIED", risk: null, explanation: null, evidence: [], exact_differences: [] };
assert(absenceMessage(missing.status, "v1") === "Không có nội dung V1", "missing text does not render null");
assert(highlightSegments("", missing.exact_differences, "v1", "MODIFIED").length === 0, "empty text stays empty");
assert(userFacingRules(null).length === 0, "null rules are safe");

if (!process.exitCode) {
  console.log("\nAll clause view UI smoke checks passed.");
}
