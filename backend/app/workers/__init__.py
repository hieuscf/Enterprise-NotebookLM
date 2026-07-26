# =============================================================================
# File: __init__.py
# Module/Service: Pipeline Worker
# Layer: Worker
# Purpose: Package marker for Celery document pipeline tasks (FR2).
# Responsibilities:
#   - Host run_pipeline orchestration; stages live under app.workers.stages
# Dependencies:
#   - Celery, Redis, app.workers.stages
# Public Exports:
#   - N/A
# Database/Table: pipeline_runs, pipeline_stage_logs
# Related Modules: Document Ingestion Service (FR2, FR13)
# Important Notes: Workers must NOT call LLM Provider (Anthropic).
# =============================================================================
