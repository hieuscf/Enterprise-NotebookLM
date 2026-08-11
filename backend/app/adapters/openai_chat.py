# =============================================================================
# File: openai_chat.py
# Module/Service: Chat Service (FR4)
# Layer: Adapter
# Purpose: OpenAI Chat Completions client for structured JSON (chat answer / rewrite).
# Responsibilities:
#   - Call OpenAI-compatible /chat/completions with JSON object response
#   - Return StructuredLlmResult (same shape as Anthropic adapter)
#   - Detect empty-completion responses (reasoning-token budget exhaustion)
#     and raise a classified error instead of a generic JSON parse failure
# Dependencies:
#   - httpx, app.adapters.llm_result
# Public Exports:
#   - extract_structured_json, extract_structured_json_async
# Database/Table: N/A
# Related Modules: app.adapters.chat_llm, answer_generator, rewrite_agent
# Important Notes:
#   - Chat path only (embedding stays on EMBEDDING_* / OpenAI embeddings API).
#   - gpt-5 / o-series prefer max_completion_tokens over max_tokens.
#   - gpt-5 / o-series are reasoning models: with response_format=json_object
#     and a modest max_completion_tokens budget, the *default* ("medium")
#     reasoning effort can consume the entire budget on hidden reasoning
#     tokens and return HTTP 200 with an EMPTY message.content
#     (finish_reason="length"). We default reasoning_effort to "minimal" for
#     these structured-extraction calls (configurable via
#     OPENAI_REASONING_EFFORT) so the visible-answer budget is not starved.
# =============================================================================

from __future__ import annotations

from typing import Any

import httpx

from app.adapters.llm_result import EmptyCompletionError, StructuredLlmResult, parse_json_object

# Rough default rates for observability when caller omits cost_estimator.
_DEFAULT_INPUT_USD_PER_MTOK = 2.5
_DEFAULT_OUTPUT_USD_PER_MTOK = 10.0


def _uses_max_completion_tokens(model: str) -> bool:
    m = (model or "").strip().lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


def _build_body(
    *,
    system: str,
    user: str,
    model: str,
    max_tokens: int,
    temperature: float,
    top_p: float,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    if _uses_max_completion_tokens(model):
        body["max_completion_tokens"] = max_tokens
        # Reasoning-tier model: keep reasoning effort low so the completion
        # budget above is spent on the visible JSON answer, not hidden
        # reasoning tokens (see module docstring — root cause of empty
        # `message.content` with finish_reason="length").
        if reasoning_effort:
            body["reasoning_effort"] = reasoning_effort
    else:
        body["max_tokens"] = max_tokens
        body["temperature"] = temperature
        body["top_p"] = top_p
    return body


def _result_from_response(
    body: dict[str, Any],
    *,
    model: str,
    cost_estimator: Any | None,
) -> StructuredLlmResult:
    choices = body.get("choices") or []
    raw_text = ""
    finish_reason: str | None = None
    if choices:
        choice = choices[0] or {}
        finish_reason = choice.get("finish_reason")
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            raw_text = content
        elif isinstance(content, list):
            raw_text = "\n".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("type") in (None, "text")
            )
    usage = body.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(
        usage.get("completion_tokens") or usage.get("output_tokens") or 0
    )
    resolved_model = str(body.get("model") or model)
    if not raw_text.strip():
        # HTTP 200 with no visible text — classify explicitly rather than
        # letting a bare JSONDecodeError obscure the real cause downstream.
        raise EmptyCompletionError(
            model=resolved_model,
            finish_reason=finish_reason,
            output_tokens=output_tokens,
        )
    data = parse_json_object(raw_text)
    if callable(cost_estimator):
        estimated = float(
            cost_estimator(input_tokens=input_tokens, output_tokens=output_tokens)
        )
    else:
        estimated = (
            input_tokens * _DEFAULT_INPUT_USD_PER_MTOK
            + output_tokens * _DEFAULT_OUTPUT_USD_PER_MTOK
        ) / 1_000_000
    return StructuredLlmResult(
        data=data,
        model=resolved_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated,
        finish_reason=finish_reason,
    )


def extract_structured_json(
    *,
    system: str,
    user: str,
    model: str,
    api_key: str,
    api_base: str = "https://api.openai.com/v1",
    max_tokens: int = 4096,
    timeout_seconds: float = 120.0,
    temperature: float = 0.0,
    top_p: float = 1.0,
    reasoning_effort: str | None = "minimal",
    cost_estimator: Any | None = None,
) -> StructuredLlmResult:
    """Sync OpenAI chat completion returning a parsed JSON object.

    Raises:
        EmptyCompletionError: Provider returned HTTP 200 with no visible text
            (reasoning-tier model exhausted its token budget on reasoning).
        ValueError: Visible text was present but not valid JSON.
        httpx.HTTPStatusError: Non-2xx provider response (auth/model/rate-limit).
    """
    with httpx.Client(timeout=timeout_seconds) as client:
        resp = client.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json=_build_body(
                system=system,
                user=user,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                reasoning_effort=reasoning_effort,
            ),
        )
        resp.raise_for_status()
        body = resp.json()
    return _result_from_response(body, model=model, cost_estimator=cost_estimator)


async def extract_structured_json_async(
    *,
    system: str,
    user: str,
    model: str,
    api_key: str,
    api_base: str = "https://api.openai.com/v1",
    max_tokens: int = 4096,
    temperature: float = 0.0,
    top_p: float = 1.0,
    timeout_seconds: float = 120.0,
    reasoning_effort: str | None = "minimal",
    cost_estimator: Any | None = None,
) -> StructuredLlmResult:
    """Async OpenAI chat completion returning a parsed JSON object (Chat FR4).

    Raises:
        EmptyCompletionError: Provider returned HTTP 200 with no visible text
            (reasoning-tier model exhausted its token budget on reasoning).
        ValueError: Visible text was present but not valid JSON.
        httpx.HTTPStatusError: Non-2xx provider response (auth/model/rate-limit).
    """
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.post(
            f"{api_base.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json=_build_body(
                system=system,
                user=user,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                reasoning_effort=reasoning_effort,
            ),
        )
        resp.raise_for_status()
        body = resp.json()
    return _result_from_response(body, model=model, cost_estimator=cost_estimator)
