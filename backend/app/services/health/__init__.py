# =============================================================================
# File: __init__.py
# Module/Service: Observability Module — System Health (FR13)
# Layer: Service
# Purpose: Package export for admin system health.
# Responsibilities:
#   - Re-export SystemHealthService
# Dependencies:
#   - app.services.health.service
# Public Exports:
#   - SystemHealthService
# Database/Table: N/A
# Related Modules: app.api.admin_health
# Important Notes: Health is availability-only — not performance or cost.
# =============================================================================

from app.services.health.service import SystemHealthService

__all__ = ["SystemHealthService"]
