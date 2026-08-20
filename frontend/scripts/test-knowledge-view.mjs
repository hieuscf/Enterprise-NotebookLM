/**
 * Node smoke tests for Knowledge View presentation helpers.
 * Run: node scripts/test-knowledge-view.mjs
 *
 * Mirrors frontend/features/documents/viewer/knowledge/document-structure.ts
 * — presentation only; Canonical content is never rewritten.
 */

const HEADING_MARKER_RE = /^(#{1,6})[ \t]+/;
const HR_RE = /^(?:-{3,}|\*{3,}|_{3,})\s*$/;
const TABLE_DELIM_RE = /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/;
const NUMERIC_CELL_RE = /^[+-]?(?:\d{1,3}(?:[.,]\d{3})*|\d+)(?:[.,]\d+)?%?$/;
const LIST_ITEM_RE = /^(\s*)(?:[-*+]|\d+[.)])\s+/;
const ORDERED_ITEM_RE = /^\s*\d+[.)]\s+/;

function headingMarkerPrefix(content) {
  const match = (content ?? "").match(HEADING_MARKER_RE);
  return match ? match[0] : "";
}

function displayHeadingText(content) {
  return (content ?? "").replace(HEADING_MARKER_RE, "").replace(/\s+#+\s*$/, "").trim();
}

function mapContentOffsetsToDisplay(content, displayText, start, end) {
  if (end <= start) return { start: 0, end: 0 };
  if (displayText === content) {
    return clampRange(displayText.length, start, end);
  }
  const cited = content.slice(Math.max(0, start), Math.max(0, end));
  if (cited) {
    const exact = displayText.indexOf(cited);
    if (exact >= 0) return { start: exact, end: exact + cited.length };
    const stripped = cited.replace(HEADING_MARKER_RE, "").replace(/^>\s?/gm, "");
    if (stripped && stripped !== cited) {
      const idx = displayText.indexOf(stripped);
      if (idx >= 0) return { start: idx, end: idx + stripped.length };
    }
  }
  const prefixLen = Math.max(0, content.length - displayText.length);
  if (content.endsWith(displayText) && prefixLen > 0) {
    return clampRange(displayText.length, start - prefixLen, end - prefixLen);
  }
  return clampRange(displayText.length, start, end);
}

function clampRange(len, start, end) {
  const s = Math.max(0, Math.min(start, len));
  const e = Math.max(s, Math.min(end, len));
  return { start: s, end: e };
}

function splitDocumentHeader(blocks, documentTitle) {
  const empty = {
    header: [],
    body: blocks,
    titleBlockId: findTitleBlockId(blocks, documentTitle),
    subtitleBlockId: null,
  };
  if (blocks.length < 2) return empty;
  const header = [];
  for (const block of blocks) {
    if (block.block_type !== "heading") break;
    const level = block.heading_level ?? 1;
    const text = displayHeadingText(block.content);
    if (level !== 1) break;
    if (text.length > 96) break;
    header.push(block);
    if (header.length >= 8) break;
  }
  if (header.length < 2) return empty;
  const next = blocks[header.length];
  if (
    next &&
    next.block_type === "heading" &&
    (next.heading_level ?? 2) >= 2 &&
    displayHeadingText(next.content).length <= 96
  ) {
    header.push(next);
  }
  const lastH1 =
    header.filter((b) => (b.heading_level ?? 1) === 1).at(-1) ??
    header[header.length - 1];
  const lastH1Index = header.findIndex((b) => b.id === lastH1.id);
  const maybeSubtitle = header[lastH1Index + 1];
  const subtitleBlockId =
    maybeSubtitle && (maybeSubtitle.heading_level ?? 2) >= 2 ? maybeSubtitle.id : null;
  return {
    header,
    body: blocks.slice(header.length),
    titleBlockId: lastH1.id,
    subtitleBlockId,
  };
}

function findTitleBlockId(blocks, documentTitle) {
  const needle = (documentTitle ?? "").replace(/\s+/g, " ").trim().toLowerCase();
  if (needle) {
    const match = blocks.find(
      (b) =>
        b.block_type === "heading" &&
        displayHeadingText(b.content).replace(/\s+/g, " ").trim().toLowerCase() === needle,
    );
    if (match) return match.id;
  }
  return blocks.find((b) => b.block_type === "heading")?.id ?? null;
}

function splitTableRow(line) {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

function parseMarkdownTable(content) {
  const lines = (content ?? "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  if (lines.length < 2 || !lines[0].includes("|") || !TABLE_DELIM_RE.test(lines[1])) {
    return null;
  }
  const headers = splitTableRow(lines[0]);
  const alignments = splitTableRow(lines[1]).map((cell) => {
    const t = cell.trim();
    const left = t.startsWith(":");
    const right = t.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    return "left";
  });
  const rows = lines.slice(2).map(splitTableRow);
  const width = headers.length;
  const paddedAlign = Array.from({ length: width }, (_, i) => alignments[i] ?? "left");
  for (let col = 0; col < width; col += 1) {
    if (paddedAlign[col] !== "left") continue;
    const values = rows.map((r) => r[col] ?? "").filter((c) => c.length > 0);
    if (values.length > 0 && values.every((c) => NUMERIC_CELL_RE.test(c))) {
      paddedAlign[col] = "right";
    }
  }
  return {
    headers,
    alignments: paddedAlign,
    rows: rows.map((r) => {
      const next = r.slice(0, width);
      while (next.length < width) next.push("");
      return next;
    }),
  };
}

function parseListModel(content) {
  const items = [];
  let ordered = false;
  for (const line of (content ?? "").split(/\r?\n/)) {
    if (!line.trim()) continue;
    if (ORDERED_ITEM_RE.test(line)) ordered = true;
    items.push(line.replace(LIST_ITEM_RE, "").trimEnd());
  }
  return { ordered, items: items.length ? items : [(content ?? "").trim()] };
}

function isSafeHref(url) {
  const t = (url ?? "").trim().toLowerCase();
  if (!t) return false;
  if (t.startsWith("javascript:") || t.startsWith("vbscript:") || t.startsWith("data:")) {
    return false;
  }
  return t.startsWith("https:") || t.startsWith("http:") || t.startsWith("mailto:") || t.startsWith("/");
}

function isRawMarkdownBlob(blocks) {
  if (blocks.length !== 1) return false;
  const block = blocks[0];
  if (block.block_type !== "paragraph") return false;
  const c = block.content ?? "";
  return HEADING_MARKER_RE.test(c) && /\n#{1,6}\s+/m.test(c);
}

let passed = 0;
function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
    return;
  }
  passed += 1;
  console.log("ok -", msg);
}

assert(displayHeadingText("# CÔNG BỐ THÔNG TIN") === "CÔNG BỐ THÔNG TIN", "strip ATX H1 marker");
assert(displayHeadingText("## PERIODIC DISCLOSURE") === "PERIODIC DISCLOSURE", "strip ATX H2 marker");
assert(displayHeadingText("CÔNG BỐ THÔNG TIN") === "CÔNG BỐ THÔNG TIN", "plain heading unchanged");
assert(headingMarkerPrefix("# Title") === "# ", "prefix captured for offset map");

const mapped = mapContentOffsetsToDisplay(
  "# TITLE",
  "TITLE",
  2,
  7,
);
assert(mapped.start === 0 && mapped.end === 5, "citation offsets map after stripping #");

const alreadyStripped = mapContentOffsetsToDisplay("TITLE", "TITLE", 0, 5);
assert(alreadyStripped.start === 0 && alreadyStripped.end === 5, "hash-free offsets pass through");

const snippetMap = mapContentOffsetsToDisplay(
  "# CÔNG BỐ THÔNG TIN ĐỊNH KỲ",
  "CÔNG BỐ THÔNG TIN ĐỊNH KỲ",
  2,
  27,
);
assert(
  snippetMap.start === 0 &&
    "CÔNG BỐ THÔNG TIN ĐỊNH KỲ".slice(snippetMap.start, snippetMap.end).startsWith("CÔNG BỐ"),
  "sub-span maps into visible heading text",
);

const lone = splitDocumentHeader([
  { id: "b0000", block_type: "heading", heading_level: 1, content: "Only title" },
  { id: "b0001", block_type: "paragraph", content: "Body" },
]);
assert(lone.header.length === 0, "single leading H1 is not a letterhead");
assert(lone.titleBlockId === "b0000", "lone first heading can still be the document title");

const report = splitDocumentHeader([
  { id: "b0000", block_type: "heading", heading_level: 1, content: "Báo cáo tài chính" },
  { id: "b0001", block_type: "heading", heading_level: 2, content: "Tổng quan" },
  { id: "b0002", block_type: "paragraph", content: "Nội dung" },
]);
assert(report.header.length === 0, "H1 then H2 is not treated as a letterhead");

const letterhead = splitDocumentHeader([
  { id: "b0000", block_type: "heading", heading_level: 1, content: "COMPANY NAME" },
  { id: "b0001", block_type: "heading", heading_level: 1, content: "REPUBLIC NAME" },
  { id: "b0002", block_type: "heading", heading_level: 1, content: "DISCLOSURE TITLE" },
  { id: "b0003", block_type: "heading", heading_level: 2, content: "English subtitle" },
  { id: "b0004", block_type: "paragraph", content: "Số / No.: 01" },
]);
assert(letterhead.header.length === 4, "leading consecutive headings form a header");
assert(letterhead.body[0].id === "b0004", "first non-heading starts the body");
assert(letterhead.titleBlockId === "b0002", "last H1 in header is the title, not every H1");
assert(
  !JSON.stringify(letterhead).toLowerCase().includes("coteccons"),
  "no company-specific header heuristic",
);

const table = parseMarkdownTable(
  "| Năm | Doanh thu | Tăng trưởng |\n| --- | ---: | ---: |\n| 2024 | 1,200 | 12% |",
);
assert(table && table.headers[0] === "Năm", "table headers parsed");
assert(table && table.rows[0][1] === "1,200", "table cells are not flattened");
assert(table && table.alignments[1] === "right", "numeric/explicit right alignment");
assert(table && !table.headers.join("").includes("|"), "pipes are not part of cell text");

const ul = parseListModel("- item 1\n- item 2\n- item 3");
assert(ul.ordered === false && ul.items[0] === "item 1", "unordered list strips bullets");
const ol = parseListModel("1. first\n2. second");
assert(ol.ordered === true && ol.items[1] === "second", "ordered list keeps sequence without markers");

assert(isSafeHref("javascript:alert(1)") === false, "javascript: URLs rejected");
assert(isSafeHref("https://example.com/doc.pdf") === true, "https URLs allowed");
assert(isSafeHref("data:text/html,<script>") === false, "data: HTML rejected");

assert(
  isRawMarkdownBlob([
    {
      id: "b0000",
      block_type: "paragraph",
      content: "# Title\n\n## Section\n\nBody",
    },
  ]) === true,
  "single paragraph of raw markdown is detected",
);
assert(
  isRawMarkdownBlob([
    { id: "b0000", block_type: "heading", heading_level: 1, content: "Title" },
    { id: "b0001", block_type: "paragraph", content: "Body" },
  ]) === false,
  "structured blocks are not treated as a markdown blob",
);

assert(HR_RE.test("---") === true, "horizontal rule detected");
assert(
  displayHeadingText("# CÔNG BỐ") === "CÔNG BỐ" &&
    displayHeadingText("# CÔNG BỐ").includes("#") === false,
  "copied heading text has no markdown marker",
);

// --- Citation snippet → block (mirrors citation-highlight.ts) ----------
function normalizeForMatch(value) {
  return (value || "")
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function matchSnippetInBlockContent(content, snippet) {
  const needle = (snippet || "").trim();
  if (!content || !needle) return null;
  const exact = content.indexOf(needle);
  if (exact >= 0) return { start: exact, end: exact + needle.length };
  const ci = content.toLowerCase().indexOf(needle.toLowerCase());
  if (ci >= 0) return { start: ci, end: ci + needle.length };
  const normContent = normalizeForMatch(content);
  const normNeedle = normalizeForMatch(needle);
  if (!normNeedle || normNeedle.length < 8) return null;
  const nidx = normContent.indexOf(normNeedle);
  if (nidx < 0) return null;
  const ratio = content.length / Math.max(1, normContent.length);
  const start = Math.max(0, Math.min(content.length - 1, Math.floor(nidx * ratio)));
  const end = Math.max(
    start + 1,
    Math.min(content.length, Math.floor((nidx + normNeedle.length) * ratio)),
  );
  return { start, end };
}

function findBlockForSnippet(blocks, snippet) {
  const needle = (snippet || "").trim();
  if (!needle || blocks.length === 0) return null;
  let best = null;
  let bestScore = 0;
  for (const block of blocks) {
    const hit = matchSnippetInBlockContent(block.content || "", needle);
    if (!hit) continue;
    const score = hit.end - hit.start;
    if (score > bestScore) {
      bestScore = score;
      best = block;
    }
  }
  return best;
}

const citeBlocks = [
  { id: "b0001", content: "Doanh thu thuần năm 2024 đạt 1.200 tỷ đồng." },
  { id: "b0002", content: "Chi phí quản lý doanh nghiệp tăng nhẹ." },
];
assert(
  findBlockForSnippet(citeBlocks, "doanh thu thuần năm 2024 đạt 1.200 tỷ")?.id ===
    "b0001",
  "normalized snippet finds citation block",
);
assert(
  findBlockForSnippet(citeBlocks, "không tồn tại trong tài liệu") === null,
  "unknown snippet does not invent a block",
);

if (process.exitCode) {
  process.exit(process.exitCode);
}
console.log(`\n${passed} knowledge-view assertions passed`);
