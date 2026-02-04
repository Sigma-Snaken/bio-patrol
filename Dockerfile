# ---------- builder ----------
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Install dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# ---------- runtime ----------
FROM python:3.12-slim

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV PYTHONPATH=/app/src/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    locales curl \
    && locale-gen en_US.UTF-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv (needed for `uv run`)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy venv from builder
COPY --from=builder /app/.venv .venv
COPY --from=builder /app/pyproject.toml /app/uv.lock ./

# Copy application code
COPY src/ src/

# Create runtime data directories (config files generated from defaults.py)
RUN mkdir -p data/config data/maps

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src/backend", "--no-access-log"]
