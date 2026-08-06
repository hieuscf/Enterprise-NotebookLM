# =============================================================================
# File: anthropic_client.py
# Module/Service: Document Ingestion / LightRAG Graph Extraction
# Layer: Adapter
# Purpose: Anthropic Messages API client for structured JSON extraction (FR2 Step 5).
# Responsibilities:
#   - Call Claude with JSON-only response; return parsed object + usage/cost
# Dependencies:
#   - httpx, app.core.config
# Public Exports:
#   - AnthropicExtractionResult, extract_structured_json, extract_structured_json_async
# Database/Table: N/A
# Related Modules: app.ai.lightrag_extraction, app.services.chat.answer_generator
# Important Notes:
#   - Graph extraction (worker) and Chat answer (backend-api) share this adapter.
#   - Chat answer path uses extract_structured_json_async (exactly 1 call / complex).
# =============================================================================

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

# Approximate public Haiku pricing (USD / 1M tokens) — for metadata estimates only.
_HAIKU_INPUT_USD_PER_MTTOK = 0.25
_HAIKU_OUTPUT_USD_PER_MTTOK = 1.25


@dataclass(frozen=True, slots=True)
class AnthropicExtractionResult:
    """Structured LLM response plus billing metadata."""

    data: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


def estimate_haiku_cost_usd(*, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for Haiku-class usage (observability only)."""
    return (
        input_tokens * _HAIKU_INPUT_USD_PER_MTTOK
        + output_tokens * _HAIKU_OUTPUT_USD_PER_MTTOK
    ) / 1_000_000


def extract_structured_json(
    *,
    system: str,
    user: str,
    model: str,
    api_key: str,
    api_base: str = "https://api.anthropic.com",
    max_tokens: int = 4096,
    timeout_seconds: float = 120.0,
) -> AnthropicExtractionResult:
    """Call Anthropic Messages API and parse a JSON object from the assistant text.

    Args:
        system: System prompt (extraction schema instructions).
        user: User content (chunk corpus).
        model: e.g. ``claude-3-5-haiku-latest``.
        api_key: Anthropic API key.
        api_base: API host (override for enterprise proxy / backend-api gateway).
        max_tokens: Generation cap.
        timeout_seconds: HTTP timeout.

    Returns:
        Parsed JSON object plus token usage and estimated USD cost.

    Raises:
        httpx.HTTPError: Transport / HTTP failures.
        ValueError: Empty or non-JSON model output.
    """
    with httpx.Client(timeout=timeout_seconds) as client:
        resp = client.post(
            f"{api_base.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        body = resp.json()

    text_parts = [
        block.get("text", "")
        for block in body.get("content", [])
        if block.get("type") == "text"
    ]
    raw_text = "\n".join(text_parts).strip()
    data = _parse_json_object(raw_text)
    usage = body.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    return AnthropicExtractionResult(
        data=data,
        model=str(body.get("model") or model),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimate_haiku_cost_usd(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


async def extract_structured_json_async(
    *,
    system: str,
    user: str,
    model: str,
    api_key: str,
    api_base: str = "https://api.anthropic.com",
    max_tokens: int = 4096,
    temperature: float = 0.0,
    top_p: float = 1.0,
    timeout_seconds: float = 120.0,
    cost_estimator: Any | None = None,
) -> AnthropicExtractionResult:
    """Async Anthropic Messages call returning a parsed JSON object (Chat FR4)."""
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.post(
            f"{api_base.rstrip('/')}/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        body = resp.json()

    text_parts = [
        block.get("text", "")
        for block in body.get("content", [])
        if block.get("type") == "text"
    ]
    raw_text = "\n".join(text_parts).strip()
    data = _parse_json_object(raw_text)
    usage = body.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    if callable(cost_estimator):
        estimated = float(
            cost_estimator(input_tokens=input_tokens, output_tokens=output_tokens)
        )
    else:
        estimated = estimate_haiku_cost_usd(
            input_tokens=input_tokens, output_tokens=output_tokens
        )
    return AnthropicExtractionResult(
        data=data,
        model=str(body.get("model") or model),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated,
    )


def _parse_json_object(text: str) -> dict[str, Any]:
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
