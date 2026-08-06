# =============================================================================
# File: __init__.py
# Module/Service: Chat Service
# Layer: Service
# Purpose: Package marker for Chat / Complex Query / agent-events services.
# Responsibilities:
#   - Export Conversation Memory, ComplexQueryPipeline, AgentEventsService
# Dependencies:
#   - session_service, complex_query_pipeline, agent_events_service
# Public Exports:
#   - ChatSessionService, ChatServiceError
#   - ComplexQueryPipeline, AgentEventsService
# Database/Table: N/A
# Related Modules: QueryOrchestrator, app.api.chat
# Important Notes: FR14 complex path only; cache/metadata/factoid stay in Router.
# =============================================================================

from app.services.chat.agent_events_service import AgentEventsService
from app.services.chat.answer_generator import PromptAnswerGenerator
from app.services.chat.complex_query_pipeline import ComplexQueryPipeline
from app.services.chat.message_service import MessageProcessingService
from app.services.chat.session_service import ChatServiceError, ChatSessionService

__all__ = [
    "AgentEventsService",
    "ChatServiceError",
    "ChatSessionService",
    "ComplexQueryPipeline",
    "MessageProcessingService",
    "PromptAnswerGenerator",
]
