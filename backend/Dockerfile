FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.lock && \
    pip install --no-deps .

RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/false -m appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "python -m alembic upgrade head && python -m uvicorn nexus.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

