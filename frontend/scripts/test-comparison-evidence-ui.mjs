/**
 * Node-side smoke checks for TASK-CMP-19 Comparison Evidence & Citation Panel.
 * Mirrors features/comparisons/comparison-evidence.ts (and related helpers).
 * Run: node scripts/test-comparison-evidence-ui.mjs
 */

function displayClauseId(id) {
  if (!id) return "—";
  return id.replace(/^(CLAUSE|ARTICLE|APPENDIX|SECTION):/i, "");
}

function asString(value) {
  if (value == null) return null;
  const text = String(value).trim();
  return text ? text : null;
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

function formatExactDifference(row) {
  const valueType = asString(row.value_type) ?? asString(row.change_type) ?? "Giá trị";
  const oldRaw = asString(row.old?.raw) ?? asString(row.old?.value);
  const newRaw = asString(row.new?.raw) ?? asString(row.new?.value);
  return {
    label: valueType,
    oldDisplay: oldRaw ?? "—",
    newDisplay: newRaw ?? "—",
  };
}

function shortChangeSummary(clause) {
  const diffs = clause.exact_differences ?? [];
  if (diffs.length > 0) {
    const first = formatExactDifference(diffs[0]);
    if (first.oldDisplay !== "—" || first.newDisplay !== "—") {
      return `${first.label}: ${first.oldDisplay} → ${first.newDisplay}`;
    }
  }
  const status = String(clause.status).toUpperCase();
  if (status === "ADDED") return "Điều khoản được thêm ở phiên bản V2.";
  if (status === "REMOVED") return "Điều khoản bị xoá khỏi phiên bản V2.";
  if (status === "MODIFIED") return "Nội dung đã thay đổi.";
  return "Không có thay đổi trong phạm vi so sánh.";
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
  const qs = params.toString();
  const base = `/workspaces/${workspaceId}/documents/${documentId}`;
  return qs ? `${base}?${qs}` : base;
}

function sourceTypeLabel(value) {
  const labels = {
    TEXT_SPAN: "Đoạn nguồn",
    CHUNK: "Đoạn văn",
    CLAUSE: "Điều khoản",
    PAGE: "Trang",
  };
  const key = String(value ?? "").trim().toUpperCase();
  if (!key) return null;
  return labels[key] ?? null;
}

function evidenceSide(item) {
  const side = String(item.side ?? "").toUpperCase();
  if (side === "OLD") return "v1";
  if (side === "NEW") return "v2";
  return "other";
}

function isPrimaryEvidence(item) {
  return String(item.role ?? "").toUpperCase() === "PRIMARY";
}

function itemCheckStatus(clause, evidenceId) {
  if (!evidenceId) return null;
  const rows = clause.verification?.evidence_results ?? [];
  const match = rows.find((row) => row.evidence_id === evidenceId);
  return match?.status ? String(match.status).toUpperCase() : null;
}

function itemVerificationState(clause, item) {
  const id = item.evidence_id ? String(item.evidence_id) : null;
  const check = itemCheckStatus(clause, id);
  if (check === "VALID") return "verified";
  if (check === "INVALID" || check === "MISMATCH") return "unverified";
  if (check === "MISSING" || check === "UNAVAILABLE") return "unavailable";
  const verifiedIds = clause.verification?.verified_evidence_ids ?? [];
  const invalidIds = clause.verification?.invalid_evidence_ids ?? [];
  if (id && verifiedIds.includes(id)) return "verified";
  if (id && invalidIds.includes(id)) return "unverified";
  const finding = String(clause.verification?.status ?? "").toUpperCase();
  if (finding === "INSUFFICIENT_EVIDENCE") return "unavailable";
  if (finding === "PARTIALLY_VERIFIED") return "partial";
  if (finding === "VERIFIED") return "unverified";
  if (finding === "INVALID") return "unverified";
  return evidenceState(clause);
}

function evidenceExcerpt(item, clause) {
  const provided = (item.display_text ?? "").trim();
  if (provided) return provided;
  const start = item.start_offset;
  const end = item.end_offset;
  if (typeof start !== "number" || typeof end !== "number" || end <= start) return null;
  const side = evidenceSide(item);
  const source = side === "v2" ? clause.v2_text : clause.v1_text;
  if (!source || end > source.length || start < 0) return null;
  return source.slice(start, end);
}

function sourceLocationLabel(item, documentTitle) {
  const parts = [];
  const title = (documentTitle ?? "").trim();
  if (title) parts.push(title);
  if (item.clause_id) parts.push(`Điều ${displayClauseId(item.clause_id)}`);
  if (typeof item.page_number === "number" && item.page_number > 0) {
    parts.push(`Trang ${item.page_number}`);
  }
  const typeLabel = sourceTypeLabel(item.source_type);
  if (typeLabel) parts.push(typeLabel);
  return parts.join(" · ") || "Vị trí nguồn không có";
}

function allEvidenceItems(clause) {
  if (Array.isArray(clause.evidence)) return clause.evidence;
  return Array.isArray(clause.citations) ? clause.citations : [];
}

function groupedEvidence(clause) {
  const groups = { v1: [], v2: [], other: [] };
  allEvidenceItems(clause).forEach((evidence, index) => {
    const side = evidenceSide(evidence);
    groups[side].push({
      key: `${evidence.evidence_id || "ev"}-${side}-${index}`,
      evidence,
      side,
      verification: itemVerificationState(clause, evidence),
      primary: isPrimaryEvidence(evidence),
      excerpt: evidenceExcerpt(evidence, clause),
      locationLabel: sourceLocationLabel(evidence),
    });
  });
  return groups;
}

function flattenEvidenceItems(clause) {
  const groups = groupedEvidence(clause);
  return [...groups.v1, ...groups.v2, ...groups.other];
}

function findingContext(clause) {
  const diffs = clause.exact_differences ?? [];
  if (diffs.length > 0) {
    const first = formatExactDifference(diffs[0]);
    if (first.oldDisplay !== "—" || first.newDisplay !== "—") {
      return `${first.label}: ${first.oldDisplay} → ${first.newDisplay}`;
    }
  }
  return shortChangeSummary(clause);
}

function aiEvidenceIds(clause) {
  const ids = clause.explanation?.output?.evidence_ids;
  if (!Array.isArray(ids)) return [];
  return ids.map((id) => String(id).trim()).filter(Boolean);
}

function aiCitationRefs(clause) {
  const items = flattenEvidenceItems(clause);
  return aiEvidenceIds(clause).map((evidenceId, index) => ({
    index: index + 1,
    evidenceId,
    item: items.find((row) => row.evidence.evidence_id === evidenceId) ?? null,
  }));
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

function absenceStatus(clause, side) {
  const status = String(clause.status).toUpperCase();
  const absence = String(clause.verification?.absence_status ?? "").toUpperCase();
  if (status === "ADDED" && side === "v1") {
    if (absence === "ABSENCE_CONFIRMED") {
      return "Nguồn xác nhận không có điều khoản tương ứng ở V1.";
    }
    return absenceMessage(status, "v1");
  }
  if (status === "REMOVED" && side === "v2") {
    if (absence === "ABSENCE_CONFIRMED") {
      return "Nguồn xác nhận không có điều khoản tương ứng ở V2.";
    }
    return absenceMessage(status, "v2");
  }
  return null;
}

function buildEvidenceSourceHref(workspaceId, evidence, fallbackDocumentId, fallbackVersionId) {
  const href = evidenceViewerHref(workspaceId, evidence, fallbackDocumentId, fallbackVersionId);
  if (!href) return null;
  const citationId = (evidence.evidence_id ?? "").trim();
  if (!citationId) return href;
  const join = href.includes("?") ? "&" : "?";
  return `${href}${join}citation=${encodeURIComponent(citationId)}`;
}

function copyCitationText(item, versionLabel) {
  return [item.locationLabel, versionLabel, item.excerpt].filter(Boolean).join("\n");
}

function hasSourceSpan(item) {
  return (
    typeof item.start_offset === "number" &&
    typeof item.end_offset === "number" &&
    item.end_offset > item.start_offset
  );
}

function shouldShowAiAnalysis(status) {
  const key = String(status).toUpperCase();
  return key === "MODIFIED" || key === "ADDED" || key === "REMOVED";
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

const v1Text = 'The liability shall not exceed 480,000,000 VND in aggregate.';
const v2Text = 'The liability shall not exceed 600,000,000 VND in aggregate.';

const verifiedModified = {
  clause_id: "CLAUSE:8.2",
  status: "MODIFIED",
  v1_text: v1Text,
  v2_text: v2Text,
  exact_differences: [
    {
      value_type: "MONEY",
      old: { raw: "480,000,000" },
      new: { raw: "600,000,000" },
    },
  ],
  risk: { risk_level: "CRITICAL", risk_category: "Liability", reason: "Cap increased." },
  explanation: {
    output: {
      explanation: "The liability cap was increased.",
      evidence_ids: ["ev-v1", "ev-v2"],
    },
  },
  evidence: [
    {
      evidence_id: "ev-v1",
      side: "OLD",
      role: "PRIMARY",
      document_id: "doc-a",
      document_version_id: "ver-a",
      clause_id: "CLAUSE:8.2",
      page_number: 14,
      chunk_id: "chunk-a",
      start_offset: 32,
      end_offset: 43,
      source_type: "TEXT_SPAN",
      display_text: "480,000,000",
    },
    {
      evidence_id: "ev-v2",
      side: "NEW",
      role: "SECONDARY",
      document_id: "doc-b",
      document_version_id: "ver-b",
      clause_id: "CLAUSE:8.2",
      page_number: 15,
      chunk_id: "chunk-b",
      source_type: "TEXT_SPAN",
      display_text: "600,000,000",
    },
    {
      evidence_id: "ev-v2-section",
      side: "NEW",
      document_id: "doc-b",
      document_version_id: "ver-b",
      page_number: 15,
      source_type: "PAGE",
      display_text: "Section 8 Limitation of Liability",
    },
  ],
  verification: {
    status: "VERIFIED",
    human_message: "Verified against source document",
    verified_evidence_ids: ["ev-v1", "ev-v2", "ev-v2-section"],
    evidence_results: [
      { evidence_id: "ev-v1", status: "VALID" },
      { evidence_id: "ev-v2", status: "VALID" },
      { evidence_id: "ev-v2-section", status: "VALID" },
    ],
  },
};

const unverified = {
  clause_id: "CLAUSE:9",
  status: "MODIFIED",
  evidence: [
    {
      evidence_id: "ev-u",
      side: "NEW",
      document_id: "doc-b",
      page_number: 22,
      display_text: "unverified excerpt",
    },
  ],
  verification: {
    status: "UNVERIFIED",
    human_message: "This citation could not be fully verified against the source.",
    verified_evidence_ids: [],
    invalid_evidence_ids: ["ev-u"],
  },
};

const pageButNotVerified = {
  clause_id: "CLAUSE:10",
  status: "MODIFIED",
  evidence: [
    {
      evidence_id: "ev-page",
      side: "OLD",
      document_id: "doc-a",
      page_number: 3,
      display_text: "has a page but is not verified",
    },
  ],
  verification: {
    status: "VERIFIED",
    verified_evidence_ids: [],
  },
};

const partial = {
  clause_id: "CLAUSE:11",
  status: "MODIFIED",
  evidence: [
    {
      evidence_id: "ev-ok",
      side: "OLD",
      document_id: "doc-a",
      page_number: 4,
      display_text: "matched",
    },
    {
      evidence_id: "ev-miss",
      side: "NEW",
      document_id: "doc-b",
      display_text: "partial",
    },
  ],
  verification: {
    status: "PARTIALLY_VERIFIED",
    human_message: "Source location verified, but excerpt matching could not be fully confirmed.",
    verified_evidence_ids: ["ev-ok"],
    evidence_results: [
      { evidence_id: "ev-ok", status: "VALID" },
      { evidence_id: "ev-miss", status: "MISMATCH", reasons: ["Excerpt could not be confirmed."] },
    ],
  },
};

const missing = {
  clause_id: "CLAUSE:12",
  status: "MODIFIED",
  evidence: [],
  verification: { status: "INSUFFICIENT_EVIDENCE" },
};

const added = {
  clause_id: "CLAUSE:8.3",
  status: "ADDED",
  v2_text: "New subclause on notice.",
  evidence: [
    {
      evidence_id: "ev-added",
      side: "NEW",
      document_id: "doc-b",
      document_version_id: "ver-b",
      page_number: 16,
      display_text: "New subclause on notice.",
    },
  ],
  verification: { status: "VERIFIED", verified_evidence_ids: ["ev-added"] },
};

const removed = {
  clause_id: "CLAUSE:19",
  status: "REMOVED",
  v1_text: "Legacy audit right.",
  evidence: [
    {
      evidence_id: "ev-removed",
      side: "OLD",
      document_id: "doc-a",
      document_version_id: "ver-a",
      page_number: 30,
      display_text: "Legacy audit right.",
    },
  ],
  verification: { status: "VERIFIED", verified_evidence_ids: ["ev-removed"] },
};

const unchanged = {
  clause_id: "CLAUSE:1",
  status: "UNCHANGED",
  v1_text: "Definitions.",
  v2_text: "Definitions.",
  evidence: [
    { evidence_id: "ev-u1", side: "OLD", document_id: "doc-a", page_number: 10, display_text: "Definitions." },
    { evidence_id: "ev-u2", side: "NEW", document_id: "doc-b", page_number: 10, display_text: "Definitions." },
  ],
  verification: { status: "VERIFIED", verified_evidence_ids: ["ev-u1", "ev-u2"] },
};

const sparse = {
  clause_id: "CLAUSE:X",
  status: "MODIFIED",
  evidence: [
    {
      evidence_id: "ev-sparse",
      side: "NEW",
      document_id: "doc-b",
    },
  ],
  verification: { status: "UNVERIFIED", verified_evidence_ids: [] },
};

const groups = groupedEvidence(verifiedModified);
assert(groups.v1.length === 1 && groups.v2.length === 2, "V1 and V2 evidence are separated");
assert(groups.v1[0].verification === "verified" && groups.v2[0].verification === "verified", "verified citations render as verified");
assert(groups.v1[0].primary === true, "PRIMARY role comes from backend");
assert(groups.v2[0].primary === false, "do not invent primary evidence");
assert(flattenEvidenceItems(verifiedModified).length === 3, "multiple evidence items are listed");
assert(groups.v1[0].excerpt === "480,000,000", "source excerpt is preserved");
assert(findingContext(verifiedModified).includes("480,000,000"), "finding shows exact change");
assert(findingContext(verifiedModified).includes("600,000,000"), "finding includes V2 value");

const v1Href = buildEvidenceSourceHref("ws1", verifiedModified.evidence[0]);
assert(v1Href.includes("/workspaces/ws1/documents/doc-a"), "opens correct V1 document");
assert(v1Href.includes("version=ver-a"), "opens correct V1 version");
assert(v1Href.includes("page=14"), "opens correct V1 page");
assert(v1Href.includes("citation=ev-v1"), "passes citation id for highlight session");
assert(v1Href.includes("chunk=chunk-a"), "passes backend chunk when present");
assert(hasSourceSpan(verifiedModified.evidence[0]), "source span is passed through, not recalculated");
assert(!v1Href.includes("480,000,000"), "excerpt is not placed in the URL");

const v2Href = buildEvidenceSourceHref("ws1", verifiedModified.evidence[1]);
assert(v2Href.includes("/documents/doc-b") && v2Href.includes("version=ver-b") && v2Href.includes("page=15"), "V2 source navigation uses backend fields");

const ai = aiCitationRefs(verifiedModified);
assert(ai.length === 2 && ai[0].evidenceId === "ev-v1" && ai[1].evidenceId === "ev-v2", "AI citations use backend evidence_ids order");
assert(ai[0].item.side === "v1" && ai[1].item.side === "v2", "AI citation chips map to the correct evidence");
assert(shouldShowAiAnalysis("MODIFIED"), "AI analysis is shown separately for modified clauses");

const unverifiedItem = flattenEvidenceItems(unverified)[0];
assert(unverifiedItem.verification === "unverified", "unverified state renders");
assert(unverifiedItem.verification !== "verified", "UI does not imply verified evidence");
assert(evidenceStateLabel(unverifiedItem.verification) === "Chưa xác minh", "unverified label is explicit");

assert(itemVerificationState(pageButNotVerified, pageButNotVerified.evidence[0]) === "unverified", "page presence does not imply verified");
assert(itemVerificationState(pageButNotVerified, pageButNotVerified.evidence[0]) !== "verified", "no frontend verification inference");

const partialItems = flattenEvidenceItems(partial);
assert(partialItems.find((row) => row.evidence.evidence_id === "ev-ok").verification === "verified", "partial finding keeps verified item");
assert(partialItems.find((row) => row.evidence.evidence_id === "ev-miss").verification === "unverified", "mismatch is not shown as verified");
assert(evidenceState(partial) === "partial", "finding-level partial status is preserved");
assert(sourceLocationLabel(partial.evidence[1]) === "Vị trí nguồn không có" || !String(partial.evidence[1].page_number), "missing page is omitted, not undefined");
assert(!sourceLocationLabel(partial.evidence[1]).includes("undefined"), "missing fields do not render undefined");
assert(!sourceLocationLabel(partial.evidence[1]).includes("null"), "missing fields do not render null");

assert(flattenEvidenceItems(missing).length === 0, "no evidence does not crash");
assert(evidenceState(missing) === "unavailable", "unavailable evidence state");
assert(evidenceStateLabel("unavailable") === "Không có bằng chứng", "unavailable copy");

assert(groupedEvidence(added).v1.length === 0, "ADDED does not invent V1 evidence");
assert(groupedEvidence(added).v2.length === 1, "ADDED shows V2 evidence");
assert(absenceStatus(added, "v1").includes("Không xác định được điều khoản tương ứng ở V1"), "ADDED uses backend absence wording");
assert(!absenceStatus(added, "v1").toLowerCase().includes("did not exist"), "ADDED does not claim the clause did not exist");

assert(groupedEvidence(removed).v2.length === 0, "REMOVED does not invent V2 evidence");
assert(groupedEvidence(removed).v1.length === 1, "REMOVED shows V1 evidence");
assert(absenceStatus(removed, "v2").includes("Không xác định được điều khoản tương ứng ở V2"), "REMOVED uses backend absence wording");

assert(!shouldShowAiAnalysis("UNCHANGED"), "unchanged avoids unnecessary AI");
assert(flattenEvidenceItems(unchanged).length === 2, "unchanged can still show source evidence");

const sparseItem = flattenEvidenceItems(sparse)[0];
assert(sparseItem.excerpt === null, "missing excerpt is not fabricated");
assert(!sourceLocationLabel(sparse.evidence[0]).includes("Trang"), "missing page is not fabricated");
assert(sourceTypeLabel("TABLE") === null, "unknown evidence types are not invented");
assert(sourceTypeLabel("TEXT_SPAN") === "Đoạn nguồn", "only backend source types are labelled");

const copied = copyCitationText(groups.v2[0], "Phiên bản 2");
assert(copied.includes("Phiên bản 2"), "copy includes version context");
assert(!copied.includes("ev-v2"), "copy does not expose internal evidence ids");
assert(!copied.includes("doc-b"), "copy does not expose document ids");

const flow = {
  summary: findingContext(verifiedModified),
  clauseView: verifiedModified.clause_id,
  panel: flattenEvidenceItems(verifiedModified).map((row) => row.side),
  viewer: buildEvidenceSourceHref("ws1", verifiedModified.evidence[1]),
};
assert(flow.summary.includes("480,000,000"), "integration: summary finding");
assert(flow.clauseView === "CLAUSE:8.2", "integration: clause view association");
assert(flow.panel.join(",") === "v1,v2,v2", "integration: evidence panel grouping");
assert(flow.viewer.includes("page=15") && flow.viewer.includes("doc-b"), "integration: document viewer target");

const a11y = {
  dialog: "role=dialog aria-modal",
  badges: "text+icon",
  keyboard: ["Escape closes panel only", "citation chips are buttons"],
  contrast: "tokens",
};
assert(a11y.dialog.includes("dialog"), "drawer uses dialog semantics");
assert(a11y.keyboard.length === 2, "keyboard interactions are defined");

const regression = [verifiedModified, unverified, partial, missing, added, removed, unchanged];
assert(regression.some((c) => c.status === "MODIFIED" && c.risk?.risk_level === "CRITICAL"), "regression includes critical modified");
assert(regression.some((c) => c.status === "ADDED"), "regression includes added");
assert(regression.some((c) => c.status === "REMOVED"), "regression includes removed");
assert(regression.some((c) => c.status === "UNCHANGED"), "regression includes unchanged");
assert(regression.some((c) => evidenceState(c) === "verified"), "regression includes verified");
assert(regression.some((c) => evidenceState(c) === "unverified"), "regression includes unverified");
assert(regression.some((c) => evidenceState(c) === "unavailable"), "regression includes missing evidence");

if (process.exitCode) {
  console.error("test-comparison-evidence-ui failed");
  process.exit(process.exitCode);
} else {
  console.log("test-comparison-evidence-ui passed");
}
