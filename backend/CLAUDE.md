# Backend Development Guide

This file provides backend-specific development guidance for the Glean project.

For general project information, see [../CLAUDE.md](../CLAUDE.md).

## Backend Structure

```
backend/
├── apps/
│   ├── api/           # FastAPI REST API (port 8000)
│   │   └── routers/   # auth, feeds, entries, bookmarks, folders, tags, admin, preference
│   └── worker/        # arq background worker (Redis queue)
│       └── tasks/     # feed_fetcher, bookmark_metadata, cleanup, embedding_worker, preference_worker
├── packages/
│   ├── database/      # SQLAlchemy models + Alembic migrations
│   ├── core/          # Business logic and domain services
│   ├── rss/           # RSS/Atom feed parsing
│   └── vector/        # Vector embeddings & preference learning (M3)
```

**Dependency Flow**: `api` → `core` → `database` ← `rss` ← `worker`, `vector` → `database`

## Technology Stack

- **Language**: Python 3.11+ (strict pyright)
- **Framework**: FastAPI
- **Database**: SQLAlchemy 2.0 (async) + PostgreSQL 16
- **State/Cache**: Redis 7 + arq
- **Package Manager**: uv
- **Linting**: ruff + pyright

## Development Workflows

### Database Changes

1. Modify models in `backend/packages/database/glean_database/models/`
2. Create migration: `make db-migrate MSG="add_field_to_table"`
3. Review generated migration in `migrations/versions/`
4. Apply: `make db-upgrade`

**Alembic Best Practices**:
- Never manually edit migration files
- Each milestone (M1, M2, M3) should have one migration file
- To modify an undeployed migration: delete file → update model → regenerate

### Adding API Endpoints

1. Create/modify router in `backend/apps/api/glean_api/routers/`
2. Register in `backend/apps/api/glean_api/main.py`
3. Endpoint pattern: `/api/{resource}`

### Adding Background Tasks

1. Create task in `backend/apps/worker/glean_worker/tasks/`
2. Register in `WorkerSettings.functions` or `WorkerSettings.cron_jobs` in `main.py`
3. Tasks are async functions with `ctx` parameter

## Code Style

- 100 char line length, ruff for formatting
- All function signatures require type hints
- SQLAlchemy models use `Mapped[T]` annotations
- Use `uv` instead of `python` to avoid virtual environment issues

### Import Ordering (isort via ruff)

```python
# Standard library
import os
from typing import Optional

# Third-party
from fastapi import APIRouter
from sqlalchemy import select

# First-party (workspace packages)
from glean_core import get_logger
from glean_database import models
```

## Logging

```python
from glean_core import get_logger
logger = get_logger(__name__)
logger.info("Message", extra={"context": "data"})
```

- Request ID auto-added in API logs
- Configure via `LOG_LEVEL`, `LOG_FILE` env vars

## Testing

```bash
# Run all tests
cd backend && uv run pytest

# Run specific test file
cd backend && uv run pytest apps/api/tests/test_auth.py

# Run specific test
cd backend && uv run pytest apps/api/tests/test_auth.py::test_login

# With coverage
cd backend && uv run pytest --cov
```

## CI Compliance

### Ruff Linting Rules

Configured in `backend/pyproject.toml`:
- Line length: **100 characters**
- Target: Python 3.11
- Enabled rules: `E` (pycodestyle), `F` (pyflakes), `I` (isort), `N` (pep8-naming), `W` (warnings), `UP` (pyupgrade), `B` (bugbear), `C4` (comprehensions), `SIM` (simplify)
- Ignored: `E501` (line length - handled by formatter), `B008` (FastAPI `Query()` pattern)

### Pyright Type Checking

- Mode: **strict**
- All function signatures require type hints
- Use `Mapped[T]` for SQLAlchemy columns
- Prefix unused parameters with `_` (e.g., `_ctx`)

### Common Fixes

```bash
# Auto-fix linting issues
cd backend && uv run ruff check --fix .

# Auto-format code
cd backend && uv run ruff format .

# Type check
cd backend && uv run pyright
```

### Common CI Failures and Solutions

| Error                              | Solution                              |
| ---------------------------------- | ------------------------------------- |
| `Ruff: F401 unused import`         | Remove the unused import              |
| `Ruff: I001 import not sorted`     | Run `uv run ruff check --fix .`       |
| `Pyright: missing type annotation` | Add type hints to function signatures |
| `Pyright: unknown member type`     | Add type annotation or use `cast()`   |

## Environment Variables

Configure in `.env` (copy from `.env.example`):
- `DATABASE_URL` - PostgreSQL connection string (asyncpg driver)
- `REDIS_URL` - Redis connection for arq worker
- `SECRET_KEY` - JWT signing key
- `CORS_ORIGINS` - Allowed frontend origins (JSON array)
- `DEBUG` - Enable/disable API docs and debug mode
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `LOG_FILE` - Optional log file path

## Notes

- Always use `uv run` instead of `python` to ensure correct virtual environment
- Never run `make db-reset` without explicit user consent
- All code comments should be in English
