# =============================================================================
# File: test_legal_risk_taxonomy.py
# Module/Service: Legal Risk Taxonomy (FR8 / TASK-CMP-07)
# Layer: Service
# Purpose: Unit, rule, multilingual, pipeline, V1/V2, FP/FN taxonomy tests.
# Responsibilities:
#   - 14 canonical categories; title vs MONEY; no risk_level; 0 LLM
# Dependencies:
#   - pytest, classify_clause_diff, classify_taxonomy, CMP-01..06 pipeline
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*.txt
# Important Notes: Taxonomy only — never assert HIGH/CRITICAL risk.
# =============================================================================

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.ai.document_structure.diff_engine import diff_normalized_structures
from app.ai.document_structure.diff_types import (
    ClauseDiff,
    DiffClassification,
    DiffResult,
    DiffSignals,
    DiffVerificationStatus,
)
from app.ai.document_structure.exact_engine import extract_exact_differences
from app.ai.document_structure.exact_types import ValueType
from app.ai.document_structure.mapping_types import MappingStatus, MappingType, clause_ref
from app.ai.document_structure.normalization import (
    NormalizedDocumentStructure,
    NormalizedUnit,
    normalize_structure,
)
from app.ai.document_structure.pipeline import extract_from_pages, extract_from_text
from app.ai.document_structure.taxonomy_engine import classify_clause_diff, classify_taxonomy
from app.ai.document_structure.taxonomy_rules import rules_for
from app.ai.document_structure.taxonomy_types import (
    RISK_LEVEL_UNSET,
    ClassificationConfidence,
    ClassificationMethod,
    RiskCategory,
)
from app.ai.document_structure.types import StructuralUnitType
from app.services.document_structure.taxonomy import LegalRiskTaxonomyEngine

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


def _norm(text: str) -> NormalizedDocumentStructure:
    return normalize_structure(extract_from_text(text, title="Doc", document_id=uuid4()))


def _unit(body: str, *, key: str = "CLAUSE:1.1", title: str = "") -> NormalizedUnit:
    number = key.split(":")[-1]
    unit_type = (
        StructuralUnitType.CLAUSE if key.startswith("CLAUSE") else StructuralUnitType.ARTICLE
    )
    heading = title or body.split(".")[0][:80]
    return NormalizedUnit(
        source_id=key,
        document_id=uuid4(),
        type=unit_type,
        canonical_number=number,
        identity_key=key,
        qualified_key=key,
        number_path=(number,),
        parent_identity_key=None,
        original_title=title,
        original_text=body,
        original_heading=title,
        normalized_title=title.casefold(),
        folded_title=title.casefold(),
        normalized_body=body.casefold(),
        folded_body=body.casefold(),
        aliases=(number,),
        heading_path=title or key,
        order_index=1,
        level=1,
        page_start=1,
        page_end=1,
    )


def _diff_row(
    classification: DiffClassification,
    source: NormalizedUnit | None,
    target: NormalizedUnit | None,
) -> ClauseDiff:
    return ClauseDiff(
        classification=classification,
        verification_status=DiffVerificationStatus.VERIFIED,
        mapping_status=MappingStatus.EXACT,
        mapping_type=MappingType.EXACT,
        mapping_confidence=1.0,
        source_unit=source,
        target_unit=target,
        source_ref=clause_ref(source, version_id=None) if source else None,
        target_ref=clause_ref(target, version_id=None) if target else None,
        signals=DiffSignals(
            content_changed=classification is DiffClassification.MODIFIED,
            number_changed=False,
            title_changed=False,
            parent_changed=False,
            position_changed=False,
        ),
    )


def _classify(title: str, old: str, new: str | None = None) -> object:
    body_new = new if new is not None else old
    return classify_clause_diff(
        _diff_row(
            DiffClassification.MODIFIED,
            _unit(old, title=title),
            _unit(body_new, key="CLAUSE:1.1b", title=title),
        )
    )


# ---------------------------------------------------------------------------
# Canonical category matrix (EN)
# ---------------------------------------------------------------------------


def test_financial_contract_price_ac03() -> None:
    row = _classify("Contract Price", "Contract price is USD 500,000.", "Contract price is USD 600,000.")
    assert row.primary_category is RiskCategory.FINANCIAL
    assert row.risk_level == RISK_LEVEL_UNSET


def test_liability_cap_ac02() -> None:
    row = _classify(
        "Limitation of Liability",
        "Liability shall not exceed USD 1,000,000.",
        "Liability shall not exceed USD 500,000.",
    )
    assert row.primary_category is RiskCategory.LIABILITY
    assert row.risk_level == RISK_LEVEL_UNSET


def test_money_does_not_imply_financial_ac16() -> None:
    row = _classify(
        "Limitation of Liability",
        "The cap is 500.000.000 đồng.",
        "The cap is 300.000.000 đồng.",
    )
    assert row.primary_category is RiskCategory.LIABILITY
    assert row.primary_category is not RiskCategory.FINANCIAL


def test_termination_ac06() -> None:
    row = _classify("Termination", "Either party may terminate with 30 days' notice.")
    assert row.primary_category is RiskCategory.TERMINATION


def test_payment_ac04() -> None:
    row = _classify("Payment Schedule", "Payment shall be made within 30 days.")
    assert row.primary_category is RiskCategory.PAYMENT


def test_contract_term_ac05() -> None:
    row = _classify("Term", "The term of this Agreement is 24 months.")
    assert row.primary_category is RiskCategory.CONTRACT_TERM


def test_confidentiality_ac07() -> None:
    row = _classify("Confidentiality", "Confidentiality obligations survive for 5 years.")
    assert row.primary_category is RiskCategory.CONFIDENTIALITY


def test_data_protection_ac08() -> None:
    row = _classify(
        "Data Protection",
        "Personal data breach shall be notified within 72 hours.",
    )
    assert row.primary_category is RiskCategory.DATA_PROTECTION


def test_intellectual_property_ac09() -> None:
    row = _classify(
        "Intellectual Property",
        "All intellectual property in the deliverables belongs to Buyer.",
    )
    assert row.primary_category is RiskCategory.INTELLECTUAL_PROPERTY


def test_warranty_ac10() -> None:
    row = _classify("Warranty", "Warranty period is 24 months.")
    assert row.primary_category is RiskCategory.WARRANTY


def test_dispute_resolution_ac11() -> None:
    row = _classify("Dispute Resolution", "Disputes shall be resolved by arbitration.")
    assert row.primary_category is RiskCategory.DISPUTE_RESOLUTION


def test_penalty_ac12() -> None:
    row = _classify("Penalty", "Late delivery is subject to a penalty of 5%.")
    assert row.primary_category is RiskCategory.PENALTY


def test_sla_ac13() -> None:
    row = _classify("SLA", "Service availability shall be 99.9%.")
    assert row.primary_category is RiskCategory.SLA


def test_governing_law_ac14() -> None:
    row = _classify("Governing Law", "This Agreement is governed by the laws of Vietnam.")
    assert row.primary_category is RiskCategory.GOVERNING_LAW


def test_other_office_ac15() -> None:
    row = _classify("", "Supplier shall maintain an office in Hanoi.")
    assert row.primary_category is RiskCategory.OTHER


# ---------------------------------------------------------------------------
# Vietnamese + rule isolation
# ---------------------------------------------------------------------------


def test_vietnamese_liability_and_payment() -> None:
    liability = _classify(
        "Giới hạn trách nhiệm",
        "Tổng trách nhiệm bồi thường không vượt quá 100% giá trị hợp đồng.",
    )
    payment = _classify("Lịch thanh toán", "Bên A thanh toán 40% trong vòng 05 ngày làm việc.")
    assert liability.primary_category is RiskCategory.LIABILITY
    assert payment.primary_category is RiskCategory.PAYMENT
    assert rules_for(RiskCategory.LIABILITY)


def test_vietnamese_term_termination_dispute() -> None:
    term = _classify("Thời hạn thực hiện", "Thời hạn thực hiện là 12 tháng kể từ ngày ký.")
    end = _classify("Chấm dứt hợp đồng", "Mỗi bên có quyền chấm dứt Hợp đồng.")
    dispute = _classify("Giải quyết tranh chấp", "Mọi tranh chấp được giải quyết bằng trọng tài.")
    assert term.primary_category is RiskCategory.CONTRACT_TERM
    assert end.primary_category is RiskCategory.TERMINATION
    assert dispute.primary_category is RiskCategory.DISPUTE_RESOLUTION


# ---------------------------------------------------------------------------
# Multi-category, confidence vs risk, no advice
# ---------------------------------------------------------------------------


def test_termination_plus_payment_secondary() -> None:
    row = _classify(
        "Termination",
        "Upon termination, all outstanding payments become immediately due.",
    )
    assert row.primary_category is RiskCategory.TERMINATION
    assert RiskCategory.PAYMENT in row.secondary_categories


def test_no_risk_level_or_legal_advice_ac19() -> None:
    row = _classify("Limitation of Liability", "Liability shall not exceed USD 500,000.")
    dumped = row.as_dict()
    assert dumped["risk_level"] == RISK_LEVEL_UNSET
    blob = str(dumped).casefold()
    assert "critical" not in blob
    assert "you should reject" not in blob
    assert "legally dangerous" not in blob
    assert "unfavorable" not in blob
    assert row.classification_confidence in {
        ClassificationConfidence.HIGH,
        ClassificationConfidence.MEDIUM,
        ClassificationConfidence.LOW,
    }


# ---------------------------------------------------------------------------
# False positives
# ---------------------------------------------------------------------------


def test_bare_duration_is_other_ac17() -> None:
    row = _classify("", "30 days")
    assert row.primary_category is RiskCategory.OTHER


def test_agreement_number_is_not_financial() -> None:
    row = _classify("", "Agreement No. 500/2025 is signed by the parties.")
    assert row.primary_category is not RiskCategory.FINANCIAL


def test_uptime_is_sla_not_financial() -> None:
    row = _classify("", "The platform shall maintain 99.9% uptime.")
    assert row.primary_category is RiskCategory.SLA


def test_jurisdiction_is_dispute_not_governing_law_ac18() -> None:
    row = _classify("", "The courts having jurisdiction over the parties shall hear the case.")
    assert row.primary_category is RiskCategory.DISPUTE_RESOLUTION
    assert row.primary_category is not RiskCategory.GOVERNING_LAW


def test_terminate_is_not_contract_term() -> None:
    row = _classify("", "The buyer may terminate within 30 days.")
    assert row.primary_category is RiskCategory.TERMINATION
    assert row.primary_category is not RiskCategory.CONTRACT_TERM


def test_warrants_that_payment_is_not_warranty() -> None:
    row = _classify("", "Supplier warrants that payment shall be made within 30 days.")
    assert row.primary_category is RiskCategory.PAYMENT
    assert row.primary_category is not RiskCategory.WARRANTY


# ---------------------------------------------------------------------------
# Pipeline / skip / determinism
# ---------------------------------------------------------------------------


def test_unchanged_clause_is_skipped() -> None:
    result = classify_taxonomy(
        DiffResult(
            source_document_id=uuid4(),
            target_document_id=uuid4(),
            source_version_id=None,
            target_version_id=None,
            diffs=[
                _diff_row(
                    DiffClassification.UNCHANGED,
                    _unit("500.000.000 đồng", title="Price"),
                    _unit("500.000.000 đồng", title="Price"),
                )
            ],
        )
    )
    assert result.assignments == []
    assert result.metadata["taxonomy_llm_calls"] == 0


def test_evidence_refs_preserved_ac22() -> None:
    source = _unit("Liability shall not exceed USD 1,000,000.", title="Limitation of Liability")
    target = _unit(
        "Liability shall not exceed USD 500,000.",
        key="CLAUSE:8.2",
        title="Limitation of Liability",
    )
    item = _diff_row(DiffClassification.MODIFIED, source, target)
    row = classify_clause_diff(item)
    assert row.source_ref is not None and row.source_ref.identity_key == "CLAUSE:1.1"
    assert row.target_ref is not None and row.target_ref.page_start == 1


def test_determinism_ac21() -> None:
    first = _classify("Payment Schedule", "Payment shall be made within 30 days.")
    second = _classify("Payment Schedule", "Payment shall be made within 30 days.")
    assert first.as_dict()["primary_category"] == second.as_dict()["primary_category"]
    assert first.as_dict()["rule_id"] == second.as_dict()["rule_id"]
    assert first.as_dict()["taxonomy_version"] == second.as_dict()["taxonomy_version"]


def test_pipeline_liability_money_stays_liability() -> None:
    v1 = _norm("ĐIỀU 8. GIỚI HẠN TRÁCH NHIỆM\n8.2. Tổng trách nhiệm bồi thường không vượt quá 500.000.000 đồng.\n")
    v2 = _norm("ĐIỀU 8. GIỚI HẠN TRÁCH NHIỆM\n8.2. Tổng trách nhiệm bồi thường không vượt quá 300.000.000 đồng.\n")
    result = LegalRiskTaxonomyEngine().classify_structures(v1, v2)
    row = result.for_source("CLAUSE:8.2")
    assert row is not None
    assert row.primary_category is RiskCategory.LIABILITY
    assert ValueType.MONEY in row.value_types or not row.value_types
    assert result.metadata["taxonomy_llm_calls"] == 0
    assert row.classification_method is ClassificationMethod.RULE


def test_v1_v2_regression_key_clauses() -> None:
    v1 = normalize_structure(extract_from_pages(_pages(V1_TXT), title="V1"))
    v2 = normalize_structure(extract_from_pages(_pages(V2_TXT), title="V2"))
    diff = diff_normalized_structures(v1, v2)
    exact = extract_exact_differences(diff)
    result = classify_taxonomy(diff, exact)
    assert result.for_source("CLAUSE:1.2") is None
    assert result.for_source("CLAUSE:1.3") is None
    assert result.for_source("CLAUSE:2.1") and (
        result.for_source("CLAUSE:2.1").primary_category is RiskCategory.CONTRACT_TERM
    )
    assert result.for_source("CLAUSE:3.1") and (
        result.for_source("CLAUSE:3.1").primary_category is RiskCategory.FINANCIAL
    )
    assert result.for_source("CLAUSE:3.2") and (
        result.for_source("CLAUSE:3.2").primary_category is RiskCategory.PAYMENT
    )
    assert result.for_source("CLAUSE:8.2") and (
        result.for_source("CLAUSE:8.2").primary_category is RiskCategory.LIABILITY
    )
    term = result.for_source("CLAUSE:9.1")
    assert term and term.primary_category is RiskCategory.TERMINATION
    added = result.for_target("CLAUSE:9.3")
    assert added and added.primary_category is RiskCategory.TERMINATION
    assert RiskCategory.PAYMENT in added.secondary_categories
    price = result.for_source("CLAUSE:3.3")
    assert price and price.primary_category is RiskCategory.FINANCIAL
    dispute = result.for_source("CLAUSE:11.2")
    assert dispute and dispute.primary_category is RiskCategory.DISPUTE_RESOLUTION
    assert result.metadata["taxonomy_llm_calls"] == 0
    assert result.taxonomy_version == "v1"
