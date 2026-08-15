# =============================================================================
# File: test_contract_comparison_orchestration.py
# Module/Service: Contract Comparison Orchestration (FR8 / TASK-CMP-15)
# Layer: Service
# Purpose: Unit, integration, regression, citation, and LLM-skip tests for
#   end-to-end comparison orchestration and auditable reports.
# Responsibilities:
#   - Input / workspace validation; aggregation; statistics; error propagation
#   - V1/V2 false ADDED/REMOVED protection; UNCHANGED → 0 LLM
# Dependencies:
#   - pytest, ContractComparisonOrchestrator, CMP-01..13 pipeline
# Public Exports:
#   - N/A
# Database/Table: N/A (in-memory fixtures / fakes)
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: Does not call the FR8 Comparison HTTP similarities path.
# =============================================================================

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.llm_boundary_types import LLMTask
from app.ai.document_structure.normalization import normalize_structure
from app.ai.document_structure.pipeline import extract_from_pages, extract_from_text
from app.ai.document_structure.report_engine import summarize_clauses
from app.ai.document_structure.report_types import (
    ClauseComparisonResult,
    ReportStatus,
)
from app.ai.document_structure.scoring_types import RiskLevel
from app.models.enums import DocumentVersionStatus
from app.services.document_structure.orchestrator import (
    ContractComparisonError,
    ContractComparisonOrchestrator,
)

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
V1_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V1.txt"
V2_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V2.txt"

ARTICLE_REGRESSION = {
    "ARTICLE:1": DiffClassification.UNCHANGED,
    "ARTICLE:2": DiffClassification.MODIFIED,
    "ARTICLE:3": DiffClassification.MODIFIED,
    "ARTICLE:4": DiffClassification.UNCHANGED,
    "ARTICLE:5": DiffClassification.UNCHANGED,
    "ARTICLE:6": DiffClassification.UNCHANGED,
    "ARTICLE:7": DiffClassification.UNCHANGED,
    "ARTICLE:8": DiffClassification.MODIFIED,
    "ARTICLE:9": DiffClassification.MODIFIED,
    "ARTICLE:10": DiffClassification.UNCHANGED,
    "ARTICLE:11": DiffClassification.MODIFIED,
    "ARTICLE:12": DiffClassification.UNCHANGED,
}


def _pages(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    pages: list[tuple[int, str]] = []
    current: int | None = None
    buf: list[str] = []
    for line in text.splitlines():
        marker = line.strip()
        if marker.startswith("===== PAGE ") and marker.endswith("====="):
            if current is not None:
                pages.append((current, "\n".join(buf)))
            current = int(marker.replace("=====", "").replace("PAGE", "").strip())
            buf = []
            continue
        buf.append(line)
    if current is not None:
        pages.append((current, "\n".join(buf)))
    return pages


def _norm(
    path: Path,
    *,
    title: str,
    document_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
):
    structure = extract_from_pages(
        _pages(path),
        title=title,
        document_id=document_id,
    )
    normalized = normalize_structure(structure)
    if workspace_id is not None:
        normalized.workspace_id = workspace_id
    if version_id is not None:
        normalized.version_id = version_id
    return normalized


def _report(v1=None, v2=None, **kwargs):
    source = v1 or _norm(V1_TXT, title="V1")
    target = v2 or _norm(V2_TXT, title="V2")
    return ContractComparisonOrchestrator().compare_structures(source, target, **kwargs)


# ---------------------------------------------------------------------------
# Unit: validation, aggregation, errors
# ---------------------------------------------------------------------------


def test_same_document_version_is_rejected() -> None:
    v1 = _norm(V1_TXT, title="V1")
    with pytest.raises(ContractComparisonError) as exc:
        ContractComparisonOrchestrator().compare_structures(v1, v1)
    assert exc.value.code == "invalid_document_pair"
    assert exc.value.status_code == 400


def test_cross_workspace_structures_are_rejected() -> None:
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    v1 = _norm(V1_TXT, title="V1", workspace_id=ws_a)
    v2 = _norm(V2_TXT, title="V2", workspace_id=ws_b)
    with pytest.raises(ContractComparisonError) as exc:
        ContractComparisonOrchestrator().compare_structures(v1, v2)
    assert exc.value.code == "not_found"
    assert exc.value.status_code == 404


def test_empty_clause_inventory_is_rejected() -> None:
    empty = normalize_structure(extract_from_text("plain prose without clauses"))
    other = _norm(V2_TXT, title="V2")
    with pytest.raises(ContractComparisonError) as exc:
        ContractComparisonOrchestrator().compare_structures(empty, other)
    assert exc.value.code == "clauses_not_available"
    assert exc.value.status_code == 409


def test_statistics_match_clause_buckets() -> None:
    rows = [
        ClauseComparisonResult(
            clause_id="CLAUSE:1.1",
            v1_clause_id="CLAUSE:1.1",
            v2_clause_id="CLAUSE:1.1",
            status=DiffClassification.UNCHANGED,
        ),
        ClauseComparisonResult(
            clause_id="CLAUSE:2.1",
            v1_clause_id="CLAUSE:2.1",
            v2_clause_id="CLAUSE:2.1",
            status=DiffClassification.MODIFIED,
        ),
        ClauseComparisonResult(
            clause_id="CLAUSE:8.3",
            v1_clause_id=None,
            v2_clause_id="CLAUSE:8.3",
            status=DiffClassification.ADDED,
        ),
        ClauseComparisonResult(
            clause_id="CLAUSE:9.9",
            v1_clause_id="CLAUSE:9.9",
            v2_clause_id=None,
            status=DiffClassification.REMOVED,
        ),
        ClauseComparisonResult(
            clause_id="CLAUSE:x",
            v1_clause_id="CLAUSE:x",
            v2_clause_id="CLAUSE:y",
            status=DiffClassification.AMBIGUOUS_MAPPING,
        ),
    ]
    summary, extra = summarize_clauses(rows)
    assert summary.unchanged == 1
    assert summary.modified == 1
    assert summary.added == 1
    assert summary.removed == 1
    assert summary.total_clauses == 4
    assert extra["unresolved"] == 1


def test_mapping_failure_is_not_a_successful_report() -> None:
    class BrokenMapper:
        def map_structures(self, *_args, **_kwargs):
            raise RuntimeError("mapping exploded")

    v1 = _norm(V1_TXT, title="V1")
    v2 = _norm(V2_TXT, title="V2")
    orch = ContractComparisonOrchestrator(mapper=BrokenMapper())  # type: ignore[arg-type]
    with pytest.raises(ContractComparisonError) as exc:
        orch.compare_structures(v1, v2)
    assert exc.value.code == "mapping_failed"


def test_partial_llm_failure_keeps_deterministic_diff() -> None:
    def generate(_system: str, _user: str) -> str:
        raise TimeoutError("llm timeout")

    report = _report(llm_task=LLMTask.EXPLAIN, generate=generate)
    assert report.summary.modified >= 1
    assert report.explanation_incomplete is True
    assert report.status is ReportStatus.PARTIAL_EXPLANATION
    assert report.clause("CLAUSE:3.1") is not None
    assert report.clause("CLAUSE:3.1").status is DiffClassification.MODIFIED


# ---------------------------------------------------------------------------
# Integration / regression
# ---------------------------------------------------------------------------


def test_v1_v2_end_to_end_pipeline_and_article_regression() -> None:
    report = _report()
    assert report.summary.total_clauses == (
        report.summary.unchanged
        + report.summary.modified
        + report.summary.added
        + report.summary.removed
    )
    assert report.summary.added == len(report.clauses["added"])
    assert report.summary.removed == len(report.clauses["removed"])
    assert report.statistics.llm_calls == 0
    assert report.metadata["retrieval_calls"] == 0
    assert report.statistics.processing_time_ms >= 0

    for key, expected in ARTICLE_REGRESSION.items():
        row = report.clause(key)
        assert row is not None, key
        actual = row.subtree_status or row.status
        assert actual is expected, (key, row.status, row.subtree_status)

    clause_2_1 = report.clause("CLAUSE:2.1")
    clause_3_1 = report.clause("CLAUSE:3.1")
    clause_8_2 = report.clause("CLAUSE:8.2")
    clause_9_2 = report.clause("CLAUSE:9.2") or report.clause("CLAUSE:9.1")
    clause_11_2 = report.clause("CLAUSE:11.2")
    for row in (clause_2_1, clause_3_1, clause_8_2, clause_11_2):
        assert row is not None
        assert row.status is DiffClassification.MODIFIED
    assert clause_9_2 is not None
    assert clause_9_2.status is DiffClassification.MODIFIED


def test_clause_1_2_and_1_3_are_not_added_when_present_in_both() -> None:
    report = _report()
    for key in ("CLAUSE:1.2", "CLAUSE:1.3"):
        row = report.clause(key)
        assert row is not None, key
        assert row.status is not DiffClassification.ADDED
        assert row.status is DiffClassification.UNCHANGED
        assert row.v1_clause_id == key
        assert row.v2_clause_id == key
        assert all(item.clause_id != key for item in report.clauses["added"])


def test_retrieval_miss_is_not_clause_absence() -> None:
    """Full inventories are compared even if a caller only 'retrieved' V2 1.2."""
    v1 = _norm(V1_TXT, title="V1")
    v2 = _norm(V2_TXT, title="V2")
    retrieved_only = {unit.identity_key for unit in v2.walk() if unit.identity_key in {"CLAUSE:1.2", "CLAUSE:1.3"}}
    assert retrieved_only == {"CLAUSE:1.2", "CLAUSE:1.3"} or {"CLAUSE:1.2", "CLAUSE:1.3"} <= v2.identity_keys()
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    assert report.clause("CLAUSE:1.2").status is not DiffClassification.ADDED  # type: ignore[union-attr]
    assert report.clause("CLAUSE:1.3").status is not DiffClassification.ADDED  # type: ignore[union-attr]
    assert "CLAUSE:1.2" in v1.identity_keys()
    assert "CLAUSE:1.3" in v1.identity_keys()


def test_genuinely_added_clauses_are_detected() -> None:
    report = _report()
    added_ids = {row.clause_id for row in report.clauses["added"]}
    assert "CLAUSE:8.3" in added_ids
    assert "CLAUSE:9.3" in added_ids
    for key in ("CLAUSE:8.3", "CLAUSE:9.3"):
        row = report.clause(key)
        assert row is not None
        assert row.v1_clause_id is None
        assert row.v2_clause_id == key
        assert all(item.get("side") != "OLD" for item in row.evidence)


def test_unchanged_preserves_original_text_not_normalized_only() -> None:
    report = _report()
    row = report.clause("CLAUSE:1.2")
    assert row is not None
    assert row.v1_text
    assert row.v2_text
    assert row.v1_text == row.v2_text
    assert "1.2" in row.v1_text or "1.2" in (row.v1_normalized or "")


def test_modified_keeps_exact_differences_without_llm() -> None:
    report = _report()
    row = report.clause("CLAUSE:3.1")
    assert row is not None
    assert row.status is DiffClassification.MODIFIED
    assert row.exact_differences
    money = [
        item
        for item in row.exact_differences
        if item.get("value_type") in {"MONEY", "NUMBER"}
    ]
    assert money
    change = money[0]
    assert change.get("old") is not None
    assert change.get("new") is not None
    assert report.statistics.llm_calls == 0


def test_risk_comes_from_existing_scoring_engine() -> None:
    report = _report()
    row = report.clause("CLAUSE:8.2")
    assert row is not None
    assert row.risk is not None
    assert row.risk["risk_category"] == "LIABILITY"
    assert row.risk["risk_level"] in {item.value for item in RiskLevel}
    assert row.risk["triggered_rules"]
    levels = report.statistics.risk_counts
    assert sum(levels.values()) == len(report.risks)


def test_meaningful_findings_have_verified_or_bound_evidence() -> None:
    report = _report()
    for row in (*report.clauses["modified"], *report.clauses["added"], *report.clauses["removed"]):
        if row.verification is None:
            continue
        status = row.verification.get("status")
        if status in {"VERIFIED", "PARTIALLY_VERIFIED"}:
            assert row.citations
            for citation in row.citations:
                assert citation.get("evidence_id")
                assert citation.get("document_id")
                if row.status is DiffClassification.ADDED:
                    assert citation.get("side") == "NEW"
                if row.status is DiffClassification.REMOVED:
                    assert citation.get("side") == "OLD"
        if status == "INVALID":
            assert row.citations == []


def test_unchanged_clauses_do_not_call_llm_even_when_explain_requested() -> None:
    calls: list[int] = []

    def generate(_system: str, _user: str) -> str:
        calls.append(1)
        raise AssertionError("UNCHANGED must not invoke LLM")

    v1 = normalize_structure(
        extract_from_text(
            "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ.\n",
            title="A",
            document_id=uuid.uuid4(),
        )
    )
    v2 = normalize_structure(
        extract_from_text(
            "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ.\n",
            title="B",
            document_id=uuid.uuid4(),
        )
    )
    report = ContractComparisonOrchestrator().compare_structures(
        v1,
        v2,
        llm_task=LLMTask.EXPLAIN,
        generate=generate,
    )
    assert report.summary.modified == 0
    assert report.summary.added == 0
    assert report.summary.removed == 0
    assert report.statistics.llm_calls == 0
    assert calls == []


def test_default_path_is_zero_llm_on_full_regression_pair() -> None:
    report = _report()
    assert report.statistics.llm_calls == 0
    assert report.statistics.llm_tokens == 0
    for row in report.clauses["unchanged"]:
        assert row.explanation is None or row.explanation.get("llm_calls") in (None, 0)


def test_report_as_dict_exposes_required_sections() -> None:
    payload = _report().as_dict(include_text=False)
    comparison = payload["comparison"]
    assert "metadata" in comparison
    assert "summary" in comparison
    assert "statistics" in comparison
    assert "clauses" in comparison
    assert "risks" in comparison
    assert "citations" in comparison
    unchanged = comparison["clauses"]["unchanged"]
    if unchanged:
        assert "v1_text" not in unchanged[0]
        assert "v2_text" not in unchanged[0]


# ---------------------------------------------------------------------------
# Async workspace isolation
# ---------------------------------------------------------------------------


class _FakeDocuments:
    def __init__(self) -> None:
        self.documents: dict[uuid.UUID, SimpleNamespace] = {}
        self.versions: dict[uuid.UUID, SimpleNamespace] = {}

    async def get_document(self, workspace_id: uuid.UUID, document_id: uuid.UUID):
        doc = self.documents.get(document_id)
        if doc is None or doc.workspace_id != workspace_id:
            return None
        return doc

    async def get_version(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
    ):
        doc = await self.get_document(workspace_id, document_id)
        if doc is None:
            return None
        ver = self.versions.get(version_id)
        if ver is None or ver.document_id != document_id:
            return None
        return ver


class _FakeExtractor:
    def __init__(self, documents: _FakeDocuments, structures: dict[uuid.UUID, object]) -> None:
        self._documents = documents
        self._structures = structures

    async def extract_normalized(
        self,
        document_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
    ):
        from app.services.document_structure.extractor import DocumentStructureError

        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise DocumentStructureError(
                "not_found",
                f"Document {document_id} not found",
                status_code=404,
            )
        return self._structures[document_id]


def _seed_doc(repo: _FakeDocuments, *, workspace_id: uuid.UUID, status=DocumentVersionStatus.ready):
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    repo.documents[document_id] = SimpleNamespace(
        id=document_id,
        workspace_id=workspace_id,
        current_version_id=version_id,
    )
    repo.versions[version_id] = SimpleNamespace(
        id=version_id,
        document_id=document_id,
        status=status,
    )
    return document_id, version_id


@pytest.mark.asyncio
async def test_compare_documents_rejects_cross_workspace() -> None:
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    repo = _FakeDocuments()
    doc_a, _ = _seed_doc(repo, workspace_id=ws_a)
    doc_b, _ = _seed_doc(repo, workspace_id=ws_b)
    extractor = _FakeExtractor(repo, {})
    orch = ContractComparisonOrchestrator(extractor=extractor, documents=repo)
    with pytest.raises(ContractComparisonError) as exc:
        await orch.compare_documents(
            workspace_id=ws_a,
            source_document_id=doc_a,
            target_document_id=doc_b,
        )
    assert exc.value.code == "not_found"
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_compare_documents_rejects_version_not_ready() -> None:
    ws = uuid.uuid4()
    repo = _FakeDocuments()
    doc_a, _ = _seed_doc(repo, workspace_id=ws, status=DocumentVersionStatus.processing)
    doc_b, _ = _seed_doc(repo, workspace_id=ws)
    orch = ContractComparisonOrchestrator(
        extractor=_FakeExtractor(repo, {}),
        documents=repo,
    )
    with pytest.raises(ContractComparisonError) as exc:
        await orch.compare_documents(
            workspace_id=ws,
            source_document_id=doc_a,
            target_document_id=doc_b,
        )
    assert exc.value.code == "version_not_ready"
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_compare_documents_runs_when_both_ready() -> None:
    ws = uuid.uuid4()
    repo = _FakeDocuments()
    doc_a, ver_a = _seed_doc(repo, workspace_id=ws)
    doc_b, ver_b = _seed_doc(repo, workspace_id=ws)
    v1 = _norm(V1_TXT, title="V1", document_id=doc_a, workspace_id=ws, version_id=ver_a)
    v2 = _norm(V2_TXT, title="V2", document_id=doc_b, workspace_id=ws, version_id=ver_b)
    orch = ContractComparisonOrchestrator(
        extractor=_FakeExtractor(repo, {doc_a: v1, doc_b: v2}),
        documents=repo,
    )
    report = await orch.compare_documents(
        workspace_id=ws,
        source_document_id=doc_a,
        target_document_id=doc_b,
    )
    assert report.workspace_id == ws
    assert report.clause("CLAUSE:1.2").status is DiffClassification.UNCHANGED  # type: ignore[union-attr]
    assert report.statistics.llm_calls == 0
