# =============================================================================
# File: test_health.py
# Module/Service: Backend API System
# Layer: Presentation
# Purpose: Smoke tests for health/readiness endpoints.
# Responsibilities:
#   - Verify /health and /ready respond with 200 in the skeleton app
# Dependencies:
#   - pytest, httpx, FastAPI TestClient / ASGITransport
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.main
# Important Notes: Phase 1.1 CI smoke coverage only.
# =============================================================================

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
