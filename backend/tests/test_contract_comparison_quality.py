# =============================================================================
# File: test_contract_comparison_quality.py
# Module/Service: Contract Comparison Quality Evaluation (FR8 / TASK-CMP-16)
# Layer: Service
# Purpose: Evaluation metrics, quality gate, regression dataset, and
#   production-hardening tests around the existing CMP-15 orchestrator.
# Responsibilities:
#   - Precision/recall/F1; ADDED/REMOVED false positives; LLM budget
#   - Determinism, idempotency, workspace isolation, evidence leakage
# Dependencies:
#   - pytest, ContractComparisonOrchestrator, ComparisonQualityEvaluator
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/comparison_evaluation, Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: Does not call an LLM to judge numeric or existence facts.
# =============================================================================

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.document_structure.diff_types import DiffClassification
from app.ai.document_structure.evaluation_engine import (
    apply_quality_gate,
    deterministic_fingerprint,
    score_classification,
)
from app.ai.document_structure.evaluation_types import (
    ExpectedClause,
    QualityReasonCode,
    QualityStatus,
)
from app.ai.document_structure.llm_boundary_types import LLMTask
from app.ai.document_structure.normalization import normalize_structure
from app.ai.document_structure.pipeline import extract_from_pages, extract_from_text
from app.ai.document_structure.quality_metrics import (
    METRIC_COMPARISON_FAILURE,
    METRIC_COMPARISON_SUCCESS,
    METRIC_LLM_CALLS,
    get_contract_comparison_metrics,
    reset_contract_comparison_metrics_for_tests,
)
from app.ai.document_structure.report_types import ReportStatus
from app.models.enums import DocumentVersionStatus
from app.schemas.comparisons import ComparisonResultPayload
from app.services.document_structure.orchestrator import (
    ContractComparisonError,
    ContractComparisonOrchestrator,
)
from app.services.document_structure.quality import ComparisonQualityEvaluator
from tests.fixtures.comparison_evaluation.ground_truth import v1_v2_expected_clauses

FIXTURES = Path(__file__).parent / "fixtures" / "contracts"
V1_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V1.txt"
V2_TXT = FIXTURES / "Hop_dong_mau_Ra_soat_Phap_ly_V2.txt"


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
    text_or_path: str | Path,
    *,
    title: str,
    document_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
):
    if isinstance(text_or_path, Path):
        structure = extract_from_pages(
            _pages(text_or_path),
            title=title,
            document_id=document_id,
        )
    else:
        structure = extract_from_text(
            text_or_path,
            title=title,
            document_id=document_id,
        )
    normalized = normalize_structure(structure)
    if workspace_id is not None:
        normalized.workspace_id = workspace_id
    return normalized


def _pair(v1: str, v2: str, *, title: str = "C") :
    return _norm(v1, title=f"{title}-v1"), _norm(v2, title=f"{title}-v2")


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_contract_comparison_metrics_for_tests()
    yield
    reset_contract_comparison_metrics_for_tests()


# ---------------------------------------------------------------------------
# Metric math (no pipeline)
# ---------------------------------------------------------------------------


def test_classification_scores_detect_false_added() -> None:
    expected = ["UNCHANGED", "UNCHANGED", "MODIFIED"]
    predicted = ["ADDED", "UNCHANGED", "MODIFIED"]
    added = score_classification(label="ADDED", expected=expected, predicted=predicted)
    assert added.false_positives == 1
    assert added.true_positives == 0
    assert added.precision == 0.0


def test_quality_gate_fails_on_summary_mismatch() -> None:
    v1, v2 = _pair(
        "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ.\n",
        "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    report.clauses["modified"].append(report.clauses["unchanged"][0])
    gated = apply_quality_gate(report)
    assert gated.quality_status is QualityStatus.FAIL
    assert QualityReasonCode.SUMMARY_MISMATCH.value in gated.quality_reasons


def test_quality_gate_fails_if_retrieval_used_for_existence() -> None:
    v1, v2 = _pair(
        "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ.\n",
        "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    report.metadata["retrieval_calls"] = 1
    gated = apply_quality_gate(report)
    assert gated.quality_status is QualityStatus.FAIL
    assert QualityReasonCode.RETRIEVAL_USED_FOR_EXISTENCE.value in gated.quality_reasons


# ---------------------------------------------------------------------------
# Required cases 1–14
# ---------------------------------------------------------------------------


def test_case_unchanged_zero_llm() -> None:
    v1, v2 = _pair(
        "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ tư vấn.\n",
        "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ tư vấn.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    row = report.clause("CLAUSE:1.1")
    assert row is not None
    assert row.status is DiffClassification.UNCHANGED
    assert report.statistics.llm_calls == 0
    assert report.quality_status is not QualityStatus.FAIL


def test_case_text_modification() -> None:
    v1, v2 = _pair(
        "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ tư vấn pháp lý.\n",
        "ĐIỀU 1. Phạm vi\n1.1. Bên A cung cấp dịch vụ tư vấn thuế và kế toán.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    row = report.clause("CLAUSE:1.1")
    assert row is not None
    assert row.status is DiffClassification.MODIFIED


def test_case_added_clause() -> None:
    v1, v2 = _pair(
        "ĐIỀU 1. Phạm vi\n1.1. Dịch vụ tư vấn.\n",
        "ĐIỀU 1. Phạm vi\n1.1. Dịch vụ tư vấn.\n1.2. Dịch vụ đào tạo bổ sung.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    row = report.clause("CLAUSE:1.2")
    assert row is not None
    assert row.status is DiffClassification.ADDED
    assert row.v1_clause_id is None
    assert row.v2_clause_id == "CLAUSE:1.2"


def test_case_removed_clause() -> None:
    v1, v2 = _pair(
        "ĐIỀU 1. Phạm vi\n1.1. Dịch vụ tư vấn.\n1.2. Dịch vụ đào tạo.\n",
        "ĐIỀU 1. Phạm vi\n1.1. Dịch vụ tư vấn.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    row = report.clause("CLAUSE:1.2")
    assert row is not None
    assert row.status is DiffClassification.REMOVED
    assert row.v2_clause_id is None
    assert row.v1_clause_id == "CLAUSE:1.2"


def test_case_renumbered_clause_maps() -> None:
    v1, v2 = _pair(
        "ĐIỀU 8. Trách nhiệm bồi thường\n"
        "Bên B chịu trách nhiệm bồi thường thiệt hại trực tiếp phát sinh từ vi phạm nghĩa vụ.\n",
        "ĐIỀU 9. Trách nhiệm của bên B\n"
        "Bên B chịu trách nhiệm bồi thường thiệt hại trực tiếp phát sinh từ vi phạm nghĩa vụ.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    article_8 = report.clause("ARTICLE:8")
    article_9 = report.clause("ARTICLE:9")
    assert article_8 is not None
    mapped = article_8.v2_clause_id == "ARTICLE:9" or (
        article_9 is not None and article_9.status is not DiffClassification.ADDED
    )
    if article_8.status is DiffClassification.REMOVED and (
        article_9 is None or article_9.status is DiffClassification.ADDED
    ):
        pytest.fail("renumbered ARTICLE:8/ARTICLE:9 treated as REMOVED+ADDED")
    assert mapped or article_8.status in {
        DiffClassification.UNCHANGED,
        DiffClassification.MODIFIED,
    }


def test_case_retrieval_miss_is_not_added() -> None:
    v1 = _norm(V1_TXT, title="V1")
    v2 = _norm(V2_TXT, title="V2")
    assert "CLAUSE:1.2" in v1.identity_keys()
    assert "CLAUSE:1.2" in v2.identity_keys()
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    for key in ("CLAUSE:1.2", "CLAUSE:1.3"):
        row = report.clause(key)
        assert row is not None
        assert row.status not in {DiffClassification.ADDED, DiffClassification.REMOVED}


def test_case_amount_change_is_deterministic() -> None:
    v1, v2 = _pair(
        "ĐIỀU 3. Giá trị hợp đồng\n3.1. Giá trị hợp đồng là 480.000.000 đồng.\n",
        "ĐIỀU 3. Giá trị hợp đồng\n3.1. Giá trị hợp đồng là 600.000.000 đồng.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    row = report.clause("CLAUSE:3.1")
    assert row is not None
    assert row.status is DiffClassification.MODIFIED
    money = [item for item in row.exact_differences if item.get("value_type") == "MONEY"]
    assert money
    assert report.statistics.llm_calls == 0


def test_case_percentage_change_is_deterministic() -> None:
    v1, v2 = _pair(
        "ĐIỀU 8. Giới hạn trách nhiệm\n8.2. Trách nhiệm không vượt quá 10% giá trị hợp đồng.\n",
        "ĐIỀU 8. Giới hạn trách nhiệm\n8.2. Trách nhiệm không vượt quá 15% giá trị hợp đồng.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    row = report.clause("CLAUSE:8.2")
    assert row is not None
    assert row.status is DiffClassification.MODIFIED
    pct = [item for item in row.exact_differences if item.get("value_type") == "PERCENTAGE"]
    assert pct
    assert report.statistics.llm_calls == 0


def test_case_date_change_is_deterministic() -> None:
    v1, v2 = _pair(
        "ĐIỀU 4. Hiệu lực\n4.1. Hợp đồng có hiệu lực từ ngày 01/01/2026.\n",
        "ĐIỀU 4. Hiệu lực\n4.1. Hợp đồng có hiệu lực từ ngày 01/01/2027.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    row = report.clause("CLAUSE:4.1")
    assert row is not None
    assert row.status is DiffClassification.MODIFIED
    dates = [item for item in row.exact_differences if item.get("value_type") == "DATE"]
    assert dates
    assert report.statistics.llm_calls == 0


def test_case_duration_change_is_deterministic() -> None:
    v1, v2 = _pair(
        "ĐIỀU 2. Thời hạn\n2.1. Thời hạn hợp đồng là 12 tháng.\n",
        "ĐIỀU 2. Thời hạn\n2.1. Thời hạn hợp đồng là 24 tháng.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    row = report.clause("CLAUSE:2.1")
    assert row is not None
    assert row.status is DiffClassification.MODIFIED
    durations = [item for item in row.exact_differences if item.get("value_type") == "DURATION"]
    assert durations
    assert report.statistics.llm_calls == 0


def test_case_liability_risk_category() -> None:
    v1, v2 = _pair(
        "ĐIỀU 8. Giới hạn trách nhiệm\n8.2. Tổng trách nhiệm bồi thường không vượt quá 1.000.000 USD.\n",
        "ĐIỀU 8. Giới hạn trách nhiệm\n8.2. Tổng trách nhiệm bồi thường không vượt quá 500.000 USD.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    row = report.clause("CLAUSE:8.2")
    assert row is not None
    assert row.risk is not None
    assert row.risk["risk_category"] == "LIABILITY"
    assert row.risk["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_case_termination_risk_category() -> None:
    v1, v2 = _pair(
        "ĐIỀU 12. Chấm dứt hợp đồng\n12.1. Mỗi bên được chấm dứt với thông báo trước 30 ngày.\n",
        "ĐIỀU 12. Chấm dứt hợp đồng\n12.1. Mỗi bên được chấm dứt với thông báo trước 7 ngày.\n",
    )
    report = ContractComparisonOrchestrator().compare_structures(v1, v2)
    row = report.clause("CLAUSE:12.1") or report.clause("ARTICLE:12")
    assert row is not None
    assert row.status is DiffClassification.MODIFIED
    assert row.risk is not None
    assert row.risk["risk_category"] == "TERMINATION"


def test_case_invalid_evidence_is_not_verified_citation() -> None:
    report = ContractComparisonOrchestrator().compare_structures(
        _norm(V1_TXT, title="V1"),
        _norm(V2_TXT, title="V2"),
    )
    for row in (*report.clauses["modified"], *report.clauses["added"], *report.clauses["removed"]):
        status = (row.verification or {}).get("status")
        if status == "INVALID":
            assert row.citations == []
        for citation in row.citations:
            assert citation.get("evidence_id")
            verified_ids = (row.verification or {}).get("verified_evidence_ids") or []
            assert citation.get("evidence_id") in verified_ids


def test_case_invalid_llm_output_does_not_fabricate_diff() -> None:
    def generate(_system: str, _user: str) -> str:
        return "{not-json"

    v1, v2 = _pair(
        "ĐIỀU 3. Giá trị\n3.1. Giá trị là 480.000.000 đồng.\n",
        "ĐIỀU 3. Giá trị\n3.1. Giá trị là 600.000.000 đồng.\n",
        title="llm",
    )
    report = ContractComparisonOrchestrator().compare_structures(
        v1,
        v2,
        llm_task=LLMTask.EXPLAIN,
        generate=generate,
    )
    row = report.clause("CLAUSE:3.1")
    assert row is not None
    assert row.status is DiffClassification.MODIFIED
    assert row.exact_differences
    assert report.explanation_incomplete is True
    assert report.status is ReportStatus.PARTIAL_EXPLANATION
    assert report.quality_status is QualityStatus.PASS_WITH_WARNINGS


# ---------------------------------------------------------------------------
# V1/V2 regression dataset + metrics
# ---------------------------------------------------------------------------


def test_v1_v2_ground_truth_evaluation() -> None:
    case_id, expected = v1_v2_expected_clauses()
    report = ContractComparisonOrchestrator().compare_structures(
        _norm(V1_TXT, title="V1"),
        _norm(V2_TXT, title="V2"),
    )
    result = ComparisonQualityEvaluator().evaluate(report, expected, case_id=case_id)
    assert result.mismatches == [], result.mismatches
    assert result.diff is not None
    assert result.diff.added_false_positive_rate == 0.0
    assert result.diff.removed_false_positive_rate == 0.0
    assert result.llm.calls == 0
    assert result.llm.unchanged_llm_calls == 0
    assert result.latency_ms >= 0
    assert result.quality_status is not QualityStatus.FAIL
    assert report.metadata["performance"]["total_ms"] >= 0
    assert report.metadata["performance"]["mapping_ms"] >= 0


def test_summary_matches_clause_buckets() -> None:
    report = ContractComparisonOrchestrator().compare_structures(
        _norm(V1_TXT, title="V1"),
        _norm(V2_TXT, title="V2"),
    )
    assert report.summary.unchanged == len(report.clauses["unchanged"])
    assert report.summary.modified == len(report.clauses["modified"])
    assert report.summary.added == len(report.clauses["added"])
    assert report.summary.removed == len(report.clauses["removed"])
    assert report.summary.total_clauses == (
        report.summary.unchanged
        + report.summary.modified
        + report.summary.added
        + report.summary.removed
    )


def test_deterministic_repeatability() -> None:
    v1a = _norm(V1_TXT, title="V1")
    v2a = _norm(V2_TXT, title="V2")
    first = ContractComparisonOrchestrator().compare_structures(v1a, v2a)
    second = ContractComparisonOrchestrator().compare_structures(
        _norm(V1_TXT, title="V1", document_id=v1a.document_id),
        _norm(V2_TXT, title="V2", document_id=v2a.document_id),
    )
    assert deterministic_fingerprint(first) == deterministic_fingerprint(second)


def test_idempotent_statistics_on_repeat() -> None:
    v1, v2 = _pair(
        "ĐIỀU 1. Phạm vi\n1.1. Dịch vụ tư vấn.\n",
        "ĐIỀU 1. Phạm vi\n1.1. Dịch vụ tư vấn.\n1.2. Dịch vụ mới.\n",
    )
    orch = ContractComparisonOrchestrator()
    first = orch.compare_structures(v1, v2)
    second = orch.compare_structures(v1, v2)
    assert first.summary.as_dict() == second.summary.as_dict()
    assert first.statistics.llm_calls == second.statistics.llm_calls == 0
    assert first.statistics.added == second.statistics.added


def test_metrics_record_success_and_failure() -> None:
    v1, v2 = _pair(
        "ĐIỀU 1. Phạm vi\n1.1. Dịch vụ tư vấn.\n",
        "ĐIỀU 1. Phạm vi\n1.1. Dịch vụ tư vấn.\n",
    )
    ContractComparisonOrchestrator().compare_structures(v1, v2)
    snap = get_contract_comparison_metrics().snapshot()
    assert snap[METRIC_COMPARISON_SUCCESS] >= 1
    assert snap[METRIC_LLM_CALLS] == 0
    with pytest.raises(ContractComparisonError):
        ContractComparisonOrchestrator().compare_structures(v1, v1)
    snap = get_contract_comparison_metrics().snapshot()
    assert snap[METRIC_COMPARISON_FAILURE] >= 1


def test_llm_budget_warning() -> None:
    def generate(_system: str, _user: str) -> str:
        return json.dumps(
            {
                "explanation": "Giá trị hợp đồng thay đổi.",
                "claims": [],
                "evidence_ids": [],
            }
        )

    v1, v2 = _pair(
        "ĐIỀU 3. Giá trị\n3.1. Giá trị là 480.000.000 đồng.\n",
        "ĐIỀU 3. Giá trị\n3.1. Giá trị là 600.000.000 đồng.\n",
        title="budget",
    )
    report = ContractComparisonOrchestrator(max_llm_calls=0).compare_structures(
        v1,
        v2,
        llm_task=LLMTask.EXPLAIN,
        generate=generate,
    )
    assert report.statistics.llm_calls >= 1
    assert report.quality_status is QualityStatus.PASS_WITH_WARNINGS
    assert QualityReasonCode.LLM_BUDGET_EXCEEDED.value in report.quality_reasons


def test_error_message_does_not_leak_contract_text() -> None:
    v1 = _norm("ĐIỀU 1. Bí mật\n1.1. Mã số thuế 0312345678 và số tài khoản 123456.\n", title="s")
    with pytest.raises(ContractComparisonError) as exc:
        ContractComparisonOrchestrator().compare_structures(v1, v1)
    assert "0312345678" not in exc.value.message
    assert "123456" not in exc.value.message


def test_evidence_stays_in_compared_documents() -> None:
    ws = uuid.uuid4()
    v1 = _norm(V1_TXT, title="V1", workspace_id=ws)
    v2 = _norm(V2_TXT, title="V2", workspace_id=ws)
    report = ContractComparisonOrchestrator().compare_structures(v1, v2, workspace_id=ws)
    allowed = {str(v1.document_id), str(v2.document_id)}
    for row in (*report.clauses["modified"], *report.clauses["added"], *report.clauses["removed"]):
        for item in (*row.evidence, *row.citations):
            doc = item.get("document_id")
            if doc:
                assert str(doc) in allowed
            ws_id = item.get("workspace_id")
            if ws_id:
                assert str(ws_id) == str(ws)


def test_fr8_api_schema_unchanged() -> None:
    payload = ComparisonResultPayload(similarities=["a"], differences=["b"])
    dumped = payload.model_dump()
    assert set(dumped) == {"similarities", "differences"}


def test_mapping_failure_is_recorded_as_failure_not_success() -> None:
    class BrokenMapper:
        def map_structures(self, *_args, **_kwargs):
            raise RuntimeError("mapping exploded")

    v1, v2 = _pair(
        "ĐIỀU 1. Phạm vi\n1.1. Dịch vụ tư vấn.\n",
        "ĐIỀU 1. Phạm vi\n1.1. Dịch vụ khác.\n",
    )
    with pytest.raises(ContractComparisonError) as exc:
        ContractComparisonOrchestrator(mapper=BrokenMapper()).compare_structures(v1, v2)  # type: ignore[arg-type]
    assert exc.value.code == "mapping_failed"
    snap = get_contract_comparison_metrics().snapshot()
    assert snap[METRIC_COMPARISON_FAILURE] >= 1


@pytest.mark.asyncio
async def test_compare_documents_isolates_workspace() -> None:
    class Repo:
        def __init__(self) -> None:
            self.documents: dict[uuid.UUID, SimpleNamespace] = {}
            self.versions: dict[uuid.UUID, SimpleNamespace] = {}

        async def get_document(self, workspace_id: uuid.UUID, document_id: uuid.UUID):
            doc = self.documents.get(document_id)
            if doc is None or doc.workspace_id != workspace_id:
                return None
            return doc

        async def get_version(self, workspace_id, document_id, version_id):
            doc = await self.get_document(workspace_id, document_id)
            if doc is None:
                return None
            return self.versions.get(version_id)

    class Extractor:
        def __init__(self, documents: Repo) -> None:
            self._documents = documents

        async def extract_normalized(self, document_id, *, workspace_id, version_id=None):
            from app.services.document_structure.extractor import DocumentStructureError

            if await documents.get_document(workspace_id, document_id) is None:
                raise DocumentStructureError("not_found", "Document not found", status_code=404)
            raise AssertionError("must not extract unauthorized document")

    documents = Repo()
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    ver_a = uuid.uuid4()
    ver_b = uuid.uuid4()
    documents.documents[doc_a] = SimpleNamespace(
        id=doc_a, workspace_id=ws_a, current_version_id=ver_a
    )
    documents.documents[doc_b] = SimpleNamespace(
        id=doc_b, workspace_id=ws_b, current_version_id=ver_b
    )
    documents.versions[ver_a] = SimpleNamespace(
        id=ver_a, document_id=doc_a, status=DocumentVersionStatus.ready
    )
    documents.versions[ver_b] = SimpleNamespace(
        id=ver_b, document_id=doc_b, status=DocumentVersionStatus.ready
    )
    orch = ContractComparisonOrchestrator(
        extractor=Extractor(documents),
        documents=documents,
    )
    with pytest.raises(ContractComparisonError) as exc:
        await orch.compare_documents(
            workspace_id=ws_a,
            source_document_id=doc_a,
            target_document_id=doc_b,
        )
    assert exc.value.code == "not_found"
    assert "ĐIỀU" not in exc.value.message
