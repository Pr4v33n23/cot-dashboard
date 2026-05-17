# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

# Trafilatura needs libxml2/libxslt for its lxml dependency at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential libxml2-dev libxslt1-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer) before copying source.
COPY pyproject.toml /app/pyproject.toml
COPY packages /app/packages
COPY apps/api /app/apps/api

# Pip resolves from pyproject; -e installs in editable mode but for prod we
# install normally so the wheel is built once.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UVICORN_WORKERS=2

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["uvicorn", "src.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--app-dir", "apps/api", \
     "--workers", "2", \
     "--log-level", "info"]
