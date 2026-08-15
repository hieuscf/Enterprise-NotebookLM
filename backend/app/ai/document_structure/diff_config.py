# =============================================================================
# File: diff_config.py
# Module/Service: Clause Diff Engine (FR8 / TASK-CMP-04)
# Layer: Service
# Purpose: Single configurable knob set for clause-level diff.
# Responsibilities:
#   - Toggle hash short-circuit, token/sentence diffs, moved-span detection
# Dependencies:
#   - stdlib dataclasses
# Public Exports:
#   - DiffConfig
# Database/Table: N/A
# Related Modules: diff_engine, diff_text
# Important Notes: Do not scatter comparison flags in call sites — pass this object.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiffConfig:
    """Testable diff knobs. Classification rules stay deterministic."""

    use_content_hash: bool = True
    compute_token_diff: bool = True
    compute_sentence_diff: bool = True
    detect_moved_spans: bool = True
    max_change_snippet_tokens: int = 32
