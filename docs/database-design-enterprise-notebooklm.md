# Database Design v2 — Enterprise NotebookLM

So với v1, bản v2 bổ sung 7 bảng mới và sửa 6 bảng để phản ánh đúng một RAG pipeline production: versioning tài liệu, embedding metadata, pipeline observability, cache truy vấn (Query Router check trước khi gọi LLM), retrieval tách khỏi citation, chat metrics đầy đủ, và lịch sử truy vấn tìm kiếm.

**Bản v3 (tài liệu này) bổ sung thêm** theo kiến trúc mới (LlamaParse Document Understanding + Hierarchical Chunking + Confidence Engine + Event-driven Micro Agents): 1 bảng mới (`agent_events`), sửa 4 bảng (`document_versions`, `document_chunks`, `pipeline_stage_logs`, `retrievals`, `message_generations`). Sơ đồ: `erd-enterprise-notebooklm-v3.mermaid`.

**Tóm tắt thay đổi (tích luỹ v1→v2→v3):**

| Loại | Bảng | Version |
|---|---|---|
| 🆕 Mới | `document_versions`, `embeddings`, `pipeline_runs`, `pipeline_stage_logs`, `retrievals`, `message_generations`, `search_history` | v2 |
| 🆕 Mới | `agent_events` | v3 |
| ✏️ Đổi tên | `semantic_cache` → `query_cache` | v2 |
| 🔧 Sửa | `documents`, `document_chunks`, `entities`, `topics`, `chat_messages`, `citations`, `query_logs` | v2 |
| 🔧 Sửa (bổ sung cột) | `document_versions` (parser info), `document_chunks` (hierarchy), `pipeline_stage_logs` (stage enum), `retrievals` (retrieval_pass), `message_generations` (confidence + agent) | v3 |

---

## 1. Versioning tài liệu (mới)

### `documents` (sửa)
Giờ chỉ giữ thông tin "định danh" của tài liệu, không còn chứa file vật lý — cho phép nhiều version cùng thuộc 1 document.

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID FK | |
| current_version_id | UUID FK → document_versions.id | Trỏ đến version đang active — dùng khi Chat/Search cần bản mới nhất |
| title | VARCHAR | Tên hiển thị (không đổi qua các version) |
| file_type | ENUM | |
| created_at / updated_at | TIMESTAMP | |

### `document_versions` (mới)
Mỗi lần upload lại/thay thế tài liệu → 1 version mới, giữ nguyên lịch sử.

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| document_id | UUID FK | |
| uploaded_by | UUID FK → users.id | |
| version_number | INT | Tăng dần 1, 2, 3... |
| storage_path | VARCHAR | Đường dẫn MinIO/S3 của version này |
| file_size_bytes | BIGINT | |
| checksum_sha256 | VARCHAR | Phát hiện file trùng/không đổi nội dung → tránh re-index không cần thiết |
| page_count | INT | |
| status | ENUM('processing','ready','failed') | |
| is_current | BOOLEAN | Đánh dấu version đang active (đồng bộ với `documents.current_version_id`) |
| parser | VARCHAR, DEFAULT 'llamaparse' | (mới v3) Engine dùng để Document Understanding — mặc định LlamaParse, cho phép đổi sang parser khác trong tương lai mà không đổi schema |
| markdown_storage_path | VARCHAR | (mới v3) Đường dẫn lưu output Markdown thô từ LlamaParse (MinIO/S3), tách khỏi `storage_path` (file gốc) để tái sử dụng khi re-chunk mà không gọi lại LlamaParse |
| layout_metadata | JSONB, NULL | (mới v3) Kết quả Layout Analysis (danh sách heading/section/bảng theo cấu trúc Markdown) — nguồn dữ liệu cho Metadata Extraction và Hierarchical Chunking |
| created_at | TIMESTAMP | |

> **Tác động dây chuyền:** `document_chunks` và `entities` giờ trỏ theo `document_version_id`/`source_version_id` thay vì `document_id` — đảm bảo khi tài liệu được cập nhật, chunk/entity cũ của version trước không bị lẫn với version mới, và có thể rollback hoặc so sánh giữa các version.

### `document_chunks` (sửa — v3: bổ sung cấu trúc phân cấp)

Bảng gốc (v1) đã có `document_version_id`, `content`, `embedding_id`, `page_number`... Bản v3 bổ sung các cột sau để phản ánh **Hierarchical Chunking** (thay vì chunking phẳng):

| Cột | Kiểu | Mô tả |
|---|---|---|
| parent_chunk_id | UUID FK → document_chunks.id, NULL | (mới v3) Self-reference — chunk cha theo cấu trúc phân cấp (vd. chunk đoạn văn trỏ về chunk section chứa nó) |
| heading_path | VARCHAR | (mới v3) Breadcrumb đường dẫn heading, vd. "1. Giới thiệu > 1.2 Mục tiêu > 1.2.1 Cụ thể" — lấy từ `document_versions.layout_metadata` |
| depth | INT | (mới v3) Độ sâu trong cây phân cấp (0 = chunk cấp cao nhất/section gốc), tương tự khái niệm `topics.level` |
| layout_type | ENUM('paragraph','heading','table','list'), NULL | (mới v3) Loại nội dung theo Layout Analysis — dùng để ưu tiên retrieval theo loại (vd. ưu tiên `table` cho câu hỏi số liệu) |

> Việc thêm `parent_chunk_id`/`heading_path` cho phép Vector Retrieval mở rộng ngữ cảnh theo chiều dọc (lấy thêm chunk cha khi chunk con điểm cao nhưng thiếu ngữ cảnh) — dùng bởi Graph Agent/Rewrite Agent khi Confidence Engine đánh giá Low Confidence (xem mục 9b).

---

## 2. RAG Pipeline & Observability (mới)

Đáp ứng yêu cầu phi chức năng "logging, tracing cho pipeline RAG để debug chất lượng câu trả lời" — trước đây tài liệu gốc chỉ mô tả luồng xử lý mà chưa có bảng lưu trạng thái từng bước.

### `pipeline_runs`
Một lượt xử lý đầy đủ cho 1 version tài liệu: OCR & Cleaning → Chunking → Embedding → Graph Extraction → Indexing.

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| document_version_id | UUID FK | |
| status | ENUM('pending','running','completed','failed') | |
| retry_count | INT | |
| error_message | TEXT NULL | |
| started_at / completed_at | TIMESTAMP | |

### `pipeline_stage_logs`
Chi tiết từng bước trong 1 pipeline run — phục vụ debug ("bước nào chậm/lỗi").

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| pipeline_run_id | UUID FK | |
| stage | ENUM('document_understanding','cleaning_normalize','hierarchical_chunking','embedding','graph_extraction','indexing') | (đổi v3) Trước là `('ocr_cleaning','chunking','embedding','graph_extraction','indexing')` — tách `ocr_cleaning` thành `document_understanding` (gọi LlamaParse, sinh Markdown+Layout+Metadata) + `cleaning_normalize` riêng; đổi `chunking` → `hierarchical_chunking` |
| status | ENUM('pending','running','completed','failed') | |
| duration_ms | INT | |
| metadata | JSONB | vd. số chunk tạo ra (kèm depth trung bình), số entity trích xuất, số heading phát hiện ở `document_understanding` |
| error_message | TEXT NULL | |
| started_at / completed_at | TIMESTAMP | |

---

## 3. Embedding Metadata (mới)

### `embeddings`
Tách riêng khỏi các bảng nội dung — vector thật lưu ở Qdrant/pgvector, bảng này chỉ lưu **metadata tham chiếu**, dùng chung cho chunk, topic, và query cache.

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| model_name | VARCHAR | vd. `text-embedding-3-large`, `voyage-3` |
| dimension | INT | Số chiều vector |
| vector_store | ENUM('qdrant','pgvector') | |
| vector_id | VARCHAR | ID/point trong vector store |
| index_name | VARCHAR | Tên collection/index |
| created_at | TIMESTAMP | |

`document_chunks.embedding_id`, `topics.embedding_id`, `query_cache.query_embedding_id` đều FK về bảng này (1 bản ghi embedding — 1 chủ sở hữu). Nếu re-embed do đổi model, tạo bản ghi `embeddings` mới thay vì update, giữ được lịch sử.

---

## 4. Query Cache — Router check trước khi gọi LLM (đổi tên + nâng cấp)

### `query_cache` (trước là `semantic_cache`)

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID FK | |
| query_embedding_id | UUID FK → embeddings.id, NULL | Dùng cho similarity check (không chỉ exact-hash) |
| query_hash | VARCHAR, INDEX | Hash câu hỏi đã chuẩn hoá — check nhanh (O(1)) trước khi so embedding |
| query_text | TEXT | |
| answer | TEXT | |
| citation_refs | JSONB | |
| similarity_threshold | FLOAT | Ngưỡng cosine similarity để tính là "hit" |
| hit_count | INT | |
| ttl_seconds | INT | Thời gian sống của cache entry |
| expires_at | TIMESTAMP | Router tự loại cache hết hạn |
| created_at / last_used_at | TIMESTAMP | |

**Luồng Query Router (đúng yêu cầu "check bảng này trước, nếu hit → không gọi LLM"):**

```
User Query
   → chuẩn hoá + hash → SELECT ... FROM query_cache WHERE query_hash = ? AND expires_at > now()
   → [Exact hit]      → trả lời ngay, tăng hit_count, KHÔNG gọi LLM
   → [Miss theo hash]  → tính embedding query → so sánh cosine với query_embedding_id gần nhất
   → [Similarity hit]  → trả lời ngay, KHÔNG gọi LLM
   → [Miss hoàn toàn]  → tiếp tục Metadata/Factoid/Complex như cũ
```

Mỗi lần kiểm tra cache (dù hit hay miss) đều được ghi vào `query_logs.cache_id` để phục vụ audit tỷ lệ cache hit.

---

## 5. Chat — tách metrics LLM ra bảng riêng (sửa)

### `chat_messages` (rút gọn)
Chỉ còn giữ nội dung hội thoại thuần, không lẫn thông tin vận hành LLM.

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| session_id | UUID FK | |
| role | ENUM('user','assistant') | |
| content | TEXT | |
| created_at | TIMESTAMP | |

### `message_generations` (mới)
Quan hệ 1–1 với `chat_messages` (chỉ tồn tại với message role = assistant và có gọi LLM thật). Đáp ứng đầy đủ các trường được yêu cầu bổ sung.

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| message_id | UUID FK, UNIQUE | |
| route_type | ENUM('cache_hit','metadata','factoid','complex') | Kết quả Query Router |
| confidence_level | ENUM('high','low'), NULL | (mới v3) Kết quả Confidence Engine — chỉ có giá trị khi `route_type='complex'`; NULL cho 3 route còn lại vì không đi qua Confidence Engine |
| confidence_score | FLOAT, NULL | (mới v3) Điểm số thô từ Confidence Engine trước khi threshold hoá thành `confidence_level` |
| agent_triggered | BOOLEAN, DEFAULT false | (mới v3) `true` nếu Event Policy Engine đã kích hoạt agent (tức `confidence_level='low'`) |
| model_used | VARCHAR | vd. claude-haiku-4-5, claude-sonnet-5 (model tiering) |
| prompt_tokens | INT | |
| completion_tokens | INT | |
| total_tokens | INT | |
| cost_usd | DECIMAL(10,6) | Tính từ tokens × đơn giá model tại thời điểm gọi — **không** gồm chi phí agent (xem `agent_events.cost_usd` riêng) |
| latency_ms | INT | Latency của riêng bước Prompt Construction → LLM; latency của agent nằm ở `agent_events.latency_ms` |
| temperature | FLOAT | |
| top_p | FLOAT | |
| finish_reason | ENUM('stop','length','content_filter','tool_calls') | |
| created_at | TIMESTAMP | |

> Với route_type ∈ {cache_hit, metadata, factoid}, `prompt_tokens`/`completion_tokens`/`cost_usd` = 0 hoặc NULL vì không gọi LLM — bảng vẫn tạo 1 dòng để giữ tính nhất quán khi truy vấn thống kê "0 lần gọi LLM" theo bảng so sánh mục 6.3 tài liệu gốc.

---

## 5b. Confidence Engine & Event-driven Agents (mới v3)

Đáp ứng kiến trúc mới: sau Cross-Encoder Reranker, `Confidence Engine` đánh giá độ tin cậy (ghi lại ở `message_generations.confidence_level/confidence_score`, mục 5). Khi Low Confidence, `Event Policy Engine` kích hoạt 1 trong 3 Micro Agent — bảng dưới đây ghi lại **mỗi lần kích hoạt agent**, độc lập với `message_generations` vì 1 message có thể không cần agent (High Confidence → không có dòng nào ở bảng này).

### `agent_events`

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| message_id | UUID FK → chat_messages.id | Message (câu hỏi) nào kích hoạt agent |
| agent_type | ENUM('rewrite','graph','sql') | Loại Micro Agent được Event Policy Engine chọn |
| trigger_reason | ENUM('ambiguous_query','multi_hop_reasoning','structured_misclassified') | Loại sự kiện: câu hỏi mơ hồ (Rewrite), cần suy luận đa bước (Graph), thực chất là structured query (SQL) |
| input_payload | JSONB | Đầu vào cho agent (vd. câu hỏi gốc, reranked candidates) |
| output_payload | JSONB | Đầu ra: câu hỏi đã viết lại (Rewrite), ngữ cảnh graph mở rộng (Graph), kết quả SQL trực tiếp (SQL) |
| triggered_second_retrieval | BOOLEAN | Có chạy lại Hybrid Retrieval (retrieval_pass=2) sau agent hay không |
| model_used | VARCHAR, NULL | Model nhẹ dùng cho agent (nếu có, vd. claude-haiku-4-5) — NULL nếu agent thuần rule-based (Graph/SQL Agent thường không cần LLM) |
| cost_usd | DECIMAL(10,6), DEFAULT 0 | Chi phí riêng của agent, tách khỏi `message_generations.cost_usd` |
| latency_ms | INT | |
| created_at | TIMESTAMP | |

> **Quan hệ:** 1 `chat_messages` (role=assistant) có tối đa 1 dòng `agent_events` — chỉ tồn tại khi `message_generations.agent_triggered=true`. Không tạo dòng cho High Confidence/Cache Hit/Metadata/Factoid.

---

## 6. Tách Retrieval khỏi Citation (sửa)

Trước đây `citations` gộp luôn kết quả truy hồi (chunk nào, score bao nhiêu) với việc "trích dẫn cuối cùng hiển thị cho user". Hai việc này có bản chất khác nhau: **retrieval** là toàn bộ ứng viên hệ thống lấy về (có thể hàng chục chunk, nhiều phương pháp), còn **citation** là tập con đã được LLM chọn + verify để hiển thị.

### `retrievals` (mới)
Lưu **toàn bộ** kết quả truy hồi cho một câu hỏi, trước khi rerank/lọc — phục vụ debug "vì sao câu trả lời sai" và đánh giá chất lượng retrieval độc lập với LLM.

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| message_id | UUID FK → chat_messages.id | Câu hỏi nào sinh ra kết quả này |
| chunk_id | UUID FK → document_chunks.id, NULL | |
| entity_id | UUID FK → entities.id, NULL | Với Low-Level Retrieval (thực thể) |
| retrieval_method | ENUM('vector','bm25','knowledge_graph','rerank') | |
| score | FLOAT | Điểm từ retrieval method / cross-encoder rerank |
| rank | INT | Thứ hạng sau re-ranking |
| retrieval_pass | INT, DEFAULT 1 | (mới v3) Lượt truy hồi: `1` = lần đầu (trước Confidence Engine); `2` = Second Retrieval sau khi Agent xử lý (chỉ có khi Low Confidence). Cho phép so sánh chất lượng trước/sau agent trên cùng 1 message |
| created_at | TIMESTAMP | |

### `citations` (sửa)
Giờ tham chiếu tới `retrievals` thay vì lặp lại chunk/document — mỗi citation = "1 kết quả retrieval đã được LLM chọn để trích dẫn và đã qua Citation Verification Layer".

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| message_id | UUID FK | |
| retrieval_id | UUID FK → retrievals.id | Trỏ ngược ra chunk/document/score gốc |
| text_snippet | TEXT | Đoạn văn bản chính xác dùng để highlight (có thể là sub-span của chunk) |
| verified | BOOLEAN | Kết quả đối chiếu deterministic (Citation Verification Layer) |
| order_index | INT | Thứ tự hiển thị trong câu trả lời |

---

## 7. Query History (mới)

### `search_history`
Trước đây chỉ có `query_logs` (log kỹ thuật cho Query Router/chi phí LLM). Bảng này lưu **lịch sử tìm kiếm của người dùng** ở Module 3 — Intelligent Search (UC3), độc lập với luồng AI Chat, phục vụ "tìm lại truy vấn đã thực hiện", gợi ý truy vấn phổ biến, phân tích hành vi tìm kiếm.

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID FK | |
| user_id | UUID FK | |
| query_text | TEXT | |
| filters | JSONB | Bộ lọc người dùng áp dụng (loại file, khoảng thời gian, tag...) |
| results_count | INT | |
| clicked_document_id | UUID FK → documents.id, NULL | Tài liệu người dùng click vào từ kết quả |
| created_at | TIMESTAMP | |

> Phân biệt: `search_history` = hành vi tìm kiếm ngữ nghĩa (Module 3); `query_logs` = log kỹ thuật của Query Router cho pipeline AI Chat (Module 4, mục 6–7 tài liệu gốc); `chat_messages`/`message_generations` = nội dung + chi phí từng lượt chat.

---

## 8. Topic — bổ sung embedding & phân cấp (sửa)

### `topics` (sửa)

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID FK | |
| embedding_id | UUID FK → embeddings.id, NULL | Vector đại diện cho chủ đề — dùng để so khớp câu hỏi với topic ở High-Level Retrieval |
| parent_topic_id | UUID FK → topics.id, NULL | Self-reference — cho phép topic phân cấp (chủ đề cha/con) |
| level | INT | Độ sâu trong cây phân cấp (0 = topic gốc) |
| name | VARCHAR | |
| summary | TEXT | |

Ví dụ phân cấp: `level 0`: "Tài chính" → `level 1`: "Báo cáo quý" / "Ngân sách" → `level 2`: "Ngân sách Marketing Q1". High-Level Retrieval có thể truy vấn theo `level` để quyết định độ rộng/hẹp của chủ đề cần lấy.

---

## 9. `query_logs` (sửa — thêm liên kết cache & message)

| Cột | Kiểu | Mô tả |
|---|---|---|
| id | UUID PK | |
| workspace_id | UUID FK | |
| user_id | UUID FK | |
| message_id | UUID FK → chat_messages.id, NULL | Liên kết tới message thực tế nếu route_type ≠ cache_hit thuần |
| cache_id | UUID FK → query_cache.id, NULL | Nếu route_type = cache_hit, trỏ tới entry cache đã khớp |
| query_text | TEXT | |
| route_type | ENUM('cache_hit','metadata','factoid','complex') | |
| llm_calls_count | INT | |
| model_used | VARCHAR NULL | |
| latency_ms | INT | |
| created_at | TIMESTAMP | |

---

## Các bảng không đổi so với v1

`users`, `workspaces`, `roles`, `workspace_members`, `entity_relations`, `topic_chunks`, `chat_sessions`, `summaries`, `extractions`, `comparisons`, `comparison_documents`, `reports`, `report_items` — mô tả chi tiết giữ nguyên như tài liệu v1 (`database-design-enterprise-notebooklm.md`).

## Ghi chú cập nhật

1. **Denormalize có kiểm soát:** `citations` không còn lưu `document_id` trực tiếp — muốn biết tài liệu nguồn phải join qua `retrieval → chunk → document_version → document`. Đánh đổi: query phức tạp hơn 1 bước JOIN, nhưng loại bỏ trùng lặp dữ liệu và tránh lệch dữ liệu khi chunk bị re-index.
2. **`message_generations` là 1–1 optional với `chat_messages`:** message role='user' sẽ không có dòng tương ứng.
3. **(v3) `agent_events` là 0–1 optional với `chat_messages`:** chỉ tồn tại khi `message_generations.agent_triggered=true` (Low Confidence). Không cần bảng riêng để đếm "0 lần agent" như cách xử lý của `message_generations` với route 0-LLM, vì đây là sự kiện thực sự tuỳ chọn (event-driven), không phải trạng thái cần thống kê đều cho mọi request.
4. **(v3) `retrievals.retrieval_pass`** cho phép 1 message có 2 lượt retrieval (pass 1 trước Confidence Engine, pass 2 sau Agent) — khi tính "Top-K context đưa vào Prompt Construction", luôn lấy `retrieval_pass` lớn nhất hiện có cho message đó (pass 2 nếu tồn tại, ngược lại pass 1).
5. Đề xuất index bổ sung: `document_versions(document_id, is_current)`, `pipeline_runs(document_version_id, status)`, `retrievals(message_id, rank)`, `retrievals(message_id, retrieval_pass)` *(mới v3)*, `agent_events(message_id)` *(mới v3)*, `document_chunks(parent_chunk_id)` *(mới v3)*, `query_cache(query_hash)` + `query_cache(workspace_id, expires_at)` cho tác vụ dọn cache hết hạn, `search_history(workspace_id, created_at)`, `topics(parent_topic_id)`.
