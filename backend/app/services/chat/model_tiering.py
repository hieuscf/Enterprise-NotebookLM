# =============================================================================
# File: model_tiering.py
# Module/Service: Chat Service / Prompt Construction (FR4, FR11)
# Layer: Service
# Purpose: Select answer LLM model from Settings (no hardcoded model ids).
# Responsibilities:
#   - Light vs strong model; optional force-strong when agent_triggered
# Dependencies:
#   - app.core.config.Settings
# Public Exports:
#   - select_answer_model, estimate_answer_cost_usd
# Database/Table: N/A
# Related Modules: answer_generator, ComplexQueryPipeline
# Important Notes: All thresholds/flags come from Settings — never if "sonnet" in code.
# =============================================================================

from __future__ import annotations

from app.core.config import Settings


def select_answer_model(
    settings: Settings,
    *,
    agent_triggered: bool = False,
    prefer_strong: bool = False,
) -> str:
    """Pick the configured answer model for one complex-query LLM call.

    Rules (config-driven):
      - Default: ``chat_answer_light_model``
      - ``prefer_strong`` (complex reasoning hint): ``chat_answer_strong_model``
      - When ``agent_triggered`` and ``chat_agent_force_strong_model``: strong model
    """
    use_strong = bool(prefer_strong)
    if agent_triggered and bool(settings.chat_agent_force_strong_model):
        use_strong = True
    if use_strong:
        return str(settings.chat_answer_strong_model)
    return str(settings.chat_answer_light_model)


def estimate_answer_cost_usd(
    settings: Settings,
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate USD cost from configured per-model rates."""
    strong = str(settings.chat_answer_strong_model)
    if model == strong:
        in_rate = float(settings.chat_answer_strong_input_usd_per_mtok)
        out_rate = float(settings.chat_answer_strong_output_usd_per_mtok)
    else:
        in_rate = float(settings.chat_answer_light_input_usd_per_mtok)
        out_rate = float(settings.chat_answer_light_output_usd_per_mtok)
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
