# =============================================================================
# File: __init__.py
# Module/Service: Repositories
# Layer: Repository
# Purpose: Package marker for SQLAlchemy data-access modules.
# Responsibilities:
#   - Hold one repository per table/group (no business rules)
# Dependencies:
#   - SQLAlchemy, app.models
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.services
# Important Notes: Multi-tenant queries must filter by workspace_id where applicable.
# =============================================================================
