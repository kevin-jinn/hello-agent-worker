# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim

ENV PYTHONUNBUFFERED=1

ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN mkdir -p src

RUN uv sync --locked

COPY . .

RUN chown -R appuser:appuser /app
USER appuser

# ✅ Safe prewarm (optional)
RUN uv run - <<'EOF'
from livekit.plugins import silero
silero.VAD.load()
print("VAD ready")
EOF

CMD ["uv", "run", "src/agent.py", "start"]