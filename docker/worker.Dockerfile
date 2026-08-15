# Worker image. CUDA runtime base so torch finds a GPU; falls back to CPU when
# the container is started without one.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.11 python3.11-venv python3-pip ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* README.md ./
COPY sarai ./sarai
RUN uv sync --group worker --no-dev --frozen || uv sync --group worker --no-dev

ENV PATH="/app/.venv/bin:$PATH" DATA_DIR=/data HF_HOME=/data/hf-cache
CMD ["python", "-m", "sarai.worker.main"]
