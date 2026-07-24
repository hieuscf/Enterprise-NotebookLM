# Enterprise NotebookLM

Hệ thống Web quản lý / khai thác tri thức doanh nghiệp bằng LLM + RAG.

## Quick start (Giai đoạn 1.1)

```bash
# 1) Secrets / env
cp .env.example .env

# 2) Hạ tầng + app containers
docker compose up -d --build

# 3) Schema PostgreSQL v2
docker compose exec backend-api alembic upgrade head

# 4) Kiểm tra
docker compose ps
curl -i http://localhost:8000/health
```

Kỳ vọng: toàn bộ service `healthy` (minio-init `Exited 0`), `GET /health` → `200` + header `X-Request-ID`, log JSON có `request_id` / `route` / `latency_ms`.

## Cấu trúc monorepo

```text
backend/
  app/
    api/          # FastAPI routers (Presentation; = "routers/" trong architecture rules)
    core/         # config, security, logging, tracing
    db/           # session, Base
    models/       # SQLAlchemy schema v2
    schemas/      # Pydantic
    services/     # business logic (GĐ sau)
    workers/      # Celery tasks (GĐ sau)
    main.py
  alembic/
  tests/
  Dockerfile
frontend/         # Next.js App Router + TailwindCSS + shadcn/ui
docker-compose.yml
docker-compose.override.yml   # local hot reload (auto-merge)
.env.example
.github/workflows/ci.yml
```

## URLs local

| Service | URL |
|---------|-----|
| API health | http://localhost:8000/health |
| Frontend (Next.js **dev**) | http://localhost:3000 |
| MinIO console | http://localhost:9001 (`minioadmin` / `minioadmin`) |
| Neo4j browser | http://localhost:7474 |
| Qdrant | http://localhost:6333/dashboard |
| Elasticsearch | http://localhost:9200 |

`docker-compose.override.yml` bật volume mount + `uvicorn --reload` + `next dev`.  
Chạy không override: `docker compose -f docker-compose.yml up -d`.

## Checklist dịch vụ

| Service | Kiểm tra nhanh |
|---------|----------------|
| postgres | `docker compose exec postgres pg_isready -U notebooklm` |
| redis | `docker compose exec redis redis-cli ping` → PONG |
| qdrant | `curl http://localhost:6333/readyz` |
| elasticsearch | `curl http://localhost:9200/_cluster/health` |
| minio | `curl http://localhost:9000/minio/health/live` |
| neo4j | mở http://localhost:7474 |
| backend-api | `curl -i http://localhost:8000/health` |
| celery-worker | `docker compose logs celery-worker --tail 20` |
| frontend | mở http://localhost:3000 |

## Database (Alembic schema v2)

```bash
docker compose exec backend-api alembic upgrade head
docker compose exec postgres psql -U notebooklm -d notebooklm -c "\dt"
```

- Migration: `backend/alembic/versions/6ebf6936f6c1_initial_schema_v2.py`
- **28 bảng** nghiệp vụ (+ `alembic_version`) — đủ nhóm TASKS/design (identity, documents, pipeline, embeddings, knowledge, chat, retrieval, search, cache/logs, artifacts). Tài liệu đôi khi ghi “27”; đếm đủ bảng join (`topic_chunks`, `comparison_documents`, …) thì là 28.

## CI (GitHub Actions)

Workflow: `.github/workflows/ci.yml` — `push` / `pull_request` → `main`.

| Job | Lệnh |
|-----|------|
| backend | `ruff check` + `black --check` + `pytest` |
| frontend | `npm ci` + `npm run lint` + `npm run build` |

Pip/npm được cache. Chạy tương đương local:

```bash
cd backend && ruff check . && black --check . && pytest -q
cd frontend && npm ci && npm run lint && npm run build
```

## Observability (FR13 foundation)

- **structlog JSON**: `request_id`, `workspace_id` (nếu có), `route`, `latency_ms`, `status_code`
- **OpenTelemetry**: FastAPI + SQLAlchemy. `OTEL_EXPORTER_OTLP_ENDPOINT` trống → không crash. `OTEL_CONSOLE_EXPORTER=true` → in span stdout.
- Hook service sau: `get_logger()`, `bind_log_context()`, `get_tracer()` từ `app.core`

## Vector store

Mặc định **Qdrant** (`VECTOR_STORE=qdrant`). Để chuyển **pgvector** sau này: đổi image Postgres sang biến thể pgvector, set `VECTOR_STORE=pgvector`, cập nhật adapter Vector DB (GĐ RAG).

## Ghi chú kiến trúc

- `backend-api` và `celery-worker` **cùng image**, khác command — scale độc lập.
- Chỉ `backend-api` được gọi Anthropic API (GĐ sau); worker/frontend không gọi LLM.
