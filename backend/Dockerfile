# =============================================================================
# File: Dockerfile
# Module/Service: Backend API System
# Layer: Adapter
# Purpose: Multi-stage image for backend-api and celery-worker containers.
# Responsibilities:
#   - Install Python dependencies and run uvicorn (API) or celery (worker)
# Dependencies:
#   - Python 3.11, requirements.txt
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: docker-compose.yml, app.main, app.workers.celery_app
# Important Notes: backend-api and celery-worker share this image; only API
#   container may call Anthropic in later phases.
# =============================================================================

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
