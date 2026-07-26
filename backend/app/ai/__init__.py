# =============================================================================
# File: __init__.py
# Module/Service: LightRAG / Document Pipeline (AI track)
# Layer: Service
# Purpose: Package boundary for AI stage processors (OCR→Graph→Topics).
# Responsibilities:
#   - Host pure processing modules callable from Celery Pipeline Worker
# Dependencies:
#   - Format parsers, local embedding — NOT Anthropic (Celery must not call LLM)
# Public Exports:
#   - N/A (import from submodules)
# Database/Table: N/A
# Related Modules: app.workers.pipeline
# Important Notes: Keep [AI] code here so [BE] orchestration can swap engines later.
# =============================================================================
