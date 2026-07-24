# Enterprise NotebookLM

Hệ thống Web quản lý / khai thác tri thức doanh nghiệp bằng LLM + RAG.

## Cấu trúc monorepo (Phase 1.1)

```text
backend/
  app/
    api/          # FastAPI routers (Presentation layer; = "routers/" trong architecture rules)
    core/         # config, security, logging
    db/           # session, Base
    models/       # SQLAlchemy (Step 3)
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
```

## Chạy local

```bash
cp .env.example .env
docker compose up -d
docker compose ps
```

- API health: http://localhost:8000/health
- Frontend (Next.js **dev**): http://localhost:3000
- MinIO console: http://localhost:9001 (minioadmin / minioadmin)
- Neo4j browser: http://localhost:7474
- Qdrant: http://localhost:6333/dashboard
- Elasticsearch: http://localhost:9200

`docker-compose.override.yml` bật volume mount + `uvicorn --reload` + `next dev`.
Chạy không override: `docker compose -f docker-compose.yml up -d`.

## Vector store: Qdrant (mặc định)

## Checklist kiểm tra dịch vụ

| Service       | Kiểm tra nhanh                                          |
| ------------- | ------------------------------------------------------- |
| postgres      | `docker compose exec postgres pg_isready -U notebooklm` |
| redis         | `docker compose exec redis redis-cli ping` → PONG       |
| qdrant        | `curl http://localhost:6333/readyz`                     |
| elasticsearch | `curl http://localhost:9200/_cluster/health`            |
| minio         | `curl http://localhost:9000/minio/health/live`          |
| neo4j         | mở http://localhost:7474                                |
| backend-api   | `curl http://localhost:8000/health`                     |
| celery-worker | `docker compose logs celery-worker --tail 20`           |
| frontend      | mở http://localhost:3000                                |

## CI (GitHub Actions)

Workflow: `.github/workflows/ci.yml` — chạy trên `push` / `pull_request` vào `main`.

| Job | Lệnh chính |
|-----|------------|
| backend | `ruff check` + `black --check` + `pytest` (smoke `GET /health`) |
| frontend | `npm ci` + `npm run lint` + `npm run build` |

Pip/npm được cache qua `actions/setup-python` và `actions/setup-node`.

## Database (Alembic schema v2)

```bash
docker compose exec backend-api alembic upgrade head
docker compose exec postgres psql -U notebooklm -d notebooklm -c "\dt"
```

Migration: `backend/alembic/versions/6ebf6936f6c1_initial_schema_v2.py` — 28 bảng (+ `alembic_version`).

## Ghi chú kiến trúc

- `backend-api` và `celery-worker` **cùng image**, khác command — scale độc lập.
- Chỉ `backend-api` được gọi Anthropic API (GĐ sau); worker/frontend không gọi LLM.
- structlog/OTel: Bước 4 còn lại của Giai đoạn 1.1.
