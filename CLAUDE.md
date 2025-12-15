# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Glean (拾灵) is a personal knowledge management tool and RSS reader built with a Python backend and TypeScript frontend. The project uses a monorepo structure with workspaces for both backend and frontend.

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

### Configuration

Environment variables in `.env` (copy from `.env.example`):
- `DATABASE_URL` - PostgreSQL connection string (asyncpg driver)
- `REDIS_URL` - Redis connection for arq worker
- `SECRET_KEY` - JWT signing key
- `CORS_ORIGINS` - Allowed frontend origins (JSON array)
- `DEBUG` - Enable/disable API docs and debug mode

## Key Development Notes

### Backend Development

#### Database Changes
1. Modify models in `backend/packages/database/glean_database/models/`
2. Create migration: `make db-migrate MSG="add_field_to_table"`
3. Review generated migration in `migrations/versions/`
4. Apply: `make db-upgrade`

**Alembic Best Practices**:
- Never manually edit migration files
- Each milestone (M1, M2, M3) should have one migration file
- To modify an undeployed migration: delete file → update model → regenerate

#### Adding API Endpoints
1. Create/modify router in `backend/apps/api/glean_api/routers/`
2. Register in `backend/apps/api/glean_api/main.py`
3. Endpoint pattern: `/api/{resource}`

#### Adding Background Tasks
1. Create task in `backend/apps/worker/glean_worker/tasks/`
2. Register in `WorkerSettings.functions` or `WorkerSettings.cron_jobs` in `main.py`
3. Tasks are async functions with `ctx` parameter

#### Code Style
- 100 char line length, ruff for formatting
- All function signatures require type hints
- SQLAlchemy models use `Mapped[T]` annotations
- Use `uv` instead of `python` to avoid virtual environment issues

#### Logging
```python
from glean_core import get_logger
logger = get_logger(__name__)
logger.info("Message", extra={"context": "data"})
```
- Request ID auto-added in API logs
- Configure via `LOG_LEVEL`, `LOG_FILE` env vars

### Frontend Development

#### UI Components (COSS UI)
This project uses [COSS UI](https://coss.com/ui/) for components.

To add a new component:
1. Visit `https://coss.com/ui/r/{component-name}.json`
2. Copy to `frontend/packages/ui/src/components/`
3. Export from `frontend/packages/ui/src/components/index.ts`

#### Dialog/AlertDialog Close Buttons

When using `AlertDialogClose` or `DialogClose` from base-ui, **do not use the `render` prop with `<Button />`** as it requires ref forwarding which the Button component doesn't support. Instead, use `buttonVariants` to apply button styling directly:

```tsx
// ❌ Bad - causes "Function components cannot be given refs" warning
import { AlertDialogClose, Button } from '@glean/ui'

<AlertDialogClose render={<Button variant="ghost" />}>
  Cancel
</AlertDialogClose>

// ✅ Good - use buttonVariants for styling
import { AlertDialogClose, buttonVariants } from '@glean/ui'

<AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
  Cancel
</AlertDialogClose>

// For default button style
<AlertDialogClose className={buttonVariants()}>
  OK
</AlertDialogClose>

// For destructive actions
<AlertDialogClose className={buttonVariants({ variant: 'destructive' })}>
  Delete
</AlertDialogClose>
```

The same pattern applies to `DialogClose`.

#### Code Style
- Prettier with Tailwind plugin
- Import order: React → third-party → workspace packages → relative

#### Logging
```typescript
import { logger, createNamedLogger } from '@glean/logger'
logger.info('Message', { context: 'data' })
```
- Configure via `VITE_LOG_LEVEL` (debug in dev, error in prod)

#### i18n (Internationalization)

This project uses **react-i18next** for internationalization. Always use translation keys instead of hardcoded text.

**Using i18n in Components:**

```tsx
// ❌ Bad - hardcoded text
<button>Save</button>
<h1>Settings</h1>

// ✅ Good - using i18n
import { useTranslation } from '@glean/i18n'

function MyComponent() {
  const { t } = useTranslation('common') // or 'auth', 'settings', etc.
  return (
    <>
      <button>{t('actions.save')}</button>
      <h1>{t('settings:title')}</h1>
    </>
  )
}
```

**Available Namespaces:**
- `common`: Shared UI text (buttons, states, actions)
- `auth`: Authentication pages (login, register)
- `settings`: Settings page
- `reader`: Reading interface
- `bookmarks`: Bookmark management
- `feeds`: Feed management, folders, OPML
- `ui`: UI component-level text

**Adding New Translations:**

1. Add key-value pairs to the appropriate namespace JSON files:
   - `frontend/packages/i18n/src/locales/en/{namespace}.json`
   - `frontend/packages/i18n/src/locales/zh-CN/{namespace}.json`

2. Use the translation in your component:
   ```tsx
   const { t } = useTranslation('namespace')
   t('your.new.key')
   ```

**Variable Interpolation:**
```json
// feeds.json
{
  "count": "{{count}} feeds"
}
```

```tsx
t('feeds:count', { count: 5 }) // Output: "5 feeds"
```

**Date Formatting:**
```tsx
import { formatRelativeTime } from '@glean/i18n/utils/date-formatter'
import { useTranslation } from '@glean/i18n'

function MyComponent({ date }) {
  const { i18n } = useTranslation()
  return <time>{formatRelativeTime(date, i18n.language)}</time>
}
```

**Language Switching:**

Users can change language in Settings → Appearance → Language.
The selection is persisted to localStorage and auto-detected on first visit.

### Testing

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

## UI Layout & Design

### Application Layout

The web app uses a **three-column layout**:

```
┌──────────────────────────────────────────────────────────────────┐
│                        Header (optional)                          │
├──────────┬─────────────────┬─────────────────────────────────────┤
│          │                 │                                      │
│ Sidebar  │   Entry List    │          Reading Pane                │
│ (72-256) │    (280-500)    │          (flexible)                  │
│          │                 │                                      │
│ - Feeds  │ - Entry cards   │ - Article title                      │
│ - Folders│ - Filters       │ - Content (prose)                    │
│ - Tags   │ - Skeleton      │ - Actions (like, bookmark, share)   │
│          │                 │                                      │
└──────────┴─────────────────┴─────────────────────────────────────┘
```

- **Sidebar**: Collapsible (72px ↔ 256px), contains navigation and feed list
- **Entry List**: Resizable (280-500px), shows article previews with filters
- **Reading Pane**: Flexible width, displays full article content

### Design Principles

| Principle         | Description                                                 |
| ----------------- | ----------------------------------------------------------- |
| Warm Dark Theme   | Default theme with amber primary (`hsl(38 92% 50%)`)        |
| Reading-First     | Optimized typography and spacing for long-form content      |
| Subtle Animations | Meaningful feedback without distraction (fade, slide, glow) |
| Glassmorphism     | Modern blur effects for overlays and cards                  |

### Color System

Always use CSS variables, never hard-coded colors:
```tsx
// Correct
className="bg-primary text-primary-foreground"
className="text-muted-foreground hover:text-foreground"

// Incorrect
className="bg-amber-500 text-slate-900"
```

Key semantic colors:
- `--primary`: Amber accent
- `--secondary`: Teal accent
- `--background` / `--foreground`: Main page colors
- `--card` / `--muted`: Surface colors
- `--destructive` / `--success` / `--warning`: Semantic states

### Typography

| Usage           | Font Family | Example Class                     |
| --------------- | ----------- | --------------------------------- |
| Headings/UI     | DM Sans     | `font-display text-2xl font-bold` |
| Article Content | Crimson Pro | `prose font-reading`              |
| Code            | Monospace   | Built-in prose styling            |

### Component Patterns

```tsx
// Glass effect for overlays
<div className="glass">...</div>

// Interactive cards
<div className="card-hover">...</div>

// Primary action buttons with glow
<Button className="btn-glow">...</Button>

// Animations
<div className="animate-fade-in">...</div>
<ul className="stagger-children">{items}</ul>
```

### Interaction Guidelines

- **Buttons**: Primary (glow on hover), Ghost (transparent), Outline (bordered)
- **Cards**: Subtle lift on hover (`translateY(-2px)`)
- **Focus States**: 4px ring in primary color
- **Loading**: Skeleton placeholders matching content layout
- **Transitions**: Fast (150ms) for hover, Standard (200ms) for state changes

Refer to `docs/design.md` for complete color palettes, spacing scales, and detailed component specifications.

## MCP Tools

When debugging frontend issues, use `chrome-devtools` MCP to help with:
- Taking snapshots and screenshots
- Inspecting network requests and console messages
- Interacting with page elements

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

### Backend Compliance

**Ruff Linting Rules** (configured in `backend/pyproject.toml`):
- Line length: **100 characters**
- Target: Python 3.11
- Enabled rules: `E` (pycodestyle), `F` (pyflakes), `I` (isort), `N` (pep8-naming), `W` (warnings), `UP` (pyupgrade), `B` (bugbear), `C4` (comprehensions), `SIM` (simplify)
- Ignored: `E501` (line length - handled by formatter), `B008` (FastAPI `Query()` pattern)

**Import Ordering** (isort via ruff):
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

**Pyright Type Checking**:
- Mode: **strict**
- All function signatures require type hints
- Use `Mapped[T]` for SQLAlchemy columns
- Prefix unused parameters with `_` (e.g., `_ctx`)

**Common Backend Fixes**:
```bash
# Auto-fix linting issues
cd backend && uv run ruff check --fix .

# Auto-format code
cd backend && uv run ruff format .
```

### Frontend Compliance

**ESLint + Prettier** (configured in `frontend/eslint.config.js` and `.prettierrc`):
- No semicolons
- Single quotes
- 2-space indentation
- 100 character print width
- Trailing commas (ES5 style)
- Tailwind class sorting (via prettier-plugin-tailwindcss)

**TypeScript**:
- Strict mode enabled
- Unused variables: error (prefix with `_` to ignore)
- All exports should be typed

**React-specific Rules**:
- Use `react-refresh/only-export-components` for HMR compatibility
- React hooks rules enforced

**Common Frontend Fixes**:
```bash
# Auto-fix ESLint issues
cd frontend && pnpm lint --fix

# Auto-format with Prettier
cd frontend && pnpm format
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

### Common CI Failures and Solutions

| Error                              | Solution                              |
| ---------------------------------- | ------------------------------------- |
| `Ruff: F401 unused import`         | Remove the unused import              |
| `Ruff: I001 import not sorted`     | Run `uv run ruff check --fix .`       |
| `Pyright: missing type annotation` | Add type hints to function signatures |
| `Pyright: unknown member type`     | Add type annotation or use `cast()`   |
| `ESLint: no-unused-vars`           | Remove variable or prefix with `_`    |
| `TypeScript: implicit any`         | Add explicit type annotation          |
| `Prettier: formatting`             | Run `pnpm format`                     |

## Miscellaneous

- This project uses monorepo structure - always check your current working directory
- You don't have to create documentation unless explicitly asked
- Never run `make db-reset` without explicit user consent
- Always write code comments in English
- DO NOT modify anything within `frontend/packages/ui/src/components/` unless explicitly asked
