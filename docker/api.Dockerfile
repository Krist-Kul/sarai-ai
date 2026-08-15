# API image. Deliberately slim: no torch, no CUDA, no model weights.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* README.md ./
COPY sarai ./sarai
RUN uv sync --group api --no-dev --frozen || uv sync --group api --no-dev

ENV PATH="/app/.venv/bin:$PATH" DATA_DIR=/data
EXPOSE 8000
CMD ["uvicorn", "sarai.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
