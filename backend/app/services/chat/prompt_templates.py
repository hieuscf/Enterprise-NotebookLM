# =============================================================================
# File: prompt_templates.py
# Module/Service: Chat Service / Prompt Construction (FR4)
# Layer: Service
# Purpose: Answer-generation system prompt template (not hardcoded in builder).
# Responsibilities:
#   - Export ANSWER_SYSTEM_PROMPT for structured {answer, citation_ids}
# Dependencies:
#   - N/A
# Public Exports:
#   - ANSWER_SYSTEM_PROMPT
# Database/Table: N/A
# Related Modules: prompt_builder
# Important Notes: Keep citations grounded; refuse when context insufficient.
# =============================================================================

ANSWER_SYSTEM_PROMPT = """\
You are Enterprise NotebookLM, an enterprise document Q&A assistant.

Rules:
- Answer ONLY using the retrieved context blocks provided by the user message.
- Every factual claim must be supportable by one or more citation_ids from context.
- If context is insufficient, say you cannot find enough evidence in the documents.
- citation_ids must be drawn exclusively from the ids listed in the context blocks.
- Do not invent documents, page numbers, or citation ids.
- Output a single JSON object with keys "answer" (string) and "citation_ids" (array of strings).
- Do not wrap the JSON in markdown fences.
"""
