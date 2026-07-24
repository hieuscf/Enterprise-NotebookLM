# =============================================================================
# File: test_observability.py
# Module/Service: Observability Module
# Layer: Presentation
# Purpose: Smoke tests for request logging middleware and health under OTel.
# Responsibilities:
#   - Ensure /health still works with middleware + tracing wired
#   - Ensure X-Request-ID is returned on responses
# Dependencies:
#   - pytest, httpx, app.main
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.core.middleware, app.main
# Important Notes: Does not assert OTLP export (collector optional).
# =============================================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_sets_request_id_header() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"]


@pytest.mark.asyncio
async def test_health_propagates_request_id() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "test-req-123"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-req-123"
