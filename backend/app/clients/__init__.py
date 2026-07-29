# =============================================================================
# File: __init__.py
# Module/Service: Pipeline Worker — HTTP Clients
# Layer: Adapter
# Purpose: Package marker for outbound API clients used by Celery workers.
# Responsibilities:
#   - Host parser and provider HTTP clients isolated from domain services
# Dependencies:
#   - N/A
# Public Exports:
#   - N/A (import submodules explicitly)
# Database/Table: N/A
# Related Modules: app.clients.llamaparse_client, app.clients.retry_policy
# Important Notes: Not for LLM Provider traffic — see graph extraction adapters.
# =============================================================================
