# =============================================================================
# File: middleware.py
# Module/Service: Observability Module / API Gateway
# Layer: Presentation
# Purpose: FastAPI middleware for per-request JSON access logging.
# Responsibilities:
#   - Assign/propagate request_id; capture workspace_id when present
#   - Log method, route, status_code, latency_ms after each response
# Dependencies:
#   - FastAPI/Starlette, structlog, app.core.logging
# Public Exports:
#   - RequestLoggingMiddleware, extract_workspace_id
# Database/Table: N/A
# Related Modules: app.main, app.core.logging
# Important Notes: Foundation only — no persistence to query_logs tables.
# =============================================================================

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.logging import bind_log_context, clear_log_context, get_logger

logger = get_logger(__name__)

_WORKSPACE_PATH_RE = re.compile(
    r"^/workspaces/(?P<workspace_id>[0-9a-fA-F-]{36})(?:/|$)",
)


def extract_workspace_id(request: Request) -> str | None:
    """Resolve workspace_id from path `/workspaces/{uuid}/...` or X-Workspace-Id."""
    header_value = request.headers.get("x-workspace-id")
    if header_value:
        return header_value.strip() or None

    match = _WORKSPACE_PATH_RE.match(request.url.path)
    if match:
        return match.group("workspace_id")
    return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log each HTTP request/response with request_id, route, latency_ms."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        clear_log_context()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        workspace_id = extract_workspace_id(request)

        bind_log_context(
            request_id=request_id,
            workspace_id=workspace_id,
            method=request.method,
            path=request.url.path,
        )

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            latency_ms = int((time.perf_counter() - started) * 1000)
            route = _resolve_route(request)
            logger.exception(
                "http_request_failed",
                route=route,
                latency_ms=latency_ms,
                status_code=status_code,
            )
            clear_log_context()
            raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        route = _resolve_route(request)
        bind_log_context(route=route, latency_ms=latency_ms, status_code=status_code)

        logger.info(
            "http_request",
            route=route,
            latency_ms=latency_ms,
            status_code=status_code,
            request_id=request_id,
            workspace_id=workspace_id,
            method=request.method,
        )

        response.headers["X-Request-ID"] = request_id
        clear_log_context()
        return response


def _resolve_route(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path
