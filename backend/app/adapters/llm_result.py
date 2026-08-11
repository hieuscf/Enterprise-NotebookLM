# =============================================================================
# File: llm_result.py
# Module/Service: Chat Service / LLM adapters
# Layer: Adapter
# Purpose: Shared structured-LLM result type + JSON object parser.
# Responsibilities:
#   - Normalize provider responses into StructuredLlmResult
#   - Parse JSON object from model text (fenced or raw)
#   - Classify empty-completion provider responses (e.g. reasoning-token
#     budget exhaustion) distinctly from generic malformed-JSON output
# Dependencies:
#   - json, re
# Public Exports:
#   - StructuredLlmResult, parse_json_object, EmptyCompletionError
# Database/Table: N/A
# Related Modules: anthropic_client, openai_chat, chat_llm
# Important Notes: Used by chat answer + rewrite; graph extraction may keep
#   AnthropicExtractionResult alias for backward compatibility.
# =============================================================================

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StructuredLlmResult:
    """Structured LLM response plus billing metadata."""

    data: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    # Provider finish/stop reason (e.g. "stop" | "length"); None when unknown.
    finish_reason: str | None = None


class EmptyCompletionError(RuntimeError):
    """Provider returned HTTP 200 but with no visible completion text.

    Typical cause: a reasoning-tier model (gpt-5 / o1 / o3 / o4) consumed its
    entire ``max_completion_tokens`` budget on hidden reasoning tokens before
    emitting any visible output (``finish_reason == "length"`` with an empty
    message). Must never be silently coerced into ``answer = ""``; callers
    should log this distinctly from a generic JSON parse failure.
    """

    def __init__(self, *, model: str, finish_reason: str | None, output_tokens: int) -> None:
        self.model = model
        self.finish_reason = finish_reason
        self.output_tokens = output_tokens
        super().__init__(
            f"empty_completion model={model} finish_reason={finish_reason} "
            f"output_tokens={output_tokens}"
        )


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from model text (allows fenced ```json blocks)."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("LLM output JSON must be an object")
    return data
