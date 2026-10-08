# =============================================================================
# File: REFACTOR_PLAN.md
# Module/Service: Architecture
# Layer: Documentation
# Purpose: Plan to decouple core document/knowledge operations from optional AI.
# =============================================================================

# AI-Optional Architecture Refactor Plan

**Principle:** Core enterprise document operations must work with `AI_ENABLED=false`.
AI is an on-demand integration, not the document lifecycle.

This change **extends** `docs/` (FR2 currently assumes upload → automatic ingestion
pipeline). The user explicitly requested the new architecture. OpenAPI keeps existing
resource groups; analysis endpoints are additive.

---

## 1. Current architecture

Modular monolith (`backend/app/`):

```
API (app/api) → Services (app/services) → Repositories → PostgreSQL
                              ↓
                    Adapters (MinIO, Qdrant, ES, Neo4j, httpx LLM)
                              ↓
                    Celery workers (app/workers)
```

Frontend talks only to Backend via Next.js BFF (`/api/proxy`). No browser LLM/SDK.

### What already matches the target

| Area | Status |
|------|--------|
| Object storage | Original bytes in **MinIO**; Postgres stores metadata + `storage_path` |
| Versioning | `documents` + `document_versions` with checksum, size, MinIO key |
| Workspace / RBAC | Independent of AI |
| Report generation | Aggregates stored artifacts; **0 LLM** |
| Contract clause diff | Deterministic orchestrator (`LLMTask.NONE`) already exists |
| Citation verification | Deterministic; does not call LLM |
| Query Router 0-LLM branches | cache / metadata / section / factoid |
| Canonical document API | `GET .../canonical` built from layout after parse |
| Standalone preview task | `generate_preview` — not an LLM stage |
| LLM transport | `httpx` only (no LangChain / LlamaIndex / OpenAI/Anthropic pip SDKs) |

### Coupling that must be broken

```
UPLOAD
  → create document + version (status=processing)
  → create pipeline_runs
  → run_pipeline.delay()
  → preview → LlamaParse/OCR → chunk → embed → graph → ES index
  → version.status = ready | failed
```

Document usability (`ready`/`failed`) is the same flag as AI index readiness.
A failed LlamaParse marks the **document version** failed even though the original
file is stored and downloadable.

Business services import AI adapters directly:

- `chat/answer_generator.py` → `chat_llm`
- `summary_service.py` → `chat_llm`
- `extraction_service.py` → `chat_llm`
- `comparison_service.py` → `chat_llm` (narrative always LLM)
- `rewrite_agent.py` → `chat_llm`
- `vector_search.py` / `hybrid_retrieval_service.py` → `embed_texts_batch`
- Search API has **no Postgres fallback** (all three retrieval sources down → 503)

No `AI_ENABLED`. App still starts without keys (lazy adapters), but **upload always
enqueues the AI pipeline**. Frontend treats `status=processing` as ingestion and
polls the full AI pipeline after every upload.

---

## 2. Problems

1. **Upload = AI analysis.** User cannot store a file without LlamaParse/embedding/graph.
2. **One status field** mixes document lifecycle and AI lifecycle.
3. **New version auto-analyzes**, invalidating the “v1 READY / v2 NOT_ANALYZED” model.
4. **Search** cannot answer from titles/metadata when Qdrant/ES/Neo4j/AI are off.
5. **Comparison FR8 narrative** always requires one LLM call (deterministic clause
   pipeline is only an optional attach).
6. **Summary** is LLM-only; no structural/metadata summary.
7. **No single AI Gateway.** Services construct provider calls themselves.
8. **No on-demand analysis API.**
9. Frontend has no `ai_analysis_status` and no “Analyze for AI” action.

---

## 3. Target architecture

Keep the **existing modular monolith**. Do **not** rename `app/api|services|domain`
into a new top-level tree. Add an integrations package and ports.

```
Frontend
   ↓ BFF / API
Application services (workspace, document, search, chat, comparison, report, analysis)
   ↓ ports
AIGateway  (only entry for generate / embed / rerank)
   ↓ (when AI_ENABLED=true)
adapters: chat_llm, embedding, llamaparse, qdrant, neo4j, elasticsearch
   ↓
Background worker: analysis pipeline (on-demand only)
```

### Document lifecycle (`document_versions.status`)

Keep existing enum for API compatibility: `processing | ready | failed`.

| Event | `status` meaning after refactor |
|-------|----------------------------------|
| Upload stored in MinIO | `ready` (file is usable: view, download, ACL, version) |
| Storage/validation failure | no version row (unchanged) |
| AI analysis failure | **stays `ready`** — file remains valid |
| Archive | not implemented (no archive product surface) — deferred |

`processing` remains in the enum for in-flight **legacy** rows and is no longer
used as “waiting for AI”. Brief upload spooling does not persist `processing`.

### AI analysis lifecycle (`document_versions.ai_analysis_status`)

```
NOT_ANALYZED → QUEUED → PROCESSING → READY
                              ↘ FAILED
READY → STALE   (when a newer current version exists; old READY is kept)
```

New version: `ai_analysis_status = not_analyzed`. Previous version keeps `ready`.

### Upload (no AI)

1. Validate file + permission
2. Create `documents` + `document_versions`
3. SHA-256, MinIO original, metadata
4. `status=ready`, `ai_analysis_status=not_analyzed`
5. **Do not** create `pipeline_runs` / **do not** `run_pipeline.delay`
6. Optionally enqueue **preview-only** `generate_preview` (local, non-LLM, needed for viewer)

### Analysis (on demand)

```
POST /workspaces/{workspaceId}/documents/{documentId}/versions/{versionId}/analysis
GET  (same path)  — never triggers analysis
```

POST is idempotent:

- `AI_ENABLED=false` → `AI_DISABLED`
- already `ready` → return current, do not re-index
- `queued` / `processing` → return current job
- `not_analyzed` / `failed` / `stale` → create `pipeline_runs`, enqueue `run_pipeline`

Worker: existing stages from `document_understanding` through `indexing`
(preview skipped if already completed). On success: `ai_analysis_status=ready`.
On failure: `ai_analysis_status=failed` + `analysis_error`; document `status` stays `ready`.

### AI Gateway

```
app/integrations/ai/
  exceptions.py     AI_DISABLED, AI_CAPABILITY_UNAVAILABLE
  gateway.py        Protocol + get_ai_gateway()
  disabled.py       raises on generate/embed/analyze
  live.py           delegates to existing chat_llm + embedding adapters
```

`get_ai_gateway()` returns Disabled gateway when `AI_ENABLED=false` **without**
importing provider modules.

Business services must call the gateway (or check `settings.ai_enabled`) rather
than Anthropic/OpenAI modules. Existing `app/adapters/chat_llm.py` stays as the
live implementation behind the gateway.

### Search

```
SearchService
  ├── BasicSearch (Postgres title/metadata + chunk ILIKE if chunks exist)
  └── HybridRetrieval (optional; AI/index stack)
```

If `AI_ENABLED=false` or hybrid raises `RetrievalUnavailableError`, return basic
results instead of 503. Map keyword hits to existing `retrieval_method=bm25`
to avoid enum/API breakage.

### Chat

Sessions remain a core feature (CRUD, history). Answering:

1. If `AI_ENABLED=false` and the path needs LLM/embed → `AI_CAPABILITY_UNAVAILABLE`
2. Complex/factoid with **no READY analysis** in workspace → clear business error
   (`DOCUMENT_NOT_ANALYZED`), no crash
3. READY versions → Query Router → retrieval → **AI Gateway** → Citation Verification → persist

0-LLM metadata routes may still run when AI is off if they only hit Postgres.

### Comparison / Summary / Report

| Feature | AI off | AI on |
|---------|--------|-------|
| Comparison | Metadata (+ checksum/size/type) diff; attach deterministic contract pipeline if chunks exist | Existing 1 LLM narrative + optional clause attach |
| Summary | Metadata / structural stats summary | Existing NL summary via gateway |
| Extraction | Table parse if chunks exist; else capability error | Existing mixed modes |
| Report | Unchanged (already 0 LLM) | Optional future NL enhancement — not in this refactor |

---

## 4. Files / modules to change

### New

| Path | Role |
|------|------|
| `backend/app/integrations/ai/*` | Gateway + disabled/live |
| `backend/app/services/analysis/analysis_service.py` | On-demand analysis |
| `backend/app/schemas/analysis.py` | GET/POST analysis body |
| `backend/alembic/versions/k5l6m7n8o9p0_ai_analysis_lifecycle.py` | Columns + enum |
| `backend/tests/test_ai_optional_architecture.py` | Tests 1–14 |
| Frontend: `AiAnalysisStatusBadge`, analyze API helpers | UI |

### Modified (high impact)

- `app/core/config.py`, `.env.example`, `docker-compose.yml` — `AI_ENABLED`
- `app/models/enums.py`, `types.py`, `models/documents.py`
- `app/services/documents.py` — stop auto-enqueue pipeline
- `app/api/documents.py` — analysis routes + `ai_analysis_status` on version
- `app/repositories/documents.py`, `pipeline_sync.py`, `workers/pipeline.py`
- `app/services/search.py` — basic fallback
- `app/services/chat/message_service.py`, `answer_generator.py`
- `app/services/summary/summary_service.py`
- `app/services/extraction/extraction_service.py`
- `app/services/comparison/comparison_service.py`
- `app/services/event_policy/agents/rewrite_agent.py`
- Frontend: `types/documents.ts`, `api-client.ts`, upload card, list, detail, chat empty states
- Existing tests that assert upload → `processing` + `run_pipeline.delay`

### Not doing (over-engineering)

- Microservices split
- Moving all of `app/` into `api/application/domain/infrastructure`
- Deleting Qdrant/Neo4j/ES/chunk tables
- Per-capability flags beyond `AI_ENABLED` (can add later)
- Document archive status (no product surface)
- Rewriting LlamaParse internals (CanonicalDocument already exists as API)

---

## 5. Database changes

Additive on `document_versions`:

| Column | Type | Default |
|--------|------|---------|
| `ai_analysis_status` | enum `ai_analysis_status` | `not_analyzed` |
| `analyzed_at` | timestamptz | null |
| `analysis_error` | text | null |

Enum values: `not_analyzed`, `queued`, `processing`, `ready`, `failed`, `stale`.

**Data backfill**

- `document_versions.status = ready` AND completed pipeline → `ai_analysis_status=ready`, `analyzed_at=pipeline.completed_at`
- failed pipeline, file still stored → `status=ready` (repair), `ai_analysis_status=failed`
- pending/running pipeline → `ai_analysis_status=processing` (or `queued`)
- no pipeline run → `not_analyzed`; if `status=processing`, set `status=ready`

Chunks/embeddings/graph tables **unchanged**. A version is valid with zero chunks.

Head revision: `j4k5l6m7n8o9`. New revision: `k5l6m7n8o9p0`.

---

## 6. API changes

Keep `/auth`, `/workspaces`, `/documents`, `/search`, `/chat`, `/summaries`,
`/extractions`, `/comparisons`, `/reports`, `/admin`.

**Additive**

- `POST/GET .../documents/{documentId}/versions/{versionId}/analysis`

**DocumentVersion response** (additive fields)

```json
{
  "status": "ready",
  "ai_analysis_status": "not_analyzed",
  "analyzed_at": null,
  "analysis_error": null
}
```

Upload still returns **202 + DocumentVersion**. Semantics: file accepted and stored,
not “AI pipeline started”. `GET .../pipeline-status` returns 404 until analysis is
requested (existing error). Frontend must not poll it after upload.

Error codes:

| Code | When |
|------|------|
| `AI_DISABLED` | Analysis POST while `AI_ENABLED=false` |
| `AI_CAPABILITY_UNAVAILABLE` | Chat/summary/NL comparison while AI off or provider missing |
| `DOCUMENT_NOT_ANALYZED` | Chat/RAG against versions that are not READY |

---

## 7. Migration strategy

1. Ship schema + fields (default `not_analyzed`).
2. Stop enqueue on upload; enqueue preview-only.
3. Add analysis API; reuse `run_pipeline` worker.
4. Gate LLM paths through gateway + `AI_ENABLED`.
5. Search fallback; comparison/summary deterministic paths.
6. Frontend dual status + Analyze CTA.
7. Tests 1–14; update upload tests.

Rollback: re-enable enqueue on upload (feature flag not needed if analysis API
exists). Columns are additive.

Default `AI_ENABLED=true` so existing deployments still *can* analyze; upload
no longer auto-triggers regardless of the flag.

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Frontend still polls pipeline after upload → 404 | Change UploadJobCard; treat stored version as success |
| Tests assume `status=processing` + delay() | Update `test_documents.py` and pipeline tests |
| Chat UX expects indexed chunks | Explicit empty/not-analyzed errors |
| Comparison tests expect LLM | Branch: AI off → deterministic result shape `{similarities,differences}` |
| OpenAPI / docs drift | Additive endpoints; note in this plan |
| Preview missing if we skip all workers | Keep `generate_preview` on upload |
| Idempotent re-index race | If queued/processing/ready, POST is a no-op |
| `get_settings` lru_cache in tests | Tests construct services with Settings(ai_enabled=False) |

---

## 9. Implementation order

Matches requested phases, adapted to current tree:

1. Config + schema + version fields (document vs AI lifecycle)
2. Confirm object storage (already MinIO) — no change beyond not blocking on AI
3. Versioning: new version = NOT_ANALYZED; old READY preserved
4. Analysis API + lifecycle updates in worker
5. AI Gateway
6. Worker: enqueue only from analysis (upload ≠ pipeline)
7. Search basic fallback
8. Chat via gateway + analysis checks
9. Comparison/summary deterministic; report unchanged
10. Frontend
11. Tests 1–14
