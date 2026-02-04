FROM python:3.12-slim

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# Install system deps + locale
RUN apt-get update && apt-get install -y \
    locales curl \
    && locale-gen en_US.UTF-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy dependency files first (for layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-install-project

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
