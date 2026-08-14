/**
 * Node smoke tests for section_extraction presentation helpers.
 * Run: node scripts/test-section-extraction-ui.mjs
 *
 * Transpiles features/chat/section-extraction/section-extraction-adapter.ts
 * (presentation only — does not touch retrieval / LLM routing).
 */

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const adapterPath = path.join(
  __dirname,
  "../features/chat/section-extraction/section-extraction-adapter.ts",
);
const source = fs.readFileSync(adapterPath, "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true,
  },
  fileName: "section-extraction-adapter.ts",
});

const module = { exports: {} };
const load = new Function("exports", "module", "require", outputText);
load(module.exports, module, require);

const {
  buildSectionExtractionModel,
  parseHtmlTableFragment,
  formatSectionHeading,
  compareSectionNumbers,
  unescapeHtmlEntities,
  stripHeadingFromBody,
  dedupeParagraphs,
  isDocumentSectionNumber,
  isHeaderFooterArtifact,
  peelHeadingPrefix,
} = module.exports;

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exitCode = 1;
  } else {
    console.log("OK:", msg);
  }
}

function flatten(nodes, acc = []) {
  for (const node of nodes) {
    acc.push(node);
    if (node.children?.length) flatten(node.children, acc);
  }
  return acc;
}

function numbersOf(model) {
  return flatten(model.nodes).map((n) => n.number);
}

const LEGACY_DOUBLE_NUMBERING = `4. SỰ KIỆN QUAN TRỌNG TRONG KỲ gồm:

5. 4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing")
6. 4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing")
7. 4.2 Mua Công ty "Coteccons KZ" LLP ("CTD KZ LLP")
8. 4.2 Mua Công ty "Coteccons KZ" LLP ("CTD KZ LLP")
9. 4.3 Mua Công ty TNHH GEO Foundation Việt Nam ("GEO")`;

const modelFromLegacy = buildSectionExtractionModel({ content: LEGACY_DOUBLE_NUMBERING });
const legacyNumbers = numbersOf(modelFromLegacy);
assert(legacyNumbers[0] === "4", "Root section number stays 4 (not a list index)");
assert(
  legacyNumbers.filter((n) => n === "4.1").length === 1,
  "4.1 heading appears once after grouping",
);
assert(
  legacyNumbers.filter((n) => n === "4.2").length === 1,
  "4.2 heading appears once after grouping",
);
assert(
  legacyNumbers.filter((n) => n === "4.3").length === 1,
  "4.3 heading appears once after grouping",
);
assert(
  !legacyNumbers.includes("5") && !legacyNumbers.includes("6") && !legacyNumbers.includes("7"),
  "Markdown list indexes 5/6/7 are discarded",
);
assert(
  JSON.stringify(legacyNumbers) === JSON.stringify(["4", "4.1", "4.2", "4.3"]),
  "Outline order is 4 → 4.1 → 4.2 → 4.3",
);

const titles = flatten(modelFromLegacy.nodes).map((n) => n.title);
assert(
  titles.every((t) => !/^\d+\.\s+\d+\./.test(t)),
  "Titles do not keep double numbering like '5. 4.1 ...'",
);
assert(
  formatSectionHeading("4.1", 'Thành lập Công ty con') === "4.1 Thành lập Công ty con",
  "Dotted section numbers are not given an extra period",
);
assert(
  formatSectionHeading("4", "SỰ KIỆN QUAN TRỌNG TRONG KỲ") === "4. SỰ KIỆN QUAN TRỌNG TRONG KỲ",
  "Top-level heading keeps '4. Title' form",
);

const headingEcho = buildSectionExtractionModel({
  content: `4.2 Mua Công ty "Coteccons KZ" LLP

4.2 Mua Công ty "Coteccons KZ" LLP
Lĩnh vực kinh doanh chính của CTD KZ LLP là cung cấp dịch vụ xây dựng.`,
});
const kz = flatten(headingEcho.nodes).find((n) => n.number === "4.2");
assert(Boolean(kz), "Parses 4.2 as a section heading");
assert(
  kz.children.length === 0 && flatten([kz]).filter((n) => n.number === "4.2").length === 1,
  "Repeated 4.2 heading is not a second section",
);
const kzText = (kz.blocks || [])
  .filter((b) => b.kind === "paragraph")
  .map((b) => b.text)
  .join("\n");
assert(
  (kzText.match(/Mua Công ty "Coteccons KZ"/g) || []).length === 0,
  "Heading text is stripped from the body",
);
assert(
  kzText.includes("Lĩnh vực kinh doanh chính"),
  "Body paragraph is kept after heading strip",
);

const dupParas = dedupeParagraphs([
  "Lĩnh vực kinh doanh chính của CTD KZ LLP là cung cấp dịch vụ xây dựng.",
  "Lĩnh vực kinh doanh chính của CTD KZ LLP là cung cấp dịch vụ xây dựng.",
  "Giá trị hợp lý tạm tính ghi nhận tại ngày mua.",
]);
assert(dupParas.length === 2, "Near-identical paragraphs collapse to one");
assert(
  dupParas[1].includes("Giá trị hợp lý"),
  "Distinct paragraphs in the same section are kept",
);

const stripped = stripHeadingFromBody("4.1", "Thành lập Công ty con", [
  "4.1 Thành lập Công ty con",
  "Hoàn tất thủ tục đăng ký ngày 30/06/2026.",
]);
assert(stripped.length === 1 && stripped[0].includes("Hoàn tất"), "stripHeadingFromBody drops the heading line");

const htmlTable = parseHtmlTableFragment(
  "<tr><th></th><th>VND</th></tr><tr><th></th><th>Giá trị hợp lý tạm tính ghi nhận tại ngày mua</th></tr><tr><td>Tài sản</td><td></td></tr>",
);
assert(Boolean(htmlTable), "HTML <tr>/<th>/<td> fragment becomes a table");
assert(htmlTable.headers[1] === "VND", "First header row is table headers");
assert(
  htmlTable.rows.some((r) => r[0] === "Tài sản"),
  "Body row 'Tài sản' is a table row, not raw HTML",
);
assert(
  htmlTable.rows.some((r) => r[1] === "Giá trị hợp lý tạm tính ghi nhận tại ngày mua"),
  "Second header-like row is kept as data",
);

const escaped = unescapeHtmlEntities("&lt;tr&gt;&lt;td&gt;Tài sản&lt;/td&gt;&lt;/tr&gt;");
assert(escaped.includes("<tr>") && escaped.includes("Tài sản"), "Unescapes &lt;tr&gt; to real tags");

const tableAnswer = buildSectionExtractionModel({
  content: `4.3 Mua Công ty TNHH GEO Foundation Việt Nam ("GEO")

Vào ngày 25 tháng 5 năm 2026, Tập đoàn đã mua 100% vốn góp.
<tr><th></th><th>VND</th></tr>
<tr><td>Tài sản</td><td>12</td></tr>`,
});
const geo = flatten(tableAnswer.nodes).find((n) => n.number === "4.3");
const tableBlock = geo.blocks.find((b) => b.kind === "table");
const paraText = geo.blocks
  .filter((b) => b.kind === "paragraph")
  .map((b) => b.text)
  .join(" ");
assert(Boolean(tableBlock), "HTML table in body becomes StructuredTable data");
assert(!paraText.includes("<tr>") && !paraText.includes("<td>"), "Raw <tr>/<td> is not left in paragraphs");
assert(paraText.includes("25 tháng 5 năm 2026"), "Narrative paragraph around the table is kept");

const deep = buildSectionExtractionModel({
  content: `2. RỦI RO

2.1 Thị trường
2.1.1 Tỷ giá
Chi tiết tỷ giá.
2.1.2 Lãi suất
2.2 Pháp lý`,
});
assert(
  JSON.stringify(numbersOf(deep)) === JSON.stringify(["2", "2.1", "2.1.1", "2.1.2", "2.2"]),
  "Arbitrary depth 2 → 2.1 → 2.1.1/2.1.2 and sibling 2.2",
);
assert(deep.nodes[0].children[0].children[0].number === "2.1.1", "2.1.1 nests under 2.1, not under 2");
assert(deep.nodes[0].children[1].number === "2.2", "2.2 is a sibling of 2.1");

const scored = buildSectionExtractionModel({
  items: [
    {
      documentId: "doc-1",
      chunkId: "c-43",
      sectionNumber: "4.3",
      sectionTitle: "GEO",
      chunkIndex: 30,
      content: "GEO body",
    },
    {
      documentId: "doc-1",
      chunkId: "c-41a",
      sectionNumber: "4.1",
      sectionTitle: "CTD Sing",
      chunkIndex: 10,
      content: "Sing A",
    },
    {
      documentId: "doc-1",
      chunkId: "c-41b",
      sectionNumber: "4.1",
      sectionTitle: "CTD Sing",
      chunkIndex: 11,
      content: "Sing B",
    },
    {
      documentId: "doc-1",
      chunkId: "c-42",
      sectionNumber: "4.2",
      sectionTitle: "CTD KZ",
      chunkIndex: 20,
      content: "KZ body",
    },
  ],
});
const scoredNums = numbersOf(scored);
assert(
  JSON.stringify(scoredNums) === JSON.stringify(["4.1", "4.2", "4.3"]),
  "chunk_index / section number beat insertion order (4.3 was listed first)",
);
const s41 = flatten(scored.nodes).find((n) => n.number === "4.1");
const s41text = s41.blocks
  .filter((b) => b.kind === "paragraph")
  .map((b) => b.text)
  .join(" ");
assert(s41text.includes("Sing A") && s41text.includes("Sing B"), "Duplicate 4.1 chunks merge body by chunk_index");
assert(s41.chunkIds.includes("c-41a") && s41.chunkIds.includes("c-41b"), "Merged section keeps both chunk ids");

assert(compareSectionNumbers("4.1", "4.2") < 0, "4.1 sorts before 4.2");
assert(compareSectionNumbers("4", "4.1") < 0, "Parent 4 sorts before 4.1");
assert(compareSectionNumbers("2.1.2", "2.2") < 0, "2.1.2 sorts before 2.2");

const cited = buildSectionExtractionModel({
  content: `4.1 Thành lập Công ty con\nHoàn tất thủ tục.`,
  citations: [
    {
      id: "cit-1",
      documentId: "doc-1",
      chunkId: "chunk-41",
      page: 1,
      textSnippet: "Thành lập Công ty con",
      sectionTitle: "Thành lập Công ty con",
      displayIndex: 1,
      verified: true,
    },
    {
      id: "cit-2",
      documentId: "doc-1",
      chunkId: "chunk-41b",
      page: 1,
      textSnippet: "Hoàn tất thủ tục",
      displayIndex: 2,
      verified: true,
    },
  ],
});
function bodyText(node) {
  if (!node) return "";
  return (node.blocks || [])
    .filter((b) => b.kind === "paragraph" || b.kind === "bullets")
    .map((b) => (b.kind === "paragraph" ? b.text : b.items.join(" ")))
    .join("\n");
}

const citedNode = flatten(cited.nodes).find((n) => n.number === "4.1");
assert(citedNode.citations.length === 1, "Same document+page citations collapse to one badge");
assert(citedNode.citations[0].chunkId === "chunk-41", "Grouped citation still points at a chunk_id");
assert(citedNode.citations[0].page === 1, "Page locator is preserved for document open");

assert(isDocumentSectionNumber("4.1") === true, "4.1 is a document section number");
assert(isDocumentSectionNumber("2.1.1") === true, "2.1.1 is a document section number");
assert(isDocumentSectionNumber("30.06.2026") === false, "Dates are not section numbers");
assert(isDocumentSectionNumber("100.000") === false, "Thousands are not section numbers");

const peeled = peelHeadingPrefix(
  '4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing") Hoàn tất thủ tục đăng ký ngày 30/06/2026.',
  "4.1",
  'Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing")',
);
assert(
  peeled && peeled.includes("Hoàn tất thủ tục"),
  "Duplicate heading line keeps the trailing body instead of dropping the whole line",
);
assert(
  peelHeadingPrefix(
    '4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing")',
    "4.1",
    'Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing")',
  ) === null,
  "Exact heading echo is removed from body",
);

assert(
  isHeaderFooterArtifact("**Công ty Cổ phần Xây dựng Coteccons**") === true,
  "Bold company running-header is an artifact",
);
assert(
  isHeaderFooterArtifact("Hoàn tất thủ tục đăng ký ngày 30/06/2026.") === false,
  "Narrative body is not an artifact",
);

const PRODUCTION_LIKE = `4. SỰ KIỆN QUAN TRỌNG TRONG KỲ

4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing")
4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing") Hoàn tất thủ tục đăng ký ngày 30/06/2026. Mục đích: thực hiện các hoạt động liên quan đến đầu tư và xây dựng.
30.06.2026 Tập đoàn đã hoàn tất thủ tục đăng ký thành lập công ty con.
**Công ty Cổ phần Xây dựng Coteccons**

4.2 Mua Công ty "Coteccons KZ" LLP ("CTD KZ LLP")
chunk A field
4.2 Mua Công ty "Coteccons KZ" LLP ("CTD KZ LLP")
Lĩnh vực kinh doanh chính của CTD KZ LLP là cung cấp dịch vụ xây dựng.

4.3 Mua Công ty TNHH GEO Foundation Việt Nam ("GEO")
Vào ngày 25 tháng 5 năm 2026, Tập đoàn đã mua 100% vốn góp.
<tr><th></th><th>VND</th></tr>
<tr><td>Tài sản</td><td>12</td></tr>
4.3 Mua Công ty TNHH GEO Foundation Việt Nam ("GEO")
**Công ty Cổ phần Xây dựng Coteccons**`;

const prod = buildSectionExtractionModel({ content: PRODUCTION_LIKE });
const prodNums = numbersOf(prod);
assert(
  JSON.stringify(prodNums) === JSON.stringify(["4", "4.1", "4.2", "4.3"]),
  "section order remains 4.1 → 4.2 → 4.3 under parent 4",
);
assert(!prodNums.includes("30.06.2026"), "Date lines are not promoted to headings");
assert(!prodNums.some((n) => n === "1" || n === "2" || n === "3"), "No 1./2./3. list indexes before section numbers");

const n41 = flatten(prod.nodes).find((n) => n.number === "4.1");
const n42 = flatten(prod.nodes).find((n) => n.number === "4.2");
const n43 = flatten(prod.nodes).find((n) => n.number === "4.3");
const t41 = bodyText(n41);
const t42 = bodyText(n42);
const t43 = bodyText(n43);

assert(Boolean(n41 && n42 && n43), "All three child sections exist");
assert(t41.includes("Hoàn tất thủ tục"), "4.1 with body must render body (not heading-only)");
assert(t41.includes("30.06.2026") || t41.includes("Tập đoàn đã hoàn tất"), "4.1 keeps date-led narrative as body");
assert(!t41.includes("**"), "4.1 body has no raw markdown emphasis artifacts");
assert(!t41.includes("Công ty Cổ phần Xây dựng Coteccons"), "header/footer artifact is not in 4.1 body");

assert(flatten(prod.nodes).filter((n) => n.number === "4.2").length === 1, "4.2 many chunks render one heading");
assert(t42.includes("Lĩnh vực kinh doanh chính") && t42.includes("chunk A"), "4.2 merges all chunk bodies");
assert(!n42.title.includes("\n"), "4.2 heading title is a single line");
assert(formatSectionHeading(n42.number, n42.title) === `4.2 ${n42.title}`, "4.2 heading uses the same number+title formatter");

assert(flatten(prod.nodes).filter((n) => n.number === "4.3").length === 1, "4.3 many chunks render one heading");
assert(t43.includes("Vào ngày 25 tháng 5"), "4.3 keeps narrative body");
assert(formatSectionHeading(n43.number, n43.title) === `4.3 ${n43.title}`, "4.3 heading uses the same number+title formatter");
assert(formatSectionHeading(n41.number, n41.title).startsWith("4.1 "), "heading formatting is consistent across subsections");
assert(!n41.title.startsWith("4.1"), "title field does not repeat the section number");
assert(!n42.title.startsWith("4.2"), "4.2 title field does not repeat the section number");
assert(!n43.title.startsWith("4.3"), "4.3 title field does not repeat the section number");

const table43 = (n43.blocks || []).find((b) => b.kind === "table");
assert(Boolean(table43), "4.3 HTML table is classified as StructuredTable");
assert(!t43.includes("<tr>") && !t43.includes("<td>"), "table HTML does not appear as raw text");
assert(!t43.includes("Công ty Cổ phần Xây dựng Coteccons"), "header/footer artifact is not in 4.3 body");

const structuredMerge = buildSectionExtractionModel({
  items: [
    {
      documentId: "doc-1",
      chunkId: "h-41",
      sectionNumber: "4.1",
      sectionTitle: 'Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing")',
      chunkIndex: 10,
      content: '4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing")',
    },
    {
      documentId: "doc-1",
      chunkId: "b-41",
      sectionNumber: "4.1",
      sectionTitle: 'Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing")',
      chunkIndex: 11,
      content:
        '4.1 Thành lập Công ty con Coteccons Construction Singapore Pte. Ltd. ("CTD Sing") Hoàn tất thủ tục đăng ký ngày 30/06/2026.',
    },
  ],
});
const merged41 = flatten(structuredMerge.nodes).find((n) => n.number === "4.1");
assert(flatten(structuredMerge.nodes).filter((n) => n.number === "4.1").length === 1, "structured 4.1 chunks group to one heading");
assert(bodyText(merged41).includes("Hoàn tất thủ tục"), "structured 4.1 merge keeps body from later chunk_index");

if (process.exitCode) {
  console.error("\nsection-extraction UI tests failed");
} else {
  console.log("\nsection-extraction UI tests passed");
}
