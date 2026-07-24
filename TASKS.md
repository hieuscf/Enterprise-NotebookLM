# TASKS.md — Enterprise NotebookLM

Kế hoạch triển khai đầy đủ hệ thống trong **3 tháng**, dựa trên `Business_Context.md` (FR1–FR13, UC1–UC12), `database-design-enterprise-notebooklm.md` (schema v2), `System_Architecture_Enterprise_NotebookLM.md` (C4 + sequence) và `Enterprise_notebooklm_openapi.yaml` (API contract).

Task được nhóm theo **Module/FR**, không gắn tuần/ngày cụ thể — nhóm tự sắp lịch theo năng lực, nhưng nên đi theo đúng **thứ tự ưu tiên (P0 → P3)** vì các module sau phụ thuộc trực tiếp vào module trước.

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

Mục tiêu: có thể tạo workspace, upload tài liệu, chạy xong pipeline OCR→Chunk→Embedding→Index. Chưa có Chat/AI.

### 1.1 Hạ tầng & DevOps
- [x] [BE] Khởi tạo repo monorepo (backend FastAPI, frontend Next.js), Docker Compose (Postgres, Redis, Qdrant/pgvector, Elasticsearch, MinIO, Neo4j).
- [x] [BE] Cấu hình `.env`/secrets, CI cơ bản (lint + test on push).
- [x] [BE] Alembic (migration) khởi tạo schema PostgreSQL từ `database-design-enterprise-notebooklm.md` (toàn bộ bảng v2: `workspaces`, `users`, `roles`, `workspace_members`, `documents`, `document_versions`, `embeddings`, `pipeline_runs`, `pipeline_stage_logs`, `entities`, `entity_relations`, `topics`, `topic_chunks`, `document_chunks`, `query_cache`, `chat_sessions`, `chat_messages`, `message_generations`, `retrievals`, `citations`, `search_history`, `query_logs`, `summaries`, `extractions`, `comparisons`, `comparison_documents`, `reports`, `report_items`).
- [x] [BE] Setup logging/tracing cơ bản (structlog + OpenTelemetry hoặc tương đương) — nền cho FR13.

### 1.2 Auth & RBAC (FR12)
- [ ] [BE] `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me` (OAuth2/JWT).
- [ ] [BE] Middleware RBAC theo Workspace (role admin/editor/viewer) — API Gateway/Auth Middleware component.
- [ ] [BE] Rate limiting theo Workspace (Redis token bucket) — chuẩn bị cho FR12.
- [ ] [FE] Trang Login, lưu token, route guard theo role.

### 1.3 Workspace Management (FR1, UC1)
- [ ] [BE] CRUD Workspace: `GET/POST /workspaces`, `GET/PATCH/DELETE /workspaces/{id}`.
- [ ] [BE] Quản lý thành viên: `GET/POST /workspaces/{id}/members`, `PATCH/DELETE /workspaces/{id}/members/{userId}`.
- [ ] [FE] UI danh sách Workspace, tạo/sửa/xoá, quản lý thành viên + phân quyền (UC10).

### 1.4 Document Ingestion & Versioning (FR2, UC2)
- [ ] [BE] `POST /workspaces/{id}/documents` — upload, tạo `documents` + `document_versions` (version_number=1), lưu file vào MinIO, tính `checksum_sha256`, enqueue Celery job.
- [ ] [BE] `POST /.../versions` (upload lại) — tạo version mới, giữ lịch sử, cập nhật `current_version_id`.
- [ ] [BE] `POST /.../versions/{versionId}/set-current` — rollback/chuyển version.
- [ ] [BE] `GET /.../versions/{versionId}/pipeline-status` — trả `pipeline_runs` + `pipeline_stage_logs`.
- [ ] [AI] Pipeline Worker (Celery task) — OCR & Cleaning (Unstructured.io/PyMuPDF/python-docx/openpyxl) cho PDF/DOCX/XLSX/PPTX/TXT.
- [ ] [AI] Chunking strategy (theo cấu trúc tài liệu, giữ metadata trang/section).
- [ ] [AI] Embedding tài liệu (model theo `embeddings.model_name`), ghi `document_chunks.embedding_id`.
- [ ] [AI] Graph Extraction (entities + entity_relations) qua LightRAG — Low-Level Retrieval.
- [ ] [AI] Topic extraction phân cấp (`topics.parent_topic_id`, `level`) — High-Level Retrieval.
- [ ] [BE] Index BM25 vào Elasticsearch song song với indexing vector.
- [ ] [BE] Ghi `pipeline_stage_logs` cho từng bước (status, duration_ms, metadata, error_message) — FR13.
- [ ] [FE] UI Upload tài liệu (drag-drop, hiển thị trạng thái pipeline realtime theo `status`).
- [ ] [FE] UI danh sách tài liệu + lịch sử version + nút "Set as current"/rollback.

**Tiêu chí hoàn thành GĐ1:** Upload 1 file PDF thật → thấy đủ 5 stage log completed → có chunk/entity/topic trong DB → có thể xem lại lịch sử version.

---

## GIAI ĐOẠN 2 (P1) — Lõi sản phẩm: Search, Query Router, AI Chat, Citation

Mục tiêu: hỏi đáp AI Chat có dẫn nguồn xác thực được (đúng sequence diagram Complex Query), tối ưu số lần gọi LLM (FR11).

### 2.1 Intelligent Search (FR3, UC3, Module 3)
- [ ] [AI] Hybrid Retrieval: Vector Search (Qdrant/pgvector) + BM25 (Elasticsearch) + Knowledge Graph query (Neo4j).
- [ ] [AI] Re-ranking Layer bằng cross-encoder (non-LLM).
- [ ] [BE] `POST /workspaces/{id}/search` — trả kết quả đã rerank, ghi `search_history` (query_text, filters, results_count, clicked_document_id).
- [ ] [BE] `GET /workspaces/{id}/search/history`.
- [ ] [FE] UI tìm kiếm ngữ nghĩa: input query, filter (file_type, thời gian, tag), hiển thị kết quả kèm score/rank.

### 2.2 Query Router (FR11, UC12)
- [ ] [AI] Rule-based classifier cho 4 nhóm: cache_hit / metadata / factoid / complex (không dùng LLM).
- [ ] [BE] Bảng `query_cache`: check `query_hash` (exact) trước, sau đó so cosine similarity qua `query_embedding_id`.
- [ ] [AI] Nhánh Metadata Query — map câu hỏi liệt kê/thống kê sang query DB trực tiếp (0 LLM call).
- [ ] [AI] Nhánh Simple Factoid — trả lời extractive từ chunk có confidence cao (0 LLM call).
- [ ] [BE] Ghi `query_logs` (route_type, llm_calls_count, cache_id, message_id, latency_ms) cho **cả 4 nhánh** kể cả 0-LLM.
- [ ] [BE] Job dọn cache hết hạn theo `expires_at` (cron/Celery beat).

### 2.3 AI Chat + Prompt Construction (FR4, FR10, UC4, UC9)
- [ ] [BE] `POST/GET /workspaces/{id}/chat/sessions`, `GET/DELETE .../sessions/{id}` (Conversation Memory).
- [ ] [BE] `GET .../sessions/{id}/messages`.
- [ ] [BE] `POST .../sessions/{id}/messages` — nhận câu hỏi, ghi `chat_messages` (role=user), gọi Query Router.
- [ ] [AI] Prompt Construction — dựng prompt từ Top-K context, gọi LLM **1 lần duy nhất** với structured output (JSON: answer + citation_ids), áp dụng model tiering (Haiku cho đơn giản, Sonnet cho phức tạp).
- [ ] [BE] Streaming response (SSE) cho endpoint chat message; hỗ trợ fallback JSON khi `Accept: application/json`.
- [ ] [BE] Ghi `message_generations` (route_type, model_used, tokens, cost_usd, latency_ms, temperature, top_p, finish_reason) — kể cả route 0-LLM (giá trị 0/NULL).
- [ ] [FE] UI Chat: gửi câu hỏi, hiển thị streaming answer, hiển thị session list (tiếp tục ngữ cảnh cũ).

### 2.4 Citation & Verification (FR5, UC4, UC11)
- [ ] [AI] Ghi toàn bộ ứng viên retrieval vào bảng `retrievals` (chunk_id/entity_id, retrieval_method, score, rank) trước khi lọc.
- [ ] [AI] Citation Verification Layer — đối chiếu deterministic `citation_ids` LLM trả về với `retrievals` đã lưu; set `verified=true/false`.
- [ ] [AI] Cơ chế fallback "không đủ căn cứ trong tài liệu" khi citation không hợp lệ, hoặc sinh lại tối đa 1 lần.
- [ ] [BE] `GET /workspaces/{id}/chat/messages/{messageId}/citations`.
- [ ] [FE] Hiển thị citation dưới câu trả lời + click để highlight đoạn văn bản gốc trên tài liệu (dùng `text_snippet`).

**Tiêu chí hoàn thành GĐ2:** Đặt câu hỏi phức tạp → đi đúng luồng sequence diagram (Router miss cache → Hybrid Retrieval → Rerank → 1 LLM call → Citation Verification) → trả lời kèm citation bấm được, verified=true. Hỏi lại câu tương tự → cache hit, 0 LLM call.

---

## GIAI ĐOẠN 3 (P2 + P3) — Modules mở rộng, bảo mật, quan sát, hoàn thiện

### 3.1 AI Summary (FR6, UC5, Module 6)
- [ ] [AI] Sinh tóm tắt 4 dạng: short/detailed/by_topic/bullet_points.
- [ ] [BE] `GET/POST /workspaces/{id}/documents/{id}/summaries`, `GET/DELETE /workspaces/{id}/summaries/{id}`.
- [ ] [FE] UI chọn dạng tóm tắt, hiển thị kết quả, lưu lịch sử.

### 3.2 Information Extraction (FR7, UC6, Module 7)
- [ ] [AI] Trích xuất table/figures/entities/timeline → JSON có cấu trúc.
- [ ] [BE] `GET/POST .../documents/{id}/extractions`, `GET/DELETE /workspaces/{id}/extractions/{id}`.
- [ ] [FE] UI hiển thị kết quả dạng bảng/JSON, export.

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
- [ ] [BE] `GET /admin/workspaces/{id}/cost-summary` (tổng hợp `message_generations` theo model/route_type).
- [ ] [BE] Circuit breaker + fallback khi LLM provider lỗi/chậm (Prompt Construction → LLM call).
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
- [ ] [BE] Tách container `backend-api` và `celery-worker` để scale độc lập.
- [ ] [BE] Docker Compose/K8s manifest production, healthcheck, autoscaling cơ bản cho pipeline worker.
- [ ] [BE] Backup/restore Postgres + MinIO.
- [ ] [BE] Runbook vận hành: xử lý pipeline_run failed, circuit breaker trip, cache dọn rác.

**Tiêu chí hoàn thành GĐ3 (release):** Toàn bộ UC1–UC12 chạy được end-to-end trên môi trường staging, có dashboard cost/observability, có test coverage cho luồng lõi (Router + Citation), tài liệu vận hành đầy đủ.

---

## Phụ lục — Ánh xạ nhanh Module ↔ FR ↔ Bảng DB chính

| Module | FR | Bảng DB chính | Endpoint chính |
|---|---|---|---|
| 1. Workspace | FR1 | workspaces, workspace_members, roles | `/workspaces/*` |
| 2. Knowledge Base | FR2 | documents, document_versions, pipeline_runs, pipeline_stage_logs, embeddings, entities, topics, document_chunks | `/workspaces/{id}/documents/*` |
| 3. Search | FR3 | search_history | `/workspaces/{id}/search` |
| 4. Chat | FR4, FR10 | chat_sessions, chat_messages, message_generations | `/workspaces/{id}/chat/*` |
| 5. Citation | FR5 | retrievals, citations | `/chat/messages/{id}/citations` |
| 6. Summary | FR6 | summaries | `/documents/{id}/summaries` |
| 7. Extraction | FR7 | extractions | `/documents/{id}/extractions` |
| 8. Comparison | FR8 | comparisons, comparison_documents | `/workspaces/{id}/comparisons` |
| 9. Report | FR9 | reports, report_items | `/workspaces/{id}/reports` |
| 10. Query Router | FR11 | query_cache, query_logs | (internal, xuyên suốt Chat) |
| Auth/RBAC | FR12 | users | `/auth/*` |
| Observability | FR13 | query_logs, pipeline_stage_logs, message_generations | `/admin/workspaces/{id}/*` |

