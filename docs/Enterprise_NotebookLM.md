**Enterprise NotebookLM**

Phát triển hệ thống Web thông minh hỗ trợ quản lý, phân tích và khai thác tri thức từ tài liệu doanh nghiệp dựa trên Large Language Models (LLM) và Retrieval-Augmented Generation (RAG).

# 1\. Mục tiêu nghiên cứu

## 1\.1 Mục tiêu tổng quát

Xây dựng một hệ thống Web cho phép doanh nghiệp lưu trữ, quản lý và khai thác tri thức từ nhiều loại tài liệu bằng công nghệ LLM và RAG.

## 1\.2 Mục tiêu cụ thể

- Quản lý nhiều Workspace theo phòng ban hoặc dự án.
- Hỗ trợ nhiều định dạng tài liệu (PDF, DOCX, XLSX, PPTX, TXT...).
- Tự động xây dựng kho tri thức (Knowledge Base).
- Hỏi đáp dựa trên RAG với dẫn nguồn (Citation).
- Tóm tắt tài liệu theo nhiều dạng.
- Trích xuất thông tin có cấu trúc.
- So sánh nhiều tài liệu.
- Tìm kiếm ngữ nghĩa bằng Hybrid Retrieval.
- Quản trị người dùng, phân quyền và bảo mật dữ liệu theo từng Workspace.

# 2\. Các module chức năng

## Module 1. Workspace Management

Mỗi doanh nghiệp có thể tạo nhiều Workspace theo phòng ban/dự án. Mỗi Workspace quản lý riêng: tài liệu, lịch sử chat, người dùng và quyền truy cập.

## Module 2. Knowledge Base

Tự động xử lý tài liệu đầu vào (PDF/DOCX/XLSX/PPTX/TXT) qua **Document Understanding** bằng **LlamaParse**: xuất trực tiếp ra Markdown, đồng thời sinh song song Layout Analysis (cấu trúc heading/bảng/section) và Metadata Extraction (trích xuất từ chính cấu trúc Markdown, không cần bước OCR riêng). Sau đó **Cleaning & Normalize** nội dung Markdown, rồi **Hierarchical Chunking** (chia theo cấu trúc phân cấp section → sub-section → đoạn văn, giữ quan hệ cha-con giữa chunk). Cuối cùng nạp vào **LightRAG Core Engine** (Entity Extraction, Relation Extraction, Graph Construction, Embedding Generation) để tạo kho tri thức có cấu trúc, index song song vào 4 kho: BM25 Index, Vector DB, Graph DB, Metadata DB — phục vụ truy hồi theo nhiều cấp độ (thực thể, chủ đề, đoạn văn bản).

## Module 3. Intelligent Search

Tìm kiếm ngữ nghĩa kết hợp Hybrid Retrieval (Vector Search + BM25 + Knowledge Graph + Metadata DB) và lớp Cross-Encoder Reranking để trả về kết quả liên quan nhất. Với luồng AI Chat (Module 4), kết quả sau rerank còn đi qua Confidence Engine để quyết định có cần Micro Agent hỗ trợ hay không (xem mục 6, 7).

## Module 4. AI Chat

Giao diện hội thoại cho phép người dùng đặt câu hỏi tự nhiên; hệ thống dựng prompt từ ngữ cảnh truy hồi được và sinh câu trả lời bằng LLM.

## Module 5. Citation

Mỗi câu trả lời được gắn kèm trích dẫn nguồn (đoạn văn bản, trang, tài liệu gốc) và cho phép highlight trực tiếp trên tài liệu.

## Module 6. AI Summary

Tóm tắt tài liệu theo nhiều dạng: tóm tắt ngắn, tóm tắt chi tiết, tóm tắt theo chủ đề, tóm tắt dạng bullet point.

## Module 7. Information Extraction

Trích xuất thông tin có cấu trúc (bảng biểu, số liệu, thực thể, mốc thời gian...) từ tài liệu phi cấu trúc, xuất ra dạng JSON/bảng.

## Module 8. Multi-document Analysis

So sánh, đối chiếu và tổng hợp thông tin từ nhiều tài liệu cùng lúc, làm nổi bật điểm giống/khác nhau.

## Module 9. Report Generation & Export

Tổng hợp kết quả (tóm tắt, trích xuất, so sánh, hội thoại) thành báo cáo có định dạng (PDF/DOCX/Markdown) và cho phép xuất/tải về hoặc chia sẻ trong Workspace. (Đề xuất bổ sung — có thể điều chỉnh nếu nhóm có định hướng khác, ví dụ: Analytics Dashboard hoặc Notification Center.)

## Module 10. Conversation Memory

Lưu trữ và quản lý lịch sử hội thoại theo phiên và theo người dùng, cho phép tiếp tục ngữ cảnh cũ và tham chiếu lại các câu hỏi/trả lời trước đó.

# 3\. Kiến trúc hệ thống (System Architecture)

Luồng xử lý tổng quát (v3):

**Ingestion (nạp tài liệu):**
- User → Enterprise Workspace → Document Management → Upload
- Upload → Document Understanding (**LlamaParse**) → 3 nhánh song song: Markdown, Layout Analysis, Metadata Extraction
- 3 nhánh → Cleaning & Normalize → Hierarchical Chunking
- Hierarchical Chunking → LightRAG Engine (Entity Extraction, Relation Extraction, Graph Construction, Embedding Generation)
- LightRAG Engine → index song song 4 kho: BM25 Index, Vector DB, Graph DB, Metadata DB

**Query (hỏi đáp):**
- User Query → Query Router (cache/metadata/factoid/complex, không dùng LLM — xem mục 6)
- Nếu **Complex Query** → Hybrid Retrieval (Vector + BM25 + Knowledge Graph + Metadata) → Cross-Encoder Reranker
- Reranker → Confidence Engine → phân nhánh:
  - **High Confidence** → Prompt Builder → 1 lần gọi LLM (structured output)
  - **Low Confidence** → Event Policy Engine → kích hoạt 1 trong 3 Micro Agent (Rewrite Agent / Graph Agent / SQL Agent) theo sự kiện → Second Retrieval (tuỳ chọn) → Prompt Builder → 1 lần gọi LLM
- LLM → Citation Verification → Enterprise NotebookLM UI (Citation & Highlight)

Chi tiết đầy đủ hai luồng trên xem sơ đồ C4 + Sequence trong `System_Architecture_Enterprise_NotebookLM.md`.

# 4\. Tech Stack đề xuất

Dựa trên lựa chọn của nhóm: Backend Python (FastAPI) + Frontend Next.js/React.

| **Thành phần**         | **Công nghệ đề xuất**                           | **Ghi chú**                                        |
| :--------------------- | :---------------------------------------------- | :------------------------------------------------- |
| Frontend               | Next.js (React) + TailwindCSS + shadcn/ui       | SSR cho tốc độ tải, streaming response cho AI Chat |
| Backend API            | Python 3.11+ / FastAPI                          | Async, tích hợp tốt với thư viện AI/ML Python      |
| Xác thực & phân quyền  | OAuth2 / JWT; Platform Manage + Workspace RBAC  | `manage` → `/admin`; `admin/editor/viewer` theo Workspace |
| RAG Orchestration      | LightRAG / LlamaIndex hoặc LangChain            | Xây Knowledge Graph + Vector Index song song       |
| Vector Database        | Qdrant hoặc pgvector (PostgreSQL)               | Lưu embedding phục vụ Vector Retrieval             |
| Knowledge Graph        | Neo4j hoặc NetworkX + lưu trữ tuỳ biến          | Phục vụ Low/High-Level Retrieval                   |
| Full-text Search       | Elasticsearch / OpenSearch (BM25)               | Kết hợp Hybrid Retrieval                           |
| Document Understanding | **LlamaParse**                                  | Parse PDF/DOCX/XLSX/PPTX/TXT trực tiếp ra Markdown + Layout Analysis + Metadata Extraction (thay thế OCR & Cleaning tổng quát ở bản trước) |
| Reranking              | Cross-encoder model (non-LLM)                   | Re-ranking Layer, đầu vào cho Confidence Engine    |
| LLM Provider           | Anthropic ChatGPT API (qua SDK)                 | Sinh câu trả lời, tóm tắt, trích xuất              |
| Hàng đợi tác vụ nền    | Celery + Redis                                  | Xử lý OCR, indexing bất đồng bộ                    |
| Cơ sở dữ liệu chính    | PostgreSQL                                      | Metadata, người dùng, Workspace, lịch sử chat      |
| Lưu trữ file           | S3-compatible (MinIO)                           | Lưu tài liệu gốc                                   |
| Triển khai             | Docker + Docker Compose                         |                                                    |

# 5\. Yêu cầu phi chức năng (tóm tắt)

- Bảo mật: mã hoá dữ liệu tại chỗ và khi truyền, phân quyền chặt theo Workspace.
- Khả năng mở rộng: kiến trúc microservice-ready, tách rời indexing và truy vấn.
- Hiệu năng: streaming response cho AI Chat, cache kết quả truy hồi thường xuyên.
- Khả năng quan sát: logging, tracing cho pipeline RAG để debug chất lượng câu trả lời.

# 6\. Tối ưu Pipeline & Giảm số lần gọi LLM

Vấn đề: không phải câu hỏi nào cũng cần đến LLM. Gọi LLM cho mọi truy vấn (kể cả re-ranking, format câu trả lời, sinh citation) làm tăng chi phí, độ trễ và rủi ro sai lệch. Giải pháp: thêm một lớp Query Router đứng trước pipeline RAG để phân loại truy vấn và chỉ gọi LLM khi thực sự cần.

## 6\.1 Query Router (lớp định tuyến truy vấn)

Router hoạt động bằng rule-based matching + embedding similarity classifier (không dùng LLM), phân loại truy vấn thành 4 nhóm:

- Cache Hit — truy vấn trùng/tương tự truy vấn đã trả lời trước (semantic cache) → trả lời ngay từ cache kèm citation gốc. 0 lần gọi LLM.
- Structured/Metadata Query — câu hỏi dạng liệt kê, lọc, thống kê (vd. "có bao nhiêu tài liệu trong workspace X") → truy vấn trực tiếp database. 0 lần gọi LLM.
- Simple Factoid — câu hỏi có câu trả lời khớp trực tiếp với 1 đoạn (chunk) với độ tin cậy cao từ Retrieval → trả lời dạng trích xuất (extractive), không cần LLM sinh văn bản. 0 lần gọi LLM.
- Complex Query — câu hỏi cần tổng hợp, suy luận, so sánh nhiều nguồn → đi qua pipeline RAG đầy đủ, tối đa 1 lần gọi LLM (xem 6.2).

## 6\.2 Gộp các bước để tối đa 1 lần gọi LLM cho truy vấn phức tạp

Pipeline cũ có thể phát sinh nhiều lần gọi LLM riêng lẻ (re-ranking bằng LLM, sinh câu trả lời, format citation). Pipeline tối ưu gộp lại:

- Re-ranking dùng cross-encoder model chuyên biệt (không phải LLM) để xếp hạng lại kết quả truy hồi.
- Prompt Construction yêu cầu LLM trả về structured output (JSON: answer + danh sách citation id) trong một lần gọi duy nhất, thay vì tách riêng bước sinh câu trả lời và bước gắn citation.
- Model tiering: dùng model nhỏ/rẻ (vd. Claude Haiku) cho câu hỏi đơn giản cần LLM nhẹ, dùng model mạnh hơn (vd. Claude Sonnet) chỉ cho truy vấn thực sự phức tạp.

## 6\.3 So sánh trước và sau tối ưu

| **Loại truy vấn**                    | **Số lần gọi LLM (trước)**           | **Số lần gọi LLM (sau)**  |
| :----------------------------------- | :----------------------------------- | :------------------------ |
| Truy vấn lặp lại / đã cache          | 1-3 lần                              | 0 lần                     |
| Truy vấn liệt kê/thống kê metadata   | 1-2 lần                              | 0 lần                     |
| Câu hỏi factoid đơn giản             | 1-2 lần                              | 0 lần                     |
| Câu hỏi phức tạp — High Confidence   | 2-4 lần (rerank + generate + format) | 1 lần (structured output) |
| Câu hỏi phức tạp — Low Confidence    | 2-4 lần                              | tối đa 1 lần LLM sinh câu trả lời + agent (non-LLM/model nhẹ) + tối đa 1 lần Second Retrieval |

## 6\.4 Confidence Engine & Event Policy Engine (chỉ áp dụng trong nhánh Complex Query)

Vấn đề bổ sung: không phải mọi kết quả sau rerank đều đủ tốt để LLM trả lời trực tiếp — nếu độ tin cậy thấp mà vẫn ép LLM sinh câu trả lời ngay, rủi ro "không đủ căn cứ" ở bước Citation Verification (7.1) tăng, gây nhiều lần fallback. Giải pháp: chèn một bước đánh giá độ tin cậy **trước** khi vào Prompt Construction, và chỉ khi cần mới huy động thêm agent — đúng nguyên tắc **event-driven**: agent không nằm trên đường đi mặc định của mọi truy vấn.

- **Confidence Engine**: tính confidence score từ kết quả Cross-Encoder Reranker (vd. dựa trên score cao nhất, độ phân tán điểm giữa các candidate, số lượng candidate vượt ngưỡng). Phân loại High Confidence / Low Confidence theo ngưỡng cấu hình được.
- **High Confidence** → đi thẳng Prompt Construction như 6.2 (không đổi).
- **Low Confidence** → **Event Policy Engine** nhận diện loại sự kiện và chọn agent tương ứng:
  - **Rewrite Agent** — sự kiện: câu hỏi mơ hồ/thiếu ngữ cảnh (điểm rerank thấp đều, không có candidate nổi bật) → viết lại câu hỏi rõ ràng hơn.
  - **Graph Agent** — sự kiện: câu hỏi cần suy luận quan hệ nhiều bước (multi-hop) mà Vector/BM25 không phủ đủ → mở rộng truy vấn qua Knowledge Graph.
  - **SQL Agent** — sự kiện: câu hỏi thực chất là structured/thống kê nhưng bị Query Router (6.1) phân loại nhầm thành Complex → truy vấn trực tiếp Metadata DB.
- **Second Retrieval (tuỳ chọn)**: sau khi agent trả về câu hỏi viết lại hoặc ngữ cảnh bổ sung, hệ thống chạy lại Hybrid Retrieval một lần nữa, rồi mới vào Prompt Construction.
- Agent dùng model nhỏ/rule-based, **không tính** vào giới hạn "tối đa 1 lần gọi LLM sinh câu trả lời cuối" ở mục 6.2 — giới hạn đó chỉ áp dụng cho bước Prompt Construction cuối cùng.
- Mọi lượt kích hoạt agent đều được ghi log (loại agent, lý do, có Second Retrieval hay không) phục vụ Observability (mục 7.2).

# 7\. Đảm bảo câu trả lời có đường dẫn xác thực (Verifiable Citation)

Yêu cầu bắt buộc ở tầng kiến trúc: mọi câu trả lời do LLM sinh ra phải được kiểm chứng bằng nguồn trước khi trả về người dùng — không chỉ là một tính năng hiển thị, mà là một bước kiểm soát trong pipeline.

## 7\.1 Citation Verification Layer

- LLM buộc phải sinh câu trả lời kèm citation id tham chiếu đến chunk/tài liệu gốc trong ngữ cảnh được cấp (ép buộc qua structured output/function calling).
- Sau khi LLM trả lời, một bước kiểm tra xác định (deterministic, không dùng LLM) đối chiếu từng citation id với danh sách chunk đã truy hồi.
- Nếu có phần nội dung không có citation hợp lệ → hệ thống từ chối trả lời phần đó, hoặc trả về "không đủ căn cứ trong tài liệu" thay vì suy đoán.
- Mỗi citation phải trỏ được đến vị trí xác thực: tên tài liệu, số trang/đoạn, và đoạn văn bản gốc để highlight trực tiếp trên UI.

## 7\.2 Vị trí trong kiến trúc tổng thể

Query Router, Confidence Engine, Event Policy Engine (+ Micro Agents) và Citation Verification Layer được triển khai như một Query Orchestration Service độc lập, nằm giữa Enterprise NotebookLM UI và LightRAG Core Engine, đạt chuẩn kiến trúc enterprise:

- Stateless, có thể scale ngang độc lập với các service khác.
- Ghi log toàn bộ quyết định định tuyến và số lần gọi LLM theo từng request để phục vụ audit và theo dõi chi phí (cost observability).
- Có cơ chế fallback/circuit breaker khi LLM provider lỗi hoặc chậm.
- Áp dụng rate limiting theo Workspace để tránh một Workspace chiếm hết tài nguyên LLM.

## 7\.3 Luồng xử lý cập nhật

- User Query → Query Router (rule-based + embedding classifier, 0 LLM)
- → [Cache Hit] Trả lời ngay kèm citation gốc
- → [Metadata Query] Truy vấn DB trực tiếp
- → [Simple Factoid] Trích xuất trực tiếp từ chunk, không sinh văn bản
- → [Complex Query] Hybrid Retrieval → Cross-encoder Re-ranking (non-LLM) → **Confidence Engine**
  - → [High Confidence] Prompt Construction → 1 LLM Call (structured output: answer + citation ids)
  - → [Low Confidence] Event Policy Engine → Rewrite/Graph/SQL Agent (theo sự kiện) → Second Retrieval (tuỳ chọn) → Prompt Construction → 1 LLM Call
- → Citation Verification Layer (deterministic check) → nếu không đạt: fallback "không đủ căn cứ" hoặc sinh lại tối đa 1 lần
- → Trả lời kèm Citation & Highlight → Enterprise NotebookLM UI
