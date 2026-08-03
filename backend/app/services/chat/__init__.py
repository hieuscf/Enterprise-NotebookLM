# =============================================================================
# File: __init__.py
# Module/Service: Chat Service
# Layer: Service
# Purpose: Package marker for Chat / Complex Query / agent-events services.
# Responsibilities:
#   - Export ComplexQueryPipeline and AgentEventsService
# Dependencies:
#   - complex_query_pipeline, agent_events_service
# Public Exports:
#   - ComplexQueryPipeline, AgentEventsService
# Database/Table: N/A
# Related Modules: QueryOrchestrator, app.api.chat
# Important Notes: FR14 complex path only; cache/metadata/factoid stay in Router.
# =============================================================================

from app.services.chat.agent_events_service import AgentEventsService
from app.services.chat.complex_query_pipeline import ComplexQueryPipeline

__all__ = ["AgentEventsService", "ComplexQueryPipeline"]
