# =============================================================================
# File: service.py
# Module/Service: Observability Module — System Health (FR13)
# Layer: Service
# Purpose: Orchestrate dependency probes and compute overall SystemHealth.
# Responsibilities:
#   - Run all health adapters concurrently
#   - Authoritative overall status from critical / degraded / unhealthy
# Dependencies:
#   - checkers.run_all_probes, Settings, AsyncSession, SystemHealthResponse
# Public Exports:
#   - SystemHealthService
# Database/Table: N/A
# Related Modules: app.api.admin_health, OpenAPI SystemHealth
# Important Notes: Overall status is computed in the service — not the frontend.
# =============================================================================

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.schemas.admin import (
    HealthServiceItem,
    HealthStatusLiteral,
    SystemHealthResponse,
)
from app.services.health.checkers import ProbeResult, run_all_probes

_OVERALL_MESSAGES: dict[HealthStatusLiteral, str] = {
    "healthy": "All monitored dependencies are responding normally.",
    "degraded": (
        "Most services are operational, but some dependencies "
        "are experiencing reduced availability."
    ),
    "unhealthy": "One or more critical dependencies are unavailable.",
    "unknown": "Health information is currently incomplete.",
}


def compute_overall_status(services: list[ProbeResult]) -> HealthStatusLiteral:
    """Authoritative rollup — critical unhealthy → unhealthy."""
    if not services:
        return "unknown"

    statuses = {s.status for s in services}
    critical_unhealthy = any(
        s.critical and s.status == "unhealthy" for s in services
    )
    if critical_unhealthy:
        return "unhealthy"
    if "unhealthy" in statuses:
        # Non-critical unhealthy → degraded (system still usable)
        return "degraded"
    if "degraded" in statuses:
        return "degraded"
    if statuses == {"healthy"}:
        return "healthy"
    if "unknown" in statuses and statuses.issubset({"healthy", "unknown"}):
        # Partial unknown without failures → unknown overall
        return "unknown"
    if "healthy" in statuses:
        return "degraded"
    return "unknown"


class SystemHealthService:
    """Build ``SystemHealthResponse`` for Platform Manage."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def get_health(self) -> SystemHealthResponse:
        checked_at = datetime.now(UTC)
        probes = await run_all_probes(session=self._session, settings=self._settings)
        overall = compute_overall_status(probes)
        services = [
            HealthServiceItem(
                id=p.id,
                name=p.name,
                category=p.category,
                status=p.status,
                provider=p.provider,
                message=p.message,
                checked_at=p.checked_at,
                response_time_ms=p.response_time_ms,
                critical=p.critical,
            )
            for p in probes
        ]
        return SystemHealthResponse(
            status=overall,
            checked_at=checked_at,
            message=_OVERALL_MESSAGES[overall],
            services=services,
        )
