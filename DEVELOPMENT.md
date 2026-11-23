# Glean Development Guide

[简体中文](DEVELOPMENT.zh-CN.md)

Use this guide to run Glean from source. For a self-hosted installation using published images, see the [deployment guide](DEPLOY.md).

## Prerequisites

- Python 3.11 and uv for the backend
- Node.js 24.15.0 or a later 24.x release, with npm
- pnpm, using the version pinned in [frontend/package.json](frontend/package.json)
- Docker with Docker Compose v2 and Make

Python 3.11 and Node.js 24 match the versions used in CI. The frontend test dependencies require at least Node.js 24.15.0 on that release line.

## Local setup

Clone the repository and install the dependencies:

```bash
git clone https://github.com/LeslieLeung/glean.git
cd glean
UV_PYTHON=3.11 make install
test -e .env || cp .env.example .env
```

`make install` installs the root npm dependencies, all backend workspace packages with uv, and the frontend workspace with pnpm.

In the root `.env`, uncomment `DATABASE_URL` and use the connection string below. Set `DEBUG=true` to enable interactive API documentation.

```dotenv
DATABASE_URL=postgresql+asyncpg://glean:devpassword@localhost:5432/glean
DEBUG=true
```

Start PostgreSQL with pgvector and Redis, apply the migrations, then start the API, worker, web app, and admin dashboard:

```bash
docker compose -f docker-compose.dev.pgvector.yml up -d --wait
make db-upgrade
make dev-all
```

| Service                    | Local URL                          |
| -------------------------- | ---------------------------------- |
| Web app                    | <http://localhost:3000>            |
| Admin dashboard            | <http://localhost:3001>            |
| API health                 | <http://localhost:8000/api/health> |
| API docs with `DEBUG=true` | <http://localhost:8000/api/docs>   |

Run `make api`, `make worker`, `make web`, or `make admin` in separate terminals to start services individually. Use `make electron` to run the desktop app with the local API running.

Keep `VECTOR_BACKEND=pgvector` for the setup above. If you are working on Milvus support, use `make up` in place of the Compose command and set `VECTOR_BACKEND=milvus` and `MILVUS_HOST=localhost` in `.env`. The two Compose files share container names and host ports. Shut down one before starting the other.

Stop the app processes with Ctrl+C and stop the pgvector infrastructure with `docker compose -f docker-compose.dev.pgvector.yml down`. For the Milvus stack, use `make down`.

## Local admin account

After applying the migrations, run this from the repository root:

```bash
(cd backend && uv run python scripts/create-admin.py)
```

Sign in to the admin dashboard with the local defaults, `admin` and `Admin123!`. For custom credentials, pass `--username` and `--password` to the script. The reader uses a separate account that you can register from the web app.

If the script reports `'str' object has no attribute 'value'` after printing `Admin user created successfully!`, the account was saved before the error while printing its role. Try signing in with the credentials you used.

If you use a custom database, export `DATABASE_URL` in your shell before running the admin script or migration commands. Those commands read the shell environment and otherwise use the default local database.

## Database migrations

Create a migration after changing SQLAlchemy models and review the generated file before applying it. Migrations live in [backend/packages/database/glean_database/migrations/versions](backend/packages/database/glean_database/migrations/versions).

```bash
make db-migrate MSG="describe the schema change"
make db-upgrade
```

## Tests and code quality

```bash
make test
make test ARGS="-k auth"
(cd frontend && pnpm test)
make lint
(cd frontend && pnpm typecheck)
```

`make test` starts an isolated PostgreSQL instance on port 5433. `make test-cov` writes an HTML coverage report to `backend/htmlcov/`. Run `make test-db-down` to stop the test database and remove its volume.

Use `make format` to format the code and `(cd frontend && pnpm build)` to build the frontend. If you have pre-commit installed, use `make pre-commit-install` to install the hooks, `make pre-commit-run` to run them manually, and `make pre-commit-uninstall` to remove them.

## Repository layout

| Path                                       | Contents                                                |
| ------------------------------------------ | ------------------------------------------------------- |
| [backend/apps/api](backend/apps/api)       | FastAPI service                                         |
| [backend/apps/worker](backend/apps/worker) | Background jobs                                         |
| [backend/packages](backend/packages)       | Shared database, core, RSS, and vector packages         |
| [frontend/apps/web](frontend/apps/web)     | Reader and Electron app                                 |
| [frontend/apps/admin](frontend/apps/admin) | Admin dashboard                                         |
| [frontend/packages](frontend/packages)     | Shared UI, API client, types, translations, and logging |

See the [repository guidelines](AGENTS.md) for code style and pull request conventions.
