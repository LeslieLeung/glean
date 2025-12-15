# Backend Dockerfile for Glean API and Worker
# Supports both API server and background worker modes

FROM python:3.11-slim

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

# Copy workspace files
COPY pyproject.toml uv.lock ./
COPY apps/ apps/
COPY packages/ packages/
COPY scripts/ scripts/

# Make scripts executable
RUN chmod +x scripts/*.sh 2>/dev/null || true

# Install dependencies
RUN uv sync --all-packages --no-dev

# Expose API port
EXPOSE 8000

# Set entrypoint for automatic migrations
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# Default command (API server - can be overridden for worker)
CMD ["uv", "run", "--no-sync", "uvicorn", "glean_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
