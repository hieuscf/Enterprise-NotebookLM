# =============================================================================
# File: ground_truth.py
# Module/Service: Contract Comparison Quality Evaluation (FR8 / TASK-CMP-16)
# Layer: Test fixture
# Purpose: Load structured expected-clause labels for evaluation tests.
# Public Exports:
#   - load_expected_clauses, v1_v2_expected_clauses
# Important Notes: Labels are test-only. Not imported by production engines.
# =============================================================================

from __future__ import annotations

import json
from pathlib import Path

from app.ai.document_structure.evaluation_types import ExpectedClause

_DIR = Path(__file__).parent


def load_expected_clauses(path: Path | None = None) -> tuple[str, list[ExpectedClause]]:
    target = path or (_DIR / "v1_v2_regression.json")
    payload = json.loads(target.read_text(encoding="utf-8"))
    rows: list[ExpectedClause] = []
    for item in payload.get("clauses", []):
        rows.append(
            ExpectedClause(
                identity_key=str(item["identity_key"]),
                status=item.get("status"),
                forbidden_statuses=tuple(item.get("forbidden_statuses") or ()),
                mapped_v2_key=item.get("mapped_v2_key"),
                risk_category=item.get("risk_category"),
                risk_level_in=tuple(item.get("risk_level_in") or ()),
                exact_value_types=tuple(item.get("exact_value_types") or ()),
                require_citations=bool(item.get("require_citations") or False),
                v1_clause_id=item["v1_clause_id"] if item.get("v1_clause_id") else None,
                v2_clause_id=item["v2_clause_id"] if item.get("v2_clause_id") else None,
                require_null_v1="v1_clause_id" in item and item.get("v1_clause_id") is None,
                require_null_v2="v2_clause_id" in item and item.get("v2_clause_id") is None,
                use_subtree=bool(item.get("use_subtree") or False),
            )
        )
    return str(payload.get("case_id") or target.stem), rows


def v1_v2_expected_clauses() -> tuple[str, list[ExpectedClause]]:
    return load_expected_clauses()
