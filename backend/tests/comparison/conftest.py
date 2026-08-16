# =============================================================================
# File: conftest.py
# Module/Service: Comparison Service (TASK-CMP-28)
# Layer: Test
# Purpose: Shared V1/V2 fixtures for the comparison regression suite.
# Responsibilities:
#   - Resolve contract fixtures without absolute hardcoded paths
#   - Build normalized structures and a deterministic comparison report
# Dependencies:
#   - pytest, ContractComparisonOrchestrator, extract/normalize pipeline
# Public Exports:
#   - fixtures: contract_dir, v1_txt, v2_txt, v1_pdf, v2_pdf,
#     v1_structure, v2_structure, v1_v2_report, compare_v1_v2
# Database/Table: N/A
# Related Modules: tests/fixtures/contracts/Hop_dong_mau_Ra_soat_Phap_ly_V*
# Important Notes: Default path uses .txt page fixtures (deterministic, 0 LLM).
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from app.ai.document_structure.normalization import (
    NormalizedDocumentStructure,
    normalize_structure,
)
from app.ai.document_structure.pipeline import extract_from_pages
from app.ai.document_structure.report_types import AuditableComparisonReport
from app.services.document_structure.orchestrator import ContractComparisonOrchestrator

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


def pages_from_txt(path: Path) -> list[tuple[int, str]]:
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


def normalize_contract(path: Path, *, title: str) -> NormalizedDocumentStructure:
    return normalize_structure(extract_from_pages(pages_from_txt(path), title=title))


@pytest.fixture(scope="session")
def contract_dir() -> Path:
    return CONTRACT_DIR


@pytest.fixture(scope="session")
def v1_txt(contract_dir: Path) -> Path:
    path = contract_dir / "Hop_dong_mau_Ra_soat_Phap_ly_V1.txt"
    assert path.is_file(), path
    return path


@pytest.fixture(scope="session")
def v2_txt(contract_dir: Path) -> Path:
    path = contract_dir / "Hop_dong_mau_Ra_soat_Phap_ly_V2.txt"
    assert path.is_file(), path
    return path


@pytest.fixture(scope="session")
def v1_pdf(contract_dir: Path) -> Path:
    path = contract_dir / "Hop_dong_mau_Ra_soat_Phap_ly_V1.pdf"
    assert path.is_file(), path
    return path


@pytest.fixture(scope="session")
def v2_pdf(contract_dir: Path) -> Path:
    path = contract_dir / "Hop_dong_mau_Ra_soat_Phap_ly_V2.pdf"
    assert path.is_file(), path
    return path


@pytest.fixture
def v1_structure(v1_txt: Path) -> NormalizedDocumentStructure:
    return normalize_contract(v1_txt, title="Hop dong V1")


@pytest.fixture
def v2_structure(v2_txt: Path) -> NormalizedDocumentStructure:
    return normalize_contract(v2_txt, title="Hop dong V2")


@pytest.fixture
def compare_v1_v2(
    v1_txt: Path,
    v2_txt: Path,
) -> Callable[..., AuditableComparisonReport]:
    def _run(**kwargs) -> AuditableComparisonReport:
        source = normalize_contract(v1_txt, title="Hop dong V1")
        target = normalize_contract(v2_txt, title="Hop dong V2")
        return ContractComparisonOrchestrator().compare_structures(source, target, **kwargs)

    return _run


@pytest.fixture
def v1_v2_report(
    v1_structure: NormalizedDocumentStructure,
    v2_structure: NormalizedDocumentStructure,
) -> AuditableComparisonReport:
    return ContractComparisonOrchestrator().compare_structures(
        v1_structure,
        v2_structure,
    )
