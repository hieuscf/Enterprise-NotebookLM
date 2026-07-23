# Business Context — Enterprise NotebookLM

> Hệ thống Web thông minh hỗ trợ quản lý, phân tích và khai thác tri thức từ tài liệu doanh nghiệp, dựa trên Large Language Models (LLM) và Retrieval-Augmented Generation (RAG).

---

## 1. Mục tiêu

### 1.1 Mục tiêu tổng quát

Xây dựng một hệ thống Web cho phép doanh nghiệp lưu trữ, quản lý và khai thác tri thức từ nhiều loại tài liệu bằng công nghệ LLM và RAG, giúp nhân viên/phòng ban tìm kiếm, tổng hợp và trích xuất thông tin nhanh chóng, chính xác, có thể kiểm chứng nguồn.

### 1.2 Mục tiêu cụ thể

- Quản lý nhiều Workspace theo phòng ban hoặc dự án.
- Hỗ trợ nhiều định dạng tài liệu (PDF, DOCX, XLSX, PPTX, TXT...).
- Tự động xây dựng kho tri thức (Knowledge Base) có cấu trúc.
- Hỏi đáp dựa trên RAG, có dẫn nguồn (Citation) rõ ràng, xác thực được.
- Tóm tắt tài liệu theo nhiều dạng (ngắn, chi tiết, theo chủ đề, bullet point).
- Trích xuất thông tin có cấu trúc (bảng biểu, số liệu, thực thể, mốc thời gian).
- So sánh và đối chiếu nhiều tài liệu cùng lúc.
- Tìm kiếm ngữ nghĩa bằng Hybrid Retrieval (Vector + BM25 + Knowledge Graph).
- Quản trị người dùng, phân quyền và bảo mật dữ liệu theo từng Workspace.
- Tối ưu chi phí và độ trễ bằng cách giảm số lần gọi LLM không cần thiết (Query Router).

---

## 2. Phạm vi (Scope)

### 2.1 Trong phạm vi (In-scope)

- Quản lý Workspace theo phòng ban/dự án (tài liệu, người dùng, lịch sử chat, quyền truy cập riêng biệt).
- Nạp và xử lý tài liệu đa định dạng: OCR & Cleaning → LightRAG Core Engine (Dual-level Graph + Vector Index).
- Truy hồi tri thức nhiều cấp độ: thực thể (Entities), chủ đề (Topics), đoạn văn bản (Chunks/Vector).
- Giao diện hội thoại AI Chat với streaming response.
- Cơ chế Citation & Highlight trực tiếp trên tài liệu gốc.
- Sinh báo cáo tổng hợp và xuất file (PDF/DOCX/Markdown).
- Lưu trữ và quản lý lịch sử hội thoại (Conversation Memory).
- Lớp Query Router và Citation Verification Layer nhằm kiểm soát chi phí và đảm bảo độ tin cậy câu trả lời.
- Xác thực, phân quyền (OAuth2/JWT, RBAC theo Workspace), mã hoá dữ liệu tại chỗ và khi truyền.

### 2.2 Ngoài phạm vi (Out-of-scope) / Đề xuất mở rộng sau

- Analytics Dashboard chuyên sâu (đề xuất bổ sung, chưa xác định phạm vi cụ thể).
- Notification Center (đề xuất bổ sung, chưa xác định phạm vi cụ thể).
- Tích hợp với hệ thống bên thứ ba ngoài lưu trữ file (ERP, CRM...) — chưa được đề cập trong tài liệu gốc.
- Ứng dụng di động (mobile app) — chưa được đề cập.

_(Ghi chú: tài liệu gốc chưa xác định rõ ràng giới hạn phạm vi này; nhóm dự án cần chốt lại trước khi triển khai.)_

---

## 3. Use Case

| #    | Use Case                                      | Actor              | Mô tả                                                                                                                        |
| ---- | --------------------------------------------- | ------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| UC1  | Tạo/quản lý Workspace                         | Admin doanh nghiệp | Tạo Workspace theo phòng ban/dự án; quản lý tài liệu, người dùng, quyền truy cập riêng cho từng Workspace                    |
| UC2  | Tải lên & xử lý tài liệu                      | Người dùng nội bộ  | Upload tài liệu (PDF/DOCX/XLSX/PPTX/TXT); hệ thống tự động OCR, chuẩn hoá và nạp vào Knowledge Base                          |
| UC3  | Tìm kiếm ngữ nghĩa                            | Người dùng nội bộ  | Nhập truy vấn tìm kiếm; hệ thống trả kết quả qua Hybrid Retrieval + Re-ranking                                               |
| UC4  | Hỏi đáp AI (Chat với dẫn nguồn)               | Người dùng nội bộ  | Đặt câu hỏi tự nhiên; nhận câu trả lời kèm citation, có thể click để xem đoạn văn bản gốc                                    |
| UC5  | Tóm tắt tài liệu                              | Người dùng nội bộ  | Yêu cầu tóm tắt (ngắn/chi tiết/theo chủ đề/bullet) cho một hoặc nhiều tài liệu                                               |
| UC6  | Trích xuất thông tin có cấu trúc              | Người dùng nội bộ  | Trích xuất bảng biểu, số liệu, thực thể, mốc thời gian ra JSON/bảng                                                          |
| UC7  | So sánh nhiều tài liệu                        | Người dùng nội bộ  | Chọn ≥2 tài liệu; hệ thống làm nổi bật điểm giống/khác nhau                                                                  |
| UC8  | Sinh & xuất báo cáo                           | Người dùng nội bộ  | Tổng hợp kết quả (tóm tắt/trích xuất/so sánh/hội thoại) thành báo cáo PDF/DOCX/Markdown, tải về hoặc chia sẻ trong Workspace |
| UC9  | Xem lại lịch sử hội thoại                     | Người dùng nội bộ  | Truy cập lại phiên chat trước đó, tiếp tục ngữ cảnh cũ                                                                       |
| UC10 | Phân quyền & quản trị bảo mật                 | Admin doanh nghiệp | Cấu hình vai trò (RBAC), kiểm soát truy cập dữ liệu theo từng Workspace                                                      |
| UC11 | Kiểm chứng câu trả lời (hệ thống)             | Hệ thống (nội bộ)  | Sau khi LLM trả lời, đối chiếu citation id với chunk đã truy hồi; từ chối/fallback nếu không đủ căn cứ                       |
| UC12 | Định tuyến truy vấn tối ưu chi phí (hệ thống) | Hệ thống (nội bộ)  | Query Router phân loại truy vấn (cache/metadata/factoid/complex) để giảm số lần gọi LLM                                      |

---

## 4. Yêu cầu chức năng (Functional Requirements)

### FR1 — Workspace Management

- Tạo, sửa, xoá Workspace theo phòng ban/dự án.
- Mỗi Workspace quản lý độc lập: tài liệu, lịch sử chat, người dùng, quyền truy cập.

### FR2 — Knowledge Base

- Xử lý tự động tài liệu đầu vào đa định dạng (PDF/DOCX/XLSX/PPTX/TXT) qua OCR & Cleaning.
- Nạp dữ liệu vào LightRAG Core Engine (Dual-level Graph + Vector Index).
- Hỗ trợ truy hồi nhiều cấp độ: thực thể, chủ đề, đoạn văn bản.

### FR3 — Intelligent Search

- Tìm kiếm ngữ nghĩa kết hợp Vector Search + BM25 + Knowledge Graph (Hybrid Retrieval).
- Áp dụng lớp Re-ranking (cross-encoder, không dùng LLM) để tăng độ liên quan kết quả.

### FR4 — AI Chat

- Giao diện hội thoại tự nhiên.
- Dựng prompt từ ngữ cảnh truy hồi được, sinh câu trả lời bằng LLM.
- Hỗ trợ streaming response.

### FR5 — Citation

- Gắn kèm trích dẫn nguồn (đoạn văn bản, trang, tài liệu gốc) cho mỗi câu trả lời.
- Cho phép highlight trực tiếp trên tài liệu.
- Citation Verification Layer kiểm tra xác định (deterministic) từng citation id trước khi trả kết quả; từ chối hoặc trả "không đủ căn cứ" nếu không hợp lệ.

### FR6 — AI Summary

- Tóm tắt tài liệu theo nhiều dạng: ngắn, chi tiết, theo chủ đề, bullet point.

### FR7 — Information Extraction

- Trích xuất thông tin có cấu trúc (bảng biểu, số liệu, thực thể, mốc thời gian) từ tài liệu phi cấu trúc.
- Xuất kết quả ra JSON hoặc bảng.

### FR8 — Multi-document Analysis

- So sánh, đối chiếu, tổng hợp thông tin từ nhiều tài liệu cùng lúc.
- Làm nổi bật điểm giống/khác nhau giữa các tài liệu.

### FR9 — Report Generation & Export

- Tổng hợp kết quả (tóm tắt, trích xuất, so sánh, hội thoại) thành báo cáo có định dạng.
- Hỗ trợ xuất PDF/DOCX/Markdown; tải về hoặc chia sẻ trong Workspace.

### FR10 — Conversation Memory

- Lưu trữ và quản lý lịch sử hội thoại theo phiên và theo người dùng.
- Cho phép tiếp tục ngữ cảnh cũ, tham chiếu lại câu hỏi/trả lời trước đó.

### FR11 — Query Router (tối ưu chi phí LLM)

- Phân loại truy vấn thành 4 nhóm bằng rule-based + embedding similarity (không dùng LLM):
  - **Cache Hit**: trả lời ngay từ cache kèm citation gốc — 0 lần gọi LLM.
  - **Structured/Metadata Query**: truy vấn trực tiếp database — 0 lần gọi LLM.
  - **Simple Factoid**: trả lời extractive từ chunk có độ tin cậy cao — 0 lần gọi LLM.
  - **Complex Query**: đi qua pipeline RAG đầy đủ — tối đa 1 lần gọi LLM (structured output: answer + citation ids).
- Áp dụng model tiering (model nhỏ cho câu hỏi đơn giản, model mạnh hơn cho truy vấn phức tạp).

### FR12 — User Management & Access Control

- Xác thực OAuth2/JWT.
- Phân quyền RBAC theo Workspace (multi-tenant).
- Rate limiting theo Workspace để tránh một Workspace chiếm hết tài nguyên LLM.

### FR13 — Observability & Reliability

- Ghi log toàn bộ quyết định định tuyến và số lần gọi LLM theo từng request (phục vụ audit, cost observability).
- Cơ chế fallback/circuit breaker khi LLM provider lỗi hoặc chậm.

---

## 5. Yêu cầu phi chức năng (tóm tắt, tham chiếu)

- **Bảo mật**: mã hoá dữ liệu tại chỗ và khi truyền; phân quyền chặt theo Workspace.
- **Khả năng mở rộng**: kiến trúc microservice-ready, tách rời indexing và truy vấn.
- **Hiệu năng**: streaming response cho AI Chat; cache kết quả truy hồi thường xuyên.
- **Khả năng quan sát**: logging, tracing cho pipeline RAG để debug chất lượng câu trả lời.

---

## 6. Ghi chú

- Module 9 (Report Generation & Export) là đề xuất bổ sung của nhóm, có thể điều chỉnh thay bằng Analytics Dashboard hoặc Notification Center tuỳ định hướng dự án.
- Tech stack đề xuất: Backend Python/FastAPI, Frontend Next.js/React, Vector DB (Qdrant/pgvector), Knowledge Graph (Neo4j/NetworkX), Full-text Search (Elasticsearch/OpenSearch), LLM Provider: Anthropic ChatGPT API — chi tiết xem tài liệu gốc _Enterprise NotebookLM v3_.
