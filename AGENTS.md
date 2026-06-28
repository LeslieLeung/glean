# Repository Guidelines

## Project Structure & Module Organization
Glean is a monorepo for a self-hosted RSS reader and personal knowledge tool. Backend code lives in `backend/`: `apps/api` is the FastAPI service, `apps/worker` contains arq jobs, and `packages/` holds shared Python packages for `database`, `core`, `rss`, and `vector`. Frontend code lives in `frontend/`: `apps/web` is the React/Vite app and Electron entry, `apps/admin` is the dashboard, and `packages/` holds shared `ui`, `api-client`, `types`, `i18n`, and `logger` workspaces. Static assets are in `asset/`, docs in `docs/`, and scripts in `scripts/`.

## Build, Test, and Development Commands
- `make setup`: run the full local setup.
- `make up` / `make down`: start or stop Docker development infrastructure.
- `make api`, `make worker`, `make web`, `make admin`: run individual services locally.
- `make dev-all`: run API, worker, web, and admin together.
- `make db-migrate MSG="add field"` and `make db-upgrade`: create and apply Alembic migrations.
- `make test` / `make test-cov`: run backend pytest with the isolated test database.
- `make lint` / `make format`: run ruff, pyright, ESLint, and Prettier.
- `cd frontend && pnpm test`: run frontend Vitest suites.

## Coding Style & Naming Conventions
Backend targets Python 3.11 with ruff formatting, 100-character lines, strict pyright, and explicit type hints. Use `Mapped[T]` for SQLAlchemy models and keep imports sorted by ruff. Frontend uses TypeScript strict mode, Prettier with 2-space indentation, single quotes, no semicolons, ES5 trailing commas, and Tailwind class sorting. Prefer workspace imports such as `@glean/api-client` over deep relative paths.

## Testing Guidelines
Python tests live under `backend/tests`, `backend/apps/*/tests`, and `backend/packages/*/tests`; name files `test_*.py`. Frontend tests live near code in `src/__tests__` or as `*.test.ts`. Add focused tests for changed API behavior, database models, workers, stores, hooks, and API-client services. Use `make test` for backend changes that need PostgreSQL on port `5433`.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commit-style subjects, for example `feat(reader): add keyboard navigation`, `fix(bookmark): truncate title`, and `chore(deps): update dependency`. Keep subjects short and scoped. Pull requests should describe the change, list tests run, link issues, and call out migrations, environment variables, Docker changes, or screenshots for UI work.

## Security & Configuration Tips
Copy local configuration from `.env.example` and never commit secrets. Change default admin credentials and `SECRET_KEY` outside development. Keep development and test databases separate; the test compose file uses port `5433`.
