FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/root/.cargo/bin:$PATH"

COPY backend/ backend/
COPY frontend/ frontend/
COPY docker/entrypoint.sh /entrypoint.sh

RUN uv venv && uv pip install -r backend/requirements.txt \
    && chmod +x /entrypoint.sh

ENV DATABASE_PATH=/data/watering.db
ENV API_BASE=http://localhost:5000

EXPOSE 5000 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:5000/api/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
