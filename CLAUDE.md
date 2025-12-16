# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Glean (拾灵) is a personal knowledge management tool and RSS reader built with a Python backend and TypeScript frontend. The project uses a monorepo structure with workspaces for both backend and frontend.

For backend-specific development guidance, see [backend/CLAUDE.md](backend/CLAUDE.md).
For frontend-specific development guidance, see [frontend/CLAUDE.md](frontend/CLAUDE.md).

## Quick Start

```bash
# Start infrastructure (PostgreSQL + Redis + Milvus)
make up

# Start all services (API + Worker + Web)
make dev-all

# Or run services individually
make api             # FastAPI server (http://localhost:8000)
make worker          # arq background worker
make web             # React web app (http://localhost:3000)
make admin           # Admin dashboard (http://localhost:3001)
```

For detailed deployment instructions, see [DEPLOY.md](DEPLOY.md).

## Docker Compose Configuration

The project includes multiple Docker Compose configurations for different use cases:

### Production Deployment

```bash
# Basic deployment (without admin dashboard)
docker compose up -d

# Full deployment with admin dashboard
docker compose --profile admin up -d

# Stop services
docker compose down
```

### Development Environment

```bash
# Start development infrastructure (PostgreSQL, Redis, Milvus)
docker compose -f docker-compose.dev.yml up -d

# View logs
docker compose -f docker-compose.dev.yml logs -f

# Stop services
docker compose -f docker-compose.dev.yml down
```

### Local Development with Override

```bash
# Use local builds instead of Docker images
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

### Environment Variables

Key environment variables for Docker deployments:

- `WEB_PORT`: Web interface port (default: 80)
- `ADMIN_PORT`: Admin dashboard port (default: 3001)
- `POSTGRES_DB/USER/PASSWORD`: Database credentials
- `SECRET_KEY`: JWT signing key
- `CREATE_ADMIN`: Create admin account on startup (default: false)
- `ADMIN_USERNAME/PASSWORD`: Admin credentials
- `DEBUG`: Enable debug mode (default: false)

For a complete list of environment variables, see `.env.example` in the project root.

## Development Commands

### Database Migrations
```bash
make db-upgrade                    # Apply migrations
make db-migrate MSG="description"  # Create new migration (autogenerate)
make db-downgrade                  # Revert last migration
make db-reset                      # Drop DB, recreate, and apply migrations (REQUIRES USER CONSENT)
```

Working directory: `backend/packages/database` | Tool: Alembic (SQLAlchemy 2.0)

### Testing & Code Quality
```bash
make test            # Run pytest for all backend packages/apps
make test-cov        # Run tests with coverage report
make lint            # Run ruff + pyright (backend), eslint (frontend)
make format          # Format code with ruff (backend), prettier (frontend)

# Frontend-specific (from frontend/ directory)
pnpm typecheck                          # Type check all packages
pnpm --filter=@glean/web typecheck      # Type check specific package
pnpm --filter=@glean/web build          # Build specific package
```

### Package Management
```bash
# Root: npm (for concurrently tool)
npm install

# Backend: uv (Python 3.11+)
cd backend && uv sync --all-packages

# Frontend: pnpm + Turborepo
cd frontend && pnpm install
```

## Architecture

### Technology Stack

| Layer       | Backend                                | Frontend                 |
| ----------- | -------------------------------------- | ------------------------ |
| Language    | Python 3.11+ (strict pyright)          | TypeScript (strict)      |
| Framework   | FastAPI                                | React 18 + Vite          |
| Database    | SQLAlchemy 2.0 (async) + PostgreSQL 16 | -                        |
| State/Cache | Redis 7 + arq                          | Zustand + TanStack Query |
| Styling     | -                                      | Tailwind CSS             |
| Package Mgr | uv                                     | pnpm + Turborepo         |
| Linting     | ruff + pyright                         | ESLint + Prettier        |

**Infrastructure**: PostgreSQL 16 (5432), Redis 7 (6379), Milvus (optional), Docker Compose

### Backend Structure

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

See [backend/CLAUDE.md](backend/CLAUDE.md) for detailed backend development guidance.

### Frontend Structure

```
frontend/
├── apps/
│   ├── web/           # Main React app (port 3000)
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   └── stores/    # Zustand state stores
│   └── admin/         # Admin dashboard (port 3001)
├── packages/
│   ├── ui/            # Shared components (COSS UI based)
│   ├── api-client/    # TypeScript API client SDK
│   ├── types/         # Shared TypeScript types
│   └── logger/        # Unified logging (loglevel based)
```

See [frontend/CLAUDE.md](frontend/CLAUDE.md) for detailed frontend development guidance.

### Configuration

Environment variables in `.env` (copy from `.env.example`):
- `DATABASE_URL` - PostgreSQL connection string (asyncpg driver)
- `REDIS_URL` - Redis connection for arq worker
- `SECRET_KEY` - JWT signing key
- `CORS_ORIGINS` - Allowed frontend origins (JSON array)
- `DEBUG` - Enable/disable API docs and debug mode

## Testing

```bash
# Backend
cd backend && uv run pytest apps/api/tests/test_auth.py
cd backend && uv run pytest apps/api/tests/test_auth.py::test_login

# Frontend
cd frontend/apps/web && pnpm test
```

**Test Account** (for automated testing):
- Email: claude.test@example.com
- Password: TestPass123!
- Feed: https://ameow.xyz/feed.xml

**Admin Dashboard**:
- URL: http://localhost:3001
- Create admin: `cd backend && uv run python ../scripts/create-admin.py`
- Default: admin / Admin123!

## CI Compliance

Before submitting code, ensure it passes all CI checks. Run these commands locally to verify:

### Quick Verification

```bash
# Backend: lint, format check, and type check
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pyright

# Frontend: lint, type check, and build
cd frontend && pnpm lint && pnpm typecheck && pnpm build
```

Or use the Makefile shortcuts:
```bash
make lint      # Run all linters (backend + frontend)
make format    # Auto-fix formatting issues
make test      # Run backend tests
```

### CI Pipeline Summary

| Check        | Backend Command                | Frontend Command   |
| ------------ | ------------------------------ | ------------------ |
| Linting      | `uv run ruff check .`          | `pnpm lint`        |
| Format Check | `uv run ruff format --check .` | (included in lint) |
| Type Check   | `uv run pyright`               | `pnpm typecheck`   |
| Tests        | `uv run pytest`                | `pnpm test`        |
| Build        | -                              | `pnpm build`       |

### Pre-Commit Checklist

Before committing changes:

1. **Format code**: `make format`
2. **Run linters**: `make lint`
3. **Run tests** (if modifying logic): `make test`
4. **Type check** (for complex changes):
   - Backend: `cd backend && uv run pyright`
   - Frontend: `cd frontend && pnpm typecheck`

## Miscellaneous

- This project uses monorepo structure - always check your current working directory
- You don't have to create documentation unless explicitly asked
- Never run `make db-reset` without explicit user consent
- Always write code comments in English
