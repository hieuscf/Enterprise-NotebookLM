# Enterprise NotebookLM

> Hệ thống Web hỗ trợ **quản lý và khai thác tri thức** từ tài liệu doanh nghiệp dựa trên **Large Language Models (LLM)** và **Retrieval-Augmented Generation (RAG)**.

---

## Giới thiệu

Trong môi trường doanh nghiệp, tài liệu (hợp đồng, báo cáo, quy trình, chính sách…) ngày càng lớn và phân tán theo phòng ban/dự án. **Enterprise NotebookLM** giúp tập trung hóa Knowledge Base theo Workspace, hỗ trợ tìm kiếm ngữ nghĩa, hỏi–đáp có dẫn nguồn (Citation), tóm tắt/trích xuất, so sánh tài liệu và rà soát hợp đồng cấp điều khoản — đồng thời tối ưu chi phí LLM qua Query Router và Citation Verification.

---

## 🚀 Tính năng cốt lõi

### Phía Người dùng (Client)

- **Đăng nhập / Workspace** — Xác thực JWT; làm việc trong Workspace theo phòng ban/dự án với vai trò `admin` / `editor` / `viewer`.
- **Quản lý tài liệu** — Upload đa định dạng (PDF, DOCX, XLSX, PPTX, TXT); theo dõi pipeline xử lý (Document Understanding → Chunking → Embedding → Graph → Indexing).
- **Intelligent Search** — Hybrid Retrieval (Vector + BM25 + Knowledge Graph) + Cross-Encoder Re-ranking.
- **AI Chat có Citation** — Hỏi–đáp ngôn ngữ tự nhiên; câu trả lời kèm nguồn đã xác minh; highlight trên tài liệu gốc; streaming response.
- **AI Summary & Extraction** — Tóm tắt (ngắn / chi tiết / theo chủ đề / bullet) và trích xuất thông tin có cấu trúc (bảng, số liệu, thực thể, mốc thời gian).
- **So sánh tài liệu & Contract Comparison** — Đối chiếu ≥2 tài liệu; với cặp hợp đồng: phân tích cấp điều khoản (Added/Removed/Modified/Unchanged), rủi ro pháp lý và evidence đã kiểm chứng.
- **Báo cáo** — Tổng hợp tóm tắt / trích xuất / so sánh / chat thành file PDF, DOCX hoặc Markdown.
- **Conversation Memory** — Lưu và tiếp tục lịch sử hội thoại theo phiên.

### Phía Quản trị (Admin / Platform Manage)

- **Admin Dashboard** — Theo dõi health hệ thống, số lượng workspace/user/document, định tuyến truy vấn và chi phí LLM (biểu đồ / metric).
- **Quản lý Workspace & tài liệu** — Danh mục workspace, pipeline runs, documents ở phạm vi nền tảng.
- **Phân quyền** — Platform role `manage` cho `/admin`; RBAC theo Workspace (`admin` / `editor` / `viewer`).
- **Observability** — Query logs theo `route_type`, cost-summary theo model, tracing/logging (structlog + OpenTelemetry).

---

## 🛠️ Công nghệ sử dụng

| Thành phần                 | Công nghệ                                                                        |
| -------------------------- | -------------------------------------------------------------------------------- |
| **Frontend**               | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, shadcn/ui           |
| **Backend API**            | Python 3.11+, FastAPI, SQLAlchemy (async), Alembic, Pydantic                     |
| **Xác thực**               | OAuth2 / JWT; Platform Manage + Workspace RBAC                                   |
| **Task queue**             | Celery + Redis                                                                   |
| **RDBMS**                  | PostgreSQL 16                                                                    |
| **Vector DB**              | Qdrant                                                                           |
| **Full-text (BM25)**       | Elasticsearch                                                                    |
| **Knowledge Graph**        | Neo4j Community (+ LightRAG dual-level)                                          |
| **Object storage**         | MinIO (S3-compatible)                                                            |
| **Document Understanding** | LlamaParse (fallback OCR local)                                                  |
| **RAG / Retrieval**        | Hybrid Retrieval + Cross-Encoder Reranker + Query Router                         |
| **LLM**                    | OpenAI / Anthropic (chat & structured output; tối đa 1 LLM call / complex query) |
| **Triển khai**             | Docker + Docker Compose                                                          |
| **CI**                     | GitHub Actions (`ruff`, `black`, `pytest`, `eslint`, `next build`)               |

Kiến trúc chi tiết: `docs/System_Architecture_Enterprise_NotebookLM.md` · Hợp đồng API: `docs/Enterprise_notebooklm_openapi.yaml`.

---

## 📸 Hình ảnh giao diện

<p align="center"><b>Đăng nhập</b></p>
<p align="center">
  <img src="https://github.com/user-attachments/assets/ee536029-69f0-4894-92d8-d30e672be730" width="915" height="434" alt="Giao diện đăng nhập">
</p>

<p align="center"><b>Workspace</b></p>
<p align="center">
  <img src="https://github.com/user-attachments/assets/2c0bc99a-c2f6-4648-86a0-8018988e11ce" width="915" height="487" alt="Danh sách Workspace">
</p>

<p align="center"><b>AI Chat có Citation</b></p>
<p align="center">
  <img src="https://github.com/user-attachments/assets/5b292653-8092-47cc-9124-7211ca2b541a" width="915" height="480" alt="AI Chat với nguồn trích dẫn">
</p>

<p align="center"><b>Document Viewer (Citation highlight)</b></p>
<p align="center">
  <img src="https://github.com/user-attachments/assets/341e6ca3-11de-4d39-8bc0-1353abccbc32" width="915" height="478" alt="Xem tài liệu và highlight citation">
</p>

<p align="center"><b>Document / Contract Comparison</b></p>
<p align="center">
  <img src="https://github.com/user-attachments/assets/34c96efa-80fa-4367-afc7-9b89bf76a644" width="915" height="482" alt="So sánh tài liệu">
</p>

<p align="center"><b>Admin Dashboard</b></p>
<p align="center">
  <img src="https://github.com/user-attachments/assets/e87c673c-8e77-4241-8ba1-31904176d1bb" width="915" height="489" alt="Admin Observability Dashboard">
</p>

---

## 💻 Hướng dẫn cài đặt và Chạy thử (Local Setup)

### Yêu cầu môi trường

- [Git](https://git-scm.com/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) / Docker Engine + **Compose v2**
- RAM khuyến nghị: **≥ 8–16 GB** (nhiều container chạy đồng thời)
- API key (tùy chọn nhưng cần cho đầy đủ chức năng AI):
  - `OPENAI_API_KEY` (hoặc Anthropic nếu cấu hình `CHAT_LLM_PROVIDER=anthropic`)
  - `LLAMAPARSE_API_KEY` (Document Understanding; có thể fallback local OCR)

### 1. Clone mã nguồn

```bash
git clone https://github.com/hieuscf/Enterprise-NotebookLM.git
cd Enterprise-NotebookLM
```

### 2. Cấu hình biến môi trường

```bash
# Linux / macOS
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Các biến quan trọng trong `.env`:

| Nhóm           | Biến                                    | Ghi chú                                            |
| -------------- | --------------------------------------- | -------------------------------------------------- |
| Auth           | `JWT_SECRET_KEY`                        | Đổi trước khi dùng môi trường chia sẻ              |
| Chat LLM       | `CHAT_LLM_PROVIDER`, `OPENAI_API_KEY`   | Mặc định provider `openai`                         |
| Document parse | `DOCUMENT_PARSER`, `LLAMAPARSE_API_KEY` | `llamaparse` hoặc `local`                          |
| Bootstrap      | `BOOTSTRAP_MANAGE_EMAIL`                | (Tuỳ chọn) promote user sẵn có lên Platform Manage |

Giá trị Postgres / Redis / MinIO / Neo4j mặc định trong `.env.example` đủ dùng cho local.

### 3. Khởi động hạ tầng và ứng dụng

```bash
docker compose up -d --build
```

`docker-compose.override.yml` (auto-merge) bật hot reload (`uvicorn --reload`, `next dev`) cho môi trường phát triển.

### 4. Khởi tạo schema PostgreSQL

```bash
docker compose exec backend-api alembic upgrade head
```

### 5. Tạo tài khoản Platform Manage (lần đầu)

```bash
docker compose exec backend-api python -m scripts.create_manage_user \
  --email admin@example.com \
  --password "YourStrongPassword" \
  --full-name "Platform Manager"
```

### 6. Kiểm tra nhanh

```bash
docker compose ps
curl -i http://localhost:8000/health
```

Kỳ vọng: các service `healthy` (MinIO init có thể `Exited 0`), `GET /health` → `200` kèm header `X-Request-ID`.

### URL local

| Service              | URL                                                 |
| -------------------- | --------------------------------------------------- |
| Frontend (Next.js)   | http://localhost:3000                               |
| Backend API / health | http://localhost:8000/health                        |
| MinIO Console        | http://localhost:9001 (`minioadmin` / `minioadmin`) |
| Neo4j Browser        | http://localhost:7474                               |
| Qdrant Dashboard     | http://localhost:6333/dashboard                     |
| Elasticsearch        | http://localhost:9200                               |

### Luồng dùng thử cơ bản

1. Mở http://localhost:3000 → đăng nhập bằng tài khoản Manage vừa tạo.
2. Tạo Workspace → mời thành viên (`admin` / `editor` / `viewer`).
3. Vào **Documents** → upload file → theo dõi pipeline đến khi `ready`.
4. Khai thác: **Search**, **Chat** (có citation), **Summary / Extraction**, **Comparison**, **Report**.
5. (Manage) vào `/admin` để xem Dashboard, query logs, cost summary.

### Checklist dịch vụ

| Service       | Kiểm tra nhanh                                          |
| ------------- | ------------------------------------------------------- |
| postgres      | `docker compose exec postgres pg_isready -U notebooklm` |
| redis         | `docker compose exec redis redis-cli ping` → `PONG`     |
| qdrant        | `curl http://localhost:6333/readyz`                     |
| elasticsearch | `curl http://localhost:9200/_cluster/health`            |
| minio         | `curl http://localhost:9000/minio/health/live`          |
| backend-api   | `curl -i http://localhost:8000/health`                  |
| celery-worker | `docker compose logs celery-worker --tail 20`           |
| frontend      | mở http://localhost:3000                                |

### Chạy kiểm thử / lint (tùy chọn)

```bash
# Backend
cd backend && ruff check . && black --check . && pytest -q

# Frontend
cd frontend && npm ci && npm run lint && npm run build
```

---

## Cấu trúc monorepo

```text
backend/                 # FastAPI + Celery workers + Alembic
  app/
    api/                 # Routers (Presentation)
    services/            # Business logic
    repositories/        # Data access
    adapters/            # LLM, Qdrant, ES, Neo4j, MinIO, …
    workers/             # Celery pipeline tasks
  alembic/
  tests/
frontend/                # Next.js App Router + Tailwind + shadcn/ui
assets/readme/           # Ảnh giao diện cho README
docker-compose.yml
docker-compose.override.yml
.env.example
.github/workflows/ci.yml
docs/                    # Tài liệu thiết kế / OpenAPI (local)
```

---

## Điểm nổi bật kỹ thuật

- **Query Router** — Phân loại cache / metadata / section / factoid / complex; nhiều nhánh **0 lần gọi LLM**.
- **Complex Query** — Hybrid Retrieval → Rerank → Confidence Engine → tối đa **1 lần LLM** (structured output) + Citation Verification deterministic.
- **Contract Comparison** — Deterministic clause mapping/diff trước, LLM giải thích sau; gắn evidence đã kiểm chứng.
- **Multi-tenant** — Mọi truy vấn dữ liệu lọc theo `workspace_id`; chỉ `backend-api` gọi LLM chat provider.

---

## Tài liệu tham chiếu

- `docs/Business_Context.md` — Mục tiêu, Use Case, Functional Requirements
- `docs/Enterprise_NotebookLM.md` — 10 module chức năng & Query Router
- `docs/System_Architecture_Enterprise_NotebookLM.md` — C4 + Sequence
- `docs/database-design-enterprise-notebooklm.md` — Schema
- `docs/Enterprise_notebooklm_openapi.yaml` — Hợp đồng API
- `docs/Đồ án Enteprise_NotebookLM.docx` — Báo cáo đồ án đầy đủ

---

## Giấy phép

Đồ án tốt nghiệp — sử dụng cho mục đích học tập và nghiên cứu. Liên hệ tác giả nếu cần tái sử dụng ngoài phạm vi học thuật.
