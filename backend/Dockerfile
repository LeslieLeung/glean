# Backend Dockerfile for Glean API and Worker
# Supports both API server and background worker modes

FROM python:3.12-slim

# Build arguments
ARG TARGETPLATFORM
ARG BUILDPLATFORM
ARG APP_VERSION=dev

# Set version as environment variable
ENV APP_VERSION=${APP_VERSION}

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Keep uv artifacts across builds to avoid re-downloading large wheels.
ENV UV_CACHE_DIR=/root/.cache/uv

# Copy dependency declarations first (changes less often → better cache)
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/database/pyproject.toml packages/database/pyproject.toml
COPY packages/rss/pyproject.toml packages/rss/pyproject.toml
COPY packages/vector/pyproject.toml packages/vector/pyproject.toml

# Install third-party dependencies only (cached unless pyproject.toml or uv.lock changes)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --all-packages --no-dev --no-install-workspace

# Copy source code and scripts (changes often, but doesn't bust dep cache)
COPY apps/ apps/
COPY packages/ packages/
COPY scripts/ scripts/

# Install workspace packages (fast, no downloads needed)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --all-packages --no-dev

# Make scripts executable
RUN chmod +x scripts/*.sh 2>/dev/null || true

# Expose API port
EXPOSE 8000

# Set entrypoint for automatic migrations
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# Default command (API server - can be overridden for worker)
CMD ["uv", "run", "--no-sync", "uvicorn", "glean_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
