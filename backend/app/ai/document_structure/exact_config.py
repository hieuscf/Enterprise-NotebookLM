# =============================================================================
# File: exact_config.py
# Module/Service: Exact Difference Detection (FR8 / TASK-CMP-06)
# Layer: Service
# Purpose: Central knobs for deterministic value extraction and alignment.
# Responsibilities:
#   - Date locale, Decimal precision, context window, feature flags
# Dependencies:
#   - stdlib dataclasses
# Public Exports:
#   - ExactDiffConfig
# Database/Table: N/A
# Related Modules: exact_engine, exact_parse
# Important Notes: Do not scatter parser constants in call sites.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExactDiffConfig:
    """Testable exact-diff knobs. Classification stays deterministic."""

    date_locale: str = "VN"
    money_precision: int = 4
    percent_precision: int = 6
    relative_precision: int = 4
    context_chars: int = 48
    min_alignment_score: float = 0.28
    include_format_only: bool = False
    include_unchanged_values: bool = False
    year_to_months: int = 12
