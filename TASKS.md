# TASKS.md — Enterprise NotebookLM

Kế hoạch triển khai đầy đủ hệ thống trong **3 tháng**, dựa trên `Business_Context.md` (FR1–FR14, UC1–UC13), `database-design-enterprise-notebooklm.md` (schema v3), `System_Architecture_Enterprise_NotebookLM.md` (C4 + sequence, v3: LlamaParse + Confidence Engine + Event-driven Agents) và `Enterprise_notebooklm_openapi.yaml` (API contract v3).

Task được nhóm theo **Module/FR**, không gắn tuần/ngày cụ thể — nhóm tự sắp lịch theo năng lực, nhưng nên đi theo đúng **thứ tự ưu tiên (P0 → P3)** vì các module sau phụ thuộc trực tiếp vào module trước.

---

## Trạng thái triển khai (cập nhật 2026-08-09)

**Baseline code hiện tại:** schema **v3** + chat migrations + **FR6 summaries** + **FR7 extractions** (Alembic head `b6c7d8e9f0a1`: summaries observability/async/sections + extractions observability/async); pipeline 6 stage: `document_understanding` → `cleaning_normalize` → `hierarchical_chunking` → `embedding` → `graph_extraction` → `indexing`. LlamaParse client có **retry (tenacity)** + **circuit breaker riêng (pybreaker)** tách khỏi LLM Provider. Auth, Workspace, Document API + FE upload/list/version/pipeline, Search (Hybrid + FE), Query Router (4 nhánh + cache cleanup), Confidence Engine & Micro Agents (FR14), Chat API + Prompt/SSE + **FE Chat UI**, AI Summary (async Celery + FE), Information Extraction (async Celery + FE, entities reuse Graph 0 LLM), `GET .../cost-summary` (+ `by_agent_type`) đã xong.

**Chat LLM provider (2026-08-08):** `CHAT_LLM_PROVIDER=anthropic|openai` — answer + rewrite dùng provider đã chọn; OpenAI Chat Completions wired (`OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`); Gemini chỉ placeholder env. Embedding vẫn `EMBEDDING_*` (độc lập). Qdrant adapter dùng `query_points` (client 1.18+ bỏ `.search`). Summary/Extraction generation (Celery) reuse cùng chat LLM + model tiering; Celery async tasks dùng `run_celery_async` (dispose AsyncEngine mỗi task — tránh asyncpg event-loop lỗi prefork).

**Chênh lệch so với tài liệu v3 (còn lại — lõi GĐ2 + GĐ3):**

| Hạng mục | Đã có | Còn thiếu (mục tiêu) |
|---|---|---|
| Schema DB / Pipeline / LlamaParse | Khớp v3 + chat soft-delete / last-message + FR6/FR7 columns | — |
| Search (FR3) | Hybrid Vector+BM25+Graph → Rerank; Search API + FE | Metadata DB là filter/post-query (`SearchService`), không phải nguồn fan-out thứ 4 |
| Query Router (FR11) | Classifier + cache + metadata/factoid/complex + `query_logs` + Celery cleanup | — |
| FR14 Confidence & Agents | Engine + Event Policy + Rewrite/Graph/SQL + Second Retrieval + `agent_events` + tests/metrics | — |
| Chat / Prompt | Sessions/messages HTTP + Prompt Construction (1 LLM) + SSE/JSON + FE Chat (sessions, stream, citations UI, agent badge) + multi-provider Anthropic/OpenAI | — |
| Citation (FR5) | Persist `retrievals`; map `citation_ids` → `citations` trên POST message; FE `CitationSection` | Citation Verification Layer cứng (verified vs DB) + fallback regenerate + `GET .../citations` + highlight đoạn gốc trên document viewer |
| Summary (FR6) | Async POST 202 + Celery `generate_summary` + status lifecycle + FE Document Detail (4 styles, reuse version, poll, history, copy) | — |
| Extraction (FR7) | Async POST 202 + Celery `generate_extraction` + structured schemas; entities **reuse Graph** (0 LLM); FE table/JSON + CSV/JSON export | Visual timeline (backlog); sidebar “Sắp có” chưa gỡ |

**Tiến độ GĐ1 (P0):** ~100% — backend + FE documents/upload/version/pipeline xong.

**Tiến độ GĐ2 (P1):** ~90% — Search + Query Router + FR14 + Chat Memory + POST messages/Prompt/SSE + **FE Chat** xong; còn **Citation Verification cứng (2.5)** (+ GET citations / highlight viewer).

**Tiến độ GĐ3 (P2):** Summary (3.1) + Extraction (3.2) **DONE**; còn Comparison / Report / Observability FE / hardening / E2E tests.

---

## 0. Team & Quy ước

- **Team 1–2 người**, tách 3 track kỹ thuật (một người có thể đảm nhiệm nhiều track):
  - **[BE]** — Backend API (FastAPI), DB schema, Celery worker, DevOps/hạ tầng.
  - **[AI]** — RAG pipeline: LightRAG, embedding, Hybrid Retrieval, re-ranking, Query Router, Prompt Construction, Citation Verification.
  - **[FE]** — Next.js/React UI: Workspace, Chat, Search, Upload, Report.
- **[DB]** = thay đổi schema/migration (thường đi kèm [BE]).
- Mỗi task có checkbox `[ ]`; đánh dấu `[x]` khi hoàn thành + PR/commit liên quan.
- Độ ưu tiên: **P0** = nền tảng bắt buộc trước, **P1** = lõi sản phẩm (AI Chat có citation), **P2** = tính năng mở rộng (Summary/Extraction/Comparison/Report), **P3** = hoàn thiện/vận hành.

---

## GIAI ĐOẠN 1 (P0) — Nền tảng: Auth, Workspace, Document Pipeline

Mục tiêu: có thể tạo workspace, upload tài liệu, chạy xong pipeline Document Understanding→Chunk→Embedding→Index (v3). Chưa có Chat/AI.

### 1.1 Hạ tầng & DevOps
- [x] [BE] Khởi tạo repo monorepo (backend FastAPI, frontend Next.js), Docker Compose (Postgres, Redis, Qdrant/pgvector, Elasticsearch, MinIO, Neo4j).
- [x] [BE] Cấu hình `.env`/secrets, CI cơ bản (lint + test on push) — `.github/workflows/ci.yml`.
- [x] [BE] Alembic schema PostgreSQL **v2** (28 bảng baseline): `6ebf6936f6c1_initial_schema_v2.py` + migrations bổ sung (`section`, `section_index`, soft-delete workspaces).
- [x] [DB] Migration schema **v3 Part 1** — `f6a7b8c9d0e1_schema_v3_part1_llamaparse_hierarchy.py` (markdown_storage_path, layout_metadata, hierarchical chunks, pipeline enum extend giữ deprecated, indexes).
- [x] [DB] Migration schema **v3 Part 2** — `d4e5f6a7b8c9_schema_v3_llamaparse_confidence_agents.py` (parser, retrieval_pass, confidence_*, agent_events).
- [x] [BE] Setup logging/tracing cơ bản (structlog + OpenTelemetry) — nền cho FR13.

### 1.2 Auth & RBAC (FR12)
- [x] [BE] `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me` (OAuth2/JWT).
- [x] [BE] Middleware RBAC theo Workspace (role admin/editor/viewer) — API Gateway/Auth Middleware component.
- [x] [BE] Rate limiting theo Workspace (Redis token bucket) — chuẩn bị cho FR12.
- [x] [FE] Trang Login, lưu token, route guard theo role.

### 1.3 Workspace Management (FR1, UC1)
- [x] [BE] CRUD Workspace: `GET/POST /workspaces`, `GET/PATCH/DELETE /workspaces/{id}`.
- [x] [BE] Quản lý thành viên: `GET/POST /workspaces/{id}/members`, `PATCH/DELETE /workspaces/{id}/members/{userId}`.
- [x] [FE] UI danh sách Workspace, tạo/sửa/xoá, quản lý thành viên + phân quyền (UC10).

### 1.4 Document Ingestion & Versioning (FR2, UC2)

#### Backend API
- [x] [BE] `POST /workspaces/{id}/documents` — upload, tạo `documents` + `document_versions` (version_number=1), lưu file vào MinIO, tính `checksum_sha256`, enqueue Celery job.
- [x] [BE] `POST /.../versions` (upload lại) — tạo version mới, giữ lịch sử, cập nhật `current_version_id`.
- [x] [BE] `POST /.../versions/{versionId}/set-current` — rollback/chuyển version.
- [x] [BE] `GET /.../versions/{versionId}/pipeline-status` — trả `pipeline_runs` + `pipeline_stage_logs`.

#### Pipeline Worker — v3 (mục tiêu)
- [x] [AI] **Document Understanding** qua **LlamaParse API** cho PDF/DOCX/XLSX/PPTX/TXT: gọi API, lưu output Markdown (`document_versions.markdown_storage_path`) và Layout Analysis (`document_versions.layout_metadata`) song song với Metadata Extraction từ chính cấu trúc Markdown (stage `document_understanding`) — `app/services/document_understanding.py` + `app/clients/llamaparse_client.py` + `app/ai/layout.py`. Không có LLAMAPARSE_API_KEY → fallback parser local, `document_versions.parser='local-ocr'`.
- [x] [AI] **Cleaning & Normalize** nội dung Markdown sau parse (loại nhiễu, chuẩn hoá định dạng) — stage `cleaning_normalize` (`app/ai/markdown_cleaning.py`, `app/workers/stages/cleaning_normalize.py`).
- [x] [AI] **Hierarchical Chunking** — chia theo cấu trúc phân cấp (section → sub-section → đoạn văn) dựa trên `layout_metadata`; ghi `document_chunks.parent_chunk_id`, `heading_path`, `depth`, `layout_type` — stage `hierarchical_chunking` (`app/ai/hierarchical_chunking/`, `app/services/hierarchical_chunking.py`). Pipeline log metadata đầy đủ; tests `tests/pipeline/test_hierarchical_chunking.py`.
- [x] [BE] **Retry + Circuit Breaker LlamaParse** (tách khỏi circuit breaker LLM Provider ở FR13/GĐ3):
  - Retry: `tenacity`, exponential backoff + jitter — `LLAMAPARSE_MAX_RETRIES`, `LLAMAPARSE_RETRY_MIN_WAIT`, `LLAMAPARSE_RETRY_MAX_WAIT` (`app/clients/retry_policy.py`).
  - Circuit breaker riêng: `pybreaker`, namespace metrics `llamaparse_cb_*` — `LLAMAPARSE_CB_FAILURE_THRESHOLD`, `LLAMAPARSE_CB_RESET_TIMEOUT`, `LLAMAPARSE_CB_SUCCESS_THRESHOLD` (`app/core/resilience/`, `app/clients/llamaparse_client.py`).
  - Fail-fast → `DataPipelineError("LlamaParse circuit breaker open")` → `pipeline_runs.status=failed`. Tests: `tests/test_llamaparse_resilience.py` (8 scenarios).

#### Pipeline Worker — v2 interim (legacy, giữ cho test/fallback)
- [x] [AI] Pipeline Worker (Celery) — OCR & Cleaning local (PyMuPDF/python-docx/openpyxl/txt) cho PDF/DOCX/XLSX/PPTX/TXT — stage `ocr_cleaning`. **Giữ lại làm parser fallback offline** cho `document_understanding` khi không có `LLAMAPARSE_API_KEY`.
- [x] [AI] Chunking theo cấu trúc section + token window — stage `chunking` (v2, **không còn trong STAGE_ORDER**; thay bởi `hierarchical_chunking`). File giữ cho legacy tests.
- [x] [AI] Embedding tài liệu (model theo `embeddings.model_name`), ghi `document_chunks.embedding_id`.
- [x] [AI] Graph Extraction (entities + entity_relations) qua LightRAG — Low-Level Retrieval.
- [x] [AI] Topic extraction phân cấp (`topics.parent_topic_id`, `level`) — High-Level Retrieval.
- [x] [BE] Index BM25 vào Elasticsearch song song với indexing vector.
- [x] [BE] Ghi `pipeline_stage_logs` cho từng bước (enum v2: `ocr_cleaning`, `chunking`, `embedding`, `graph_extraction`, `indexing`) — FR13.
- [x] [BE] Cập nhật `pipeline_stage_logs` sang enum v3 (6 stage) — migration `d4e5f6a7b8c9` + `PipelineStage` ORM.

#### Frontend
- [x] [FE] UI Upload tài liệu (drag-drop, hiển thị trạng thái pipeline realtime theo `status`, 6 stage v3) — `frontend/app/workspaces/[id]/upload/`, `features/documents/DocumentUploadView.tsx`, `PipelineStatusTracker.tsx`.
- [x] [FE] UI danh sách tài liệu + lịch sử version + nút "Set as current"/rollback — `frontend/app/workspaces/[id]/documents/`, `DocumentVersionHistory.tsx`, `setCurrentVersion` trong `lib/api-client.ts`.

**Tiêu chí hoàn thành GĐ1:** Upload 1 file PDF thật → thấy đủ 6 stage log completed (kể cả `document_understanding` gọi LlamaParse thành công) → có chunk (kèm `parent_chunk_id`/`heading_path`)/entity/topic trong DB → có thể xem lại lịch sử version qua UI. **→ Đạt.**

---

## GIAI ĐOẠN 2 (P1) — Lõi sản phẩm: Search, Query Router, AI Chat, Citation

Mục tiêu: hỏi đáp AI Chat có dẫn nguồn xác thực được (đúng sequence diagram Complex Query), tối ưu số lần gọi LLM (FR11).

### 2.1 Intelligent Search (FR3, UC3, Module 3)
- [x] [AI] Hybrid Retrieval: Vector Search (Qdrant/pgvector) + BM25 (Elasticsearch) + Knowledge Graph (Neo4j) fan-out song song → merge/dedupe — `app/services/retrieval/hybrid_retrieval_service.py` (+ `vector_search`, `bm25_search`, `graph_search`). Metadata DB dùng làm **filter/post-query** trên Search API (`metadata_search.py`, `SearchService._apply_filters`), không fan-out song song trong Hybrid.
- [x] [AI] Re-ranking Layer bằng cross-encoder (non-LLM) — `app/services/retrieval/reranker.py` (backend `cross_encoder` + heuristic fallback).
- [x] [BE] `POST /workspaces/{id}/search` — trả kết quả đã rerank, ghi `search_history` — `app/api/search.py`, `app/services/search.py`.
- [x] [BE] `GET /workspaces/{id}/search/history` (+ `PATCH .../history/{id}` click tracking).
- [x] [FE] UI tìm kiếm ngữ nghĩa: input query, filter, kết quả + history — `frontend/app/workspaces/[id]/search/`, `features/search/*`, `hooks/useSearch.ts`.

### 2.2 Query Router (FR11, UC12)
- [x] [AI] Rule-based classifier cho 4 nhóm: cache_hit / metadata / factoid / complex (không dùng LLM) — `app/services/query_router/router.py`, `rule_classifier.py` / `classifier.py`.
- [x] [BE] Bảng `query_cache`: check `query_hash` (exact) trước, sau đó cosine similarity qua embedding — `app/services/query_router/cache.py`, `app/repositories/query_cache.py`.
- [x] [AI] Nhánh Metadata Query — map câu hỏi liệt kê/thống kê sang query DB trực tiếp (0 LLM call) — `metadata_branch.py`, `handlers/metadata_handler.py`.
- [x] [AI] Nhánh Simple Factoid — trả lời extractive từ chunk có confidence cao (0 LLM call) — `factoid_branch.py`, `handlers/factoid_handler.py`, `lightweight_retriever.py`.
- [x] [BE] Ghi `query_logs` (route_type, llm_calls_count, cache_id, message_id, latency_ms) cho **cả 4 nhánh** kể cả 0-LLM — `orchestrator.py` → `logging_service.py`.
- [x] [BE] Job dọn cache hết hạn theo `expires_at` (Celery beat) — `app/tasks/cleanup_expired_cache.py`, schedule trong `workers/celery_app.py`.

### 2.3 Confidence Engine & Event-driven Micro Agents (FR14, UC13 — mới v3)

> **Ưu tiên: P1** — Low Confidence nằm trên nhánh Complex Query lõi (UC13); production
> thường gặp query mơ hồ / multi-hop / structured misclassified. Không đánh P2 vì
> thiếu Confidence Engine + Agents sẽ làm Complex Query trả lời kém tin cậy dù
> High-confidence path vẫn chạy được.
>
> **Trạng thái Task 5 (Testing & Observability): DONE** — integration A–D, boundary
> unit tests, `by_agent_type` trên cost-summary, structured `agent_triggered` logs,
> in-process FR14 metrics (+ TODO Prometheus).

- [x] [AI] Confidence Engine — tính `confidence_score` từ kết quả Cross-Encoder Reranker (score cao nhất, độ phân tán điểm, số candidate vượt ngưỡng), phân loại `high`/`low` theo threshold cấu hình được. Chỉ chạy trong nhánh Complex Query, sau Re-ranking.
- [x] [AI] Event Policy Engine — xác định `trigger_reason` (ambiguous_query/multi_hop_reasoning/structured_misclassified) và chọn agent tương ứng khi Low Confidence.
- [x] [AI] Rewrite Agent — viết lại câu hỏi mơ hồ/thiếu ngữ cảnh (model nhẹ, vd. Haiku).
- [x] [AI] Graph Agent — mở rộng truy vấn qua Knowledge Graph (Neo4j) cho câu hỏi multi-hop, không bắt buộc dùng LLM.
- [x] [AI] SQL Agent — truy vấn trực tiếp Metadata DB (PostgreSQL) cho câu hỏi structured bị Query Router phân loại nhầm thành Complex.
- [x] [AI] Second Retrieval (tuỳ chọn) — chạy lại Hybrid Retrieval với câu hỏi/ngữ cảnh đã qua agent, ghi `retrievals.retrieval_pass=2`.
- [x] [BE] Ghi `agent_events` (agent_type, trigger_reason, triggered_second_retrieval, model_used, cost_usd, latency_ms) mỗi lần agent được kích hoạt.
- [x] [BE] `GET /workspaces/{id}/chat/messages/{messageId}/agent-events`.
- [x] [BE][AI] Integration tests Low Confidence (A ambiguous / B multi-hop / C structured / D retry-still-low) — `tests/integration/test_fr14_low_confidence_pipeline.py`.
- [x] [AI] Boundary unit tests Confidence Engine — `tests/test_confidence_engine.py`.
- [x] [BE] Structured logging `agent_triggered` + in-process FR14 metrics (`app/core/fr14_metrics.py`; TODO Prometheus khi có exporter).
- [x] [BE] Mở rộng `GET /admin/workspaces/{id}/cost-summary` với `by_agent_type` (backward-compatible).

### 2.4 AI Chat + Prompt Construction (FR4, FR10, UC4, UC9)

> **Part 1/3 DONE (2026-08-06):** Conversation Memory — session CRUD (soft-delete
> `deleted_at`/`deleted_by`) + GET messages (nested generation/citations).  
> **Part 2/3 DONE (2026-08-06):** POST messages → Query Router → Prompt Construction
> (1 answer LLM) + model tiering + SSE/JSON; `get_latest_retrieval_pass` helper;
> tests `tests/test_chat_message_processing.py`.  
> **Part 3/3 DONE (2026-08-07/08):** FE Chat UI — routes `/workspaces/[id]/chat`,
> session sidebar, SSE stream, citations list, agent badge; Sidebar link enabled
> khi có `workspaceId`.  
> **Ops (2026-08-08):** Multi-provider chat LLM — `CHAT_LLM_PROVIDER` + OpenAI
> adapter (`app/adapters/openai_chat.py`, `chat_llm.py`); Qdrant `query_points` fix.

- [x] [BE] `POST/GET /workspaces/{id}/chat/sessions`, `GET/DELETE .../sessions/{id}` (Conversation Memory) — `ChatSessionService` + soft-delete migration `c0d1e2f3a4b5`; tests `tests/test_chat_sessions.py`.
- [x] [BE] `GET .../sessions/{id}/messages` — nested `generation` + `citations`; user → generation=null, citations=[].
- [x] [BE] `POST .../sessions/{id}/messages` — user insert → Query Router → 0-LLM persist / complex FR14 + Prompt Construction; `MessageProcessingService.generate_answer`.
- [x] [AI] Prompt Construction — `prompt_builder.build_prompt` + `PromptAnswerGenerator` (structured `{answer, citation_ids}`); latest retrieval pass only via `RetrievalRecordRepository.list_for_latest_pass`.
- [x] [BE] Streaming response (SSE) mặc định; `Accept: application/json` → JSON `ChatMessage`.
- [x] [BE] Ghi `message_generations` (0-LLM + complex); `agent_triggered` / confidence từ pipeline; session `touch_after_message` (+ `last_message_*` / `message_count` migration `c1d2e3f4a5b6`).
- [x] [BE] Chat LLM provider switch — `CHAT_LLM_PROVIDER=anthropic|openai` (Gemini env placeholder); answer + rewrite qua `app/adapters/chat_llm.py`; tests `tests/test_openai_chat.py`.
- [x] [FE] UI Chat: gửi câu hỏi, streaming answer, session list / tiếp tục ngữ cảnh — `frontend/app/workspaces/[id]/chat/`, `features/chat/*`, `hooks/useChat*.ts`, `lib/chat.api.ts`.

### 2.5 Citation & Verification (FR5, UC4, UC11)
- [x] [AI] Ghi toàn bộ ứng viên retrieval vào bảng `retrievals` (chunk_id/entity_id, retrieval_method, score, rank, retrieval_pass) trước khi lọc — `RetrievalRecordsRepository` trong `complex_query_pipeline.py` (pass 1/2).
- [ ] [AI] Citation Verification Layer — đối chiếu deterministic `citation_ids` LLM trả về với `retrievals` đã lưu (cả pass 1 và pass 2 nếu có); set `verified=true/false`. (Map citation trên POST message đã có; chưa có verification service / regenerate.)
- [ ] [AI] Cơ chế fallback "không đủ căn cứ trong tài liệu" khi citation không hợp lệ, hoặc sinh lại tối đa 1 lần.
- [ ] [BE] `GET /workspaces/{id}/chat/messages/{messageId}/citations`.
- [x] [FE] Hiển thị citation dưới câu trả lời trong Chat — `features/chat/CitationSection.tsx` (+ link document). **Còn lại:** click → highlight đoạn gốc trên document viewer (`text_snippet`).
- [x] [FE] Badge khi `generation.agent_triggered` — `features/chat/AgentBadge.tsx` (copy generic; không gọi `agent-events` chỉ để label). **Tuỳ chọn sau:** copy theo `agent_type` từ Admin/agent-events.

**Tiêu chí hoàn thành GĐ2:**
- Đặt câu hỏi phức tạp, High Confidence → đi đúng luồng (Router miss cache → Hybrid Retrieval → Rerank → Confidence Engine=high → 1 LLM call → Citation Verification) → trả lời kèm citation bấm được, verified=true.
- Đặt câu hỏi mơ hồ/multi-hop cố tình → Confidence Engine=low → thấy đúng agent được kích hoạt trong `agent_events`, có Second Retrieval (`retrieval_pass=2`), vẫn ra câu trả lời kèm citation verified.
- Hỏi lại câu tương tự → cache hit, 0 LLM call, không có `agent_events`.

> **Hiện trạng (2026-08-08):** Search + Router + FR14 + Chat API/Prompt/SSE + FE Chat đạt; tiêu chí end-to-end **Citation Verification cứng** (verified + GET citations + highlight viewer) **chưa đạt** — còn mục 2.5.

---

## GIAI ĐOẠN 3 (P2 + P3) — Modules mở rộng, bảo mật, quan sát, hoàn thiện

### 3.1 AI Summary (FR6, UC5, Module 6)

> **DONE (2026-08-08):** Parts 1–3 — migration observability + async status/sections;
> `SummaryService.request_summary` / `process_summary`; Celery `generate_summary`;
> API GET/POST/DELETE (POST **202**, RBAC member read / editor+ write);
> FE Document Detail section (4 styles, current-version reuse, poll ~2.5s, history,
> old-version badge, copy). OpenAPI Summary synced. Tests: `test_summary_service.py`,
> `test_summaries_api.py`, `scripts/test-summary-ui.mjs`.

- [x] [AI] Sinh tóm tắt 4 dạng: short/detailed/by_topic/bullet_points — structured LLM + `by_topic.sections`; version-bound `source_version_id`.
- [x] [BE] `GET/POST /workspaces/{id}/documents/{id}/summaries`, `GET/DELETE /workspaces/{id}/summaries/{id}` — async 202 + status `processing|completed|failed`.
- [x] [FE] UI chọn dạng tóm tắt, hiển thị kết quả, lưu lịch sử — `features/summaries/*` trên Document Detail.

### 3.2 Information Extraction (FR7, UC6, Module 7)

> **DONE (2026-08-08/09):** Parts 4–6 — migration observability + async status;
> `ExtractionService` (table/figures/timeline LLM structured; **entities REUSE Graph**
> `Entity.source_version_id` → 0 LLM); Celery `generate_extraction` + `run_celery_async`;
> API GET/POST/DELETE (POST **202**, cùng RBAC Summary); FE Document Detail
> (type+format, reuse, poll, history, table/JSON, CSV/JSON export). Visual timeline
> deferred (table/list đủ P2). Tests: `test_extraction_service.py`,
> `test_extractions_api.py`, `scripts/test-extraction-ui.mjs`.

- [x] [AI] Trích xuất table/figures/entities/timeline → JSON có cấu trúc (Pydantic per-type; entities reuse LightRAG/Graph khi standard path).
- [x] [BE] `GET/POST .../documents/{id}/extractions`, `GET/DELETE /workspaces/{id}/extractions/{id}` — async 202 + status lifecycle.
- [x] [FE] UI hiển thị kết quả dạng bảng/JSON, export CSV/JSON — `features/extractions/*` trên Document Detail.

### 3.3 Multi-document Comparison (FR8, UC7, Module 8)
- [ ] [AI] So sánh ≥2 tài liệu (similarities/differences), tuỳ chọn `focus`.
- [ ] [BE] `GET/POST /workspaces/{id}/comparisons`, `GET/DELETE .../comparisons/{id}`.
- [ ] [FE] UI chọn ≥2 tài liệu, hiển thị bảng so sánh highlight giống/khác.

### 3.4 Report Generation & Export (FR9, UC8, Module 9)
- [ ] [BE] `POST /workspaces/{id}/reports` — gộp summary/extraction/comparison/chat_session theo `items[]`, xử lý bất đồng bộ.
- [ ] [BE] Sinh file PDF/DOCX/Markdown (dùng thư viện tương ứng theo từng format).
- [ ] [BE] `GET .../reports/{id}`, `GET .../reports/{id}/export`, `DELETE .../reports/{id}`.
- [ ] [FE] UI tạo báo cáo (chọn nguồn), theo dõi trạng thái, tải file.

### 3.5 Observability & Reliability (FR13, UC11 phần hệ thống)
- [ ] [BE] `GET /admin/workspaces/{id}/query-logs` (filter route_type).
- [ ] [BE] `GET /admin/workspaces/{id}/pipeline-runs` (filter status).
- [x] [BE] `GET /admin/workspaces/{id}/cost-summary` (tổng hợp `message_generations` theo model/route_type; FR14 thêm `by_agent_type` từ `agent_events`, backward-compatible).
- [ ] [BE] Circuit breaker + fallback khi **LLM provider** lỗi/chậm (Prompt Construction → LLM call). **Tách instance/state/metrics khỏi LlamaParse CB** (`anthropic_cb_*` hoặc tương đương — dùng chung framework `app/core/resilience/`).
- [ ] [FE] Dashboard admin cơ bản: cost summary, pipeline status, query log.

### 3.6 Bảo mật & Đa tenant (hoàn thiện FR12)
- [ ] [BE] Rà soát RBAC toàn bộ endpoint theo `workspaceId` (không rò rỉ chéo workspace).
- [ ] [BE] Mã hoá dữ liệu khi truyền (TLS Nginx + internal TLS/overlay network nếu multi-node) và tại chỗ (encryption at rest cho MinIO/Postgres).
- [ ] [BE] Audit lại rate limiting theo Workspace dưới tải thực tế.

### 3.7 Kiểm thử & Chất lượng
- [ ] [BE][AI] Unit test cho Query Router (đúng phân loại 4 nhóm), Citation Verification (đúng verified true/false).
- [ ] [BE] Integration test luồng end-to-end: upload → pipeline → chat → citation → report.
- [ ] [FE] Test UI luồng chính (Chat, Upload, Search, Report) — Playwright/Cypress.
- [ ] [AI] Đánh giá chất lượng retrieval (precision/recall thủ công trên bộ câu hỏi mẫu) trước khi release.
- [ ] [BE] Load test Query Router + Chat endpoint (đảm bảo cache giảm tải LLM đúng như bảng so sánh mục 6.3 tài liệu gốc).

### 3.8 Triển khai (Deployment)
- [x] [BE] Tách container `backend-api` và `celery-worker` để scale độc lập — `docker-compose.yml`.
- [ ] [BE] Docker Compose/K8s manifest production, healthcheck, autoscaling cơ bản cho pipeline worker.
- [ ] [BE] Backup/restore Postgres + MinIO.
- [ ] [BE] Runbook vận hành: xử lý pipeline_run failed, circuit breaker trip (LlamaParse vs LLM), cache dọn rác.

**Tiêu chí hoàn thành GĐ3 (release):** Toàn bộ UC1–UC13 chạy được end-to-end trên môi trường staging, có dashboard cost/observability, có test coverage cho luồng lõi (Router + Citation + Confidence Engine), tài liệu vận hành đầy đủ.

---

## Phụ lục — Ánh xạ nhanh Module ↔ FR ↔ Bảng DB chính

| Module | FR | Bảng DB chính | Endpoint chính |
|---|---|---|---|
| 1. Workspace | FR1 | workspaces, workspace_members, roles | `/workspaces/*` |
| 2. Knowledge Base | FR2 | documents, document_versions (parser, layout_metadata), pipeline_runs, pipeline_stage_logs, embeddings, entities, topics, document_chunks (parent_chunk_id, heading_path, depth) | `/workspaces/{id}/documents/*` |
| 3. Search | FR3 | search_history | `/workspaces/{id}/search` |
| 4. Chat | FR4, FR10 | chat_sessions, chat_messages, message_generations | `/workspaces/{id}/chat/*` |
| 5. Citation | FR5 | retrievals (retrieval_pass), citations | `/chat/messages/{id}/citations` |
| Confidence Engine & Agents | FR14 (mới v3) | message_generations (confidence_level, confidence_score, agent_triggered), agent_events | `/chat/messages/{id}/agent-events` |
| 6. Summary | FR6 | summaries (source_version_id, status, sections, tokens/cost) | `/documents/{id}/summaries` (POST 202) |
| 7. Extraction | FR7 | extractions (source_version_id, status, result_json, tokens/cost) | `/documents/{id}/extractions` (POST 202) |
| 8. Comparison | FR8 | comparisons, comparison_documents | `/workspaces/{id}/comparisons` |
| 9. Report | FR9 | reports, report_items | `/workspaces/{id}/reports` |
| 10. Query Router | FR11 | query_cache, query_logs | (internal, xuyên suốt Chat) |
| Auth/RBAC | FR12 | users | `/auth/*` |
| Observability | FR13 | query_logs, pipeline_stage_logs, message_generations | `/admin/workspaces/{id}/*` |
