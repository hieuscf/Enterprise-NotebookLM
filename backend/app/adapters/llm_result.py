# =============================================================================
# File: llm_result.py
# Module/Service: Chat Service / LLM adapters
# Layer: Adapter
# Purpose: Shared structured-LLM result type + JSON object parser.
# Responsibilities:
#   - Normalize provider responses into StructuredLlmResult
#   - Parse JSON object from model text (fenced or raw)
# Dependencies:
#   - json, re
# Public Exports:
#   - StructuredLlmResult, parse_json_object
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
