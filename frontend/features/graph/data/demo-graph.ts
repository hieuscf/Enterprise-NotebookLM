/**
 * =============================================================================
 * File: demo-graph.ts
 * Module/Service: Knowledge Graph (Web App)
 * Layer: Adapter
 * Purpose: Workspace-scoped demo Knowledge Graph until the read API exists.
 * Responsibilities:
 *   - Provide a hierarchical, multi-connected enterprise sample graph
 *   - Stamp every payload with the active workspace_id
 * Dependencies:
 *   - types/knowledge-graph
 * Public Exports:
 *   - buildDemoKnowledgeGraph
 * Database/Table: N/A (demo only)
 * Related Modules: features/graph/graph.api.ts
 * Important Notes: Replace with OpenAPI-backed fetch when graph-read lands.
 * =============================================================================
 */

import type {
  KnowledgeGraphEdge,
  KnowledgeGraphNode,
  KnowledgeGraphPayload,
} from "@/types/knowledge-graph";

const DEMO_NODES: KnowledgeGraphNode[] = [
  {
    id: "t-enterprise",
    type: "topic",
    label: "Enterprise Strategy",
    description:
      "Top-level strategic themes spanning product, market, and risk across the workspace corpus.",
    confidence: 0.96,
    subtype: "Root topic",
    connection_count: 4,
  },
  {
    id: "t-product",
    type: "topic",
    label: "Product Strategy",
    description:
      "Roadmap priorities, product lines, and go-to-market sequencing for core offerings.",
    confidence: 0.94,
    subtype: "Topic",
    connection_count: 5,
  },
  {
    id: "t-market",
    type: "topic",
    label: "Market Analysis",
    description:
      "Regional demand signals, competitive positioning, and customer segment insights.",
    confidence: 0.92,
    subtype: "Topic",
    connection_count: 5,
  },
  {
    id: "t-finance",
    type: "topic",
    label: "Financial Planning",
    description:
      "Revenue planning, margin targets, and capital allocation themes.",
    confidence: 0.9,
    subtype: "Topic",
    connection_count: 4,
  },
  {
    id: "t-risk",
    type: "topic",
    label: "Risk Management",
    description:
      "Operational, compliance, and market risk themes extracted from board materials.",
    confidence: 0.88,
    subtype: "Topic",
    connection_count: 3,
  },
  {
    id: "e-product-a",
    type: "entity",
    label: "Product A",
    description:
      "Flagship enterprise analytics platform targeting mid-market and regulated industries.",
    confidence: 0.95,
    subtype: "Product",
    connection_count: 8,
    citations: [
      {
        document_id: "doc-annual",
        document_title: "Annual Report 2025",
        page_number: 42,
        snippet: "Product A contributed 38% of recurring revenue in FY2025.",
      },
      {
        document_id: "doc-strategy",
        document_title: "Product Strategy.pdf",
        page_number: 18,
        snippet: "Product A remains the primary growth engine for FY26.",
      },
    ],
  },
  {
    id: "e-product-b",
    type: "entity",
    label: "Product B",
    description:
      "Complementary workflow suite positioned for expansion accounts.",
    confidence: 0.91,
    subtype: "Product",
    connection_count: 5,
    citations: [
      {
        document_id: "doc-strategy",
        document_title: "Product Strategy.pdf",
        page_number: 24,
        snippet: "Product B attaches to Product A deployments in 62% of deals.",
      },
    ],
  },
  {
    id: "e-customer-x",
    type: "entity",
    label: "Customer X",
    description: "Strategic enterprise account in the Vietnam Market segment.",
    confidence: 0.89,
    subtype: "Organization",
    connection_count: 4,
  },
  {
    id: "e-customer-y",
    type: "entity",
    label: "Customer Y",
    description: "Regional manufacturing conglomerate evaluating Product B.",
    confidence: 0.86,
    subtype: "Organization",
    connection_count: 3,
  },
  {
    id: "e-vietnam",
    type: "entity",
    label: "Vietnam Market",
    description:
      "Priority growth geography for FY26, with focus on regulated industries.",
    confidence: 0.93,
    subtype: "Market",
    connection_count: 6,
    citations: [
      {
        document_id: "doc-market",
        document_title: "Market Research.docx",
        page_number: 7,
        snippet: "Vietnam Market demand for analytics platforms grew 24% YoY.",
      },
    ],
  },
  {
    id: "e-q4",
    type: "entity",
    label: "Q4 Revenue",
    description: "Fourth-quarter recurring revenue outcome and drivers.",
    confidence: 0.92,
    subtype: "Metric",
    connection_count: 4,
    citations: [
      {
        document_id: "doc-annual",
        document_title: "Annual Report 2025",
        page_number: 12,
        snippet: "Q4 Revenue exceeded plan by 6.4% on Product A expansion.",
      },
    ],
  },
  {
    id: "e-alpha",
    type: "entity",
    label: "Project Alpha",
    description:
      "Cross-functional initiative to localize Product A for Vietnam Market.",
    confidence: 0.9,
    subtype: "Project",
    connection_count: 5,
  },
  {
    id: "e-smith",
    type: "entity",
    label: "John Smith",
    description: "Program lead for Project Alpha and Product A GTM.",
    confidence: 0.87,
    subtype: "Person",
    connection_count: 3,
  },
  {
    id: "e-apple",
    type: "entity",
    label: "Acme Holdings",
    description: "Parent enterprise referenced in partnership materials.",
    confidence: 0.84,
    subtype: "Organization",
    connection_count: 2,
  },
  {
    id: "c-gtm",
    type: "concept",
    label: "Go-to-Market",
    description: "Keyword cluster around launch sequencing and channel mix.",
    confidence: 0.82,
    subtype: "Concept",
    connection_count: 3,
  },
  {
    id: "c-compliance",
    type: "concept",
    label: "Regulatory Compliance",
    description: "Recurring concept across risk and Vietnam Market materials.",
    confidence: 0.85,
    subtype: "Concept",
    connection_count: 3,
  },
  {
    id: "c-margin",
    type: "concept",
    label: "Gross Margin",
    description: "Financial concept linking Product A and Q4 Revenue.",
    confidence: 0.83,
    subtype: "Concept",
    connection_count: 2,
  },
  {
    id: "d-annual",
    type: "document",
    label: "Annual Report 2025",
    description: "Primary financial and strategic source for FY2025.",
    confidence: 1,
    subtype: "PDF",
    connection_count: 5,
    citations: [
      {
        document_id: "doc-annual",
        document_title: "Annual Report 2025",
        page_number: 1,
      },
    ],
    metadata: { document_id: "doc-annual" },
  },
  {
    id: "d-strategy",
    type: "document",
    label: "Product Strategy.pdf",
    description: "Product roadmap and portfolio prioritization brief.",
    confidence: 1,
    subtype: "PDF",
    connection_count: 5,
    citations: [
      {
        document_id: "doc-strategy",
        document_title: "Product Strategy.pdf",
        page_number: 1,
      },
    ],
    metadata: { document_id: "doc-strategy" },
  },
  {
    id: "d-market",
    type: "document",
    label: "Market Research.docx",
    description: "Regional demand and competitive landscape study.",
    confidence: 1,
    subtype: "DOCX",
    connection_count: 4,
    citations: [
      {
        document_id: "doc-market",
        document_title: "Market Research.docx",
        page_number: 1,
      },
    ],
    metadata: { document_id: "doc-market" },
  },
  {
    id: "d-risk",
    type: "document",
    label: "Risk Register Q4.xlsx",
    description: "Operational and compliance risk register extract.",
    confidence: 1,
    subtype: "XLSX",
    connection_count: 2,
    citations: [
      {
        document_id: "doc-risk",
        document_title: "Risk Register Q4.xlsx",
        page_number: 1,
      },
    ],
    metadata: { document_id: "doc-risk" },
  },
];

const DEMO_EDGES: KnowledgeGraphEdge[] = [
  {
    id: "r1",
    source: "t-enterprise",
    target: "t-product",
    relation: "contains",
    confidence: 0.97,
  },
  {
    id: "r2",
    source: "t-enterprise",
    target: "t-market",
    relation: "contains",
    confidence: 0.96,
  },
  {
    id: "r3",
    source: "t-enterprise",
    target: "t-finance",
    relation: "contains",
    confidence: 0.95,
  },
  {
    id: "r4",
    source: "t-enterprise",
    target: "t-risk",
    relation: "contains",
    confidence: 0.93,
  },
  {
    id: "r5",
    source: "t-product",
    target: "e-product-a",
    relation: "contains",
    confidence: 0.94,
  },
  {
    id: "r6",
    source: "t-product",
    target: "e-product-b",
    relation: "contains",
    confidence: 0.92,
  },
  {
    id: "r7",
    source: "t-market",
    target: "e-customer-x",
    relation: "contains",
    confidence: 0.9,
  },
  {
    id: "r8",
    source: "t-market",
    target: "e-customer-y",
    relation: "contains",
    confidence: 0.88,
  },
  {
    id: "r9",
    source: "t-market",
    target: "e-vietnam",
    relation: "contains",
    confidence: 0.94,
  },
  {
    id: "r10",
    source: "t-finance",
    target: "e-q4",
    relation: "contains",
    confidence: 0.93,
  },
  {
    id: "r11",
    source: "e-product-a",
    target: "e-vietnam",
    relation: "targets",
    confidence: 0.91,
    citations: [
      {
        document_id: "doc-market",
        document_title: "Market Research.docx",
        page_number: 12,
        snippet: "Product A is prioritized for Vietnam Market expansion.",
      },
      {
        document_id: "doc-strategy",
        document_title: "Product Strategy.pdf",
        page_number: 8,
        snippet: "Localization for Vietnam Market begins with Product A.",
      },
    ],
  },
  {
    id: "r12",
    source: "e-product-a",
    target: "e-q4",
    relation: "related_to",
    confidence: 0.9,
  },
  {
    id: "r13",
    source: "e-apple",
    target: "e-product-a",
    relation: "owns",
    confidence: 0.8,
  },
  {
    id: "r14",
    source: "e-smith",
    target: "e-alpha",
    relation: "manages",
    confidence: 0.92,
  },
  {
    id: "r15",
    source: "e-alpha",
    target: "e-product-a",
    relation: "related_to",
    confidence: 0.89,
  },
  {
    id: "r16",
    source: "e-alpha",
    target: "e-vietnam",
    relation: "targets",
    confidence: 0.9,
  },
  {
    id: "r17",
    source: "e-customer-x",
    target: "e-product-a",
    relation: "related_to",
    confidence: 0.86,
  },
  {
    id: "r18",
    source: "e-customer-y",
    target: "e-product-b",
    relation: "related_to",
    confidence: 0.84,
  },
  {
    id: "r19",
    source: "d-annual",
    target: "e-product-a",
    relation: "supports",
    confidence: 0.95,
  },
  {
    id: "r20",
    source: "d-annual",
    target: "e-q4",
    relation: "supports",
    confidence: 0.96,
  },
  {
    id: "r21",
    source: "d-strategy",
    target: "e-product-a",
    relation: "supports",
    confidence: 0.94,
  },
  {
    id: "r22",
    source: "d-strategy",
    target: "e-product-b",
    relation: "supports",
    confidence: 0.91,
  },
  {
    id: "r23",
    source: "d-market",
    target: "e-vietnam",
    relation: "supports",
    confidence: 0.93,
  },
  {
    id: "r24",
    source: "d-market",
    target: "e-customer-x",
    relation: "mentions",
    confidence: 0.85,
  },
  {
    id: "r25",
    source: "d-risk",
    target: "t-risk",
    relation: "supports",
    confidence: 0.88,
  },
  {
    id: "r26",
    source: "t-product",
    target: "c-gtm",
    relation: "contains",
    confidence: 0.82,
  },
  {
    id: "r27",
    source: "t-risk",
    target: "c-compliance",
    relation: "contains",
    confidence: 0.87,
  },
  {
    id: "r28",
    source: "e-vietnam",
    target: "c-compliance",
    relation: "related_to",
    confidence: 0.84,
  },
  {
    id: "r29",
    source: "e-q4",
    target: "c-margin",
    relation: "related_to",
    confidence: 0.83,
  },
  {
    id: "r30",
    source: "e-product-a",
    target: "c-gtm",
    relation: "mentions",
    confidence: 0.81,
  },
  {
    id: "r31",
    source: "e-product-b",
    target: "e-vietnam",
    relation: "depends_on",
    confidence: 0.72,
  },
  {
    id: "r32",
    source: "t-finance",
    target: "e-product-a",
    relation: "related_to",
    confidence: 0.86,
  },
];

export function buildDemoKnowledgeGraph(
  workspaceId: string,
): KnowledgeGraphPayload {
  const nodes = DEMO_NODES.map((n) => ({
    ...n,
    citations: n.citations?.map((c) => ({
      ...c,
      document_id: c.document_id,
    })),
  }));
  const edges = DEMO_EDGES.map((e) => ({ ...e }));

  return {
    workspace_id: workspaceId,
    nodes,
    edges,
    stats: {
      entities: nodes.filter((n) => n.type === "entity").length,
      relationships: edges.length,
      topics: nodes.filter((n) => n.type === "topic").length,
      documents: nodes.filter((n) => n.type === "document").length,
      concepts: nodes.filter((n) => n.type === "concept").length,
    },
    generated_at: new Date().toISOString(),
  };
}
