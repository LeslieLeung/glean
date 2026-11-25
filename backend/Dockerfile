# Backend Dockerfile for Glean API and Worker
# Supports both API server and background worker modes

# Locked NumPy wheels support up to CPython 3.14.
FROM python:3.14-slim

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

# Install uv (pinned version)
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /uvx /bin/

# Create unprivileged runtime user
RUN groupadd --system appuser && useradd --system --gid appuser --create-home appuser

# Copy workspace files
COPY pyproject.toml uv.lock ./
COPY apps/ apps/
COPY packages/ packages/
COPY scripts/ scripts/

# Make scripts executable and grant appuser ownership of /app and logs
RUN chmod +x scripts/*.sh 2>/dev/null || true \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app

# Install dependencies
RUN uv sync --locked --all-packages --no-dev --no-cache \
    && chown -R appuser:appuser /app

USER appuser

# Expose API port
EXPOSE 8000

# Set entrypoint for automatic migrations
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# Default command (API server - can be overridden for worker)
CMD ["uv", "run", "--no-sync", "uvicorn", "glean_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
