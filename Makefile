.PHONY: help setup up down api worker web admin db-migrate db-upgrade db-downgrade \
        test lint format clean logs install-backend install-frontend verify

# Default target
help:
	@echo "Glean Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup          - Full setup (Docker + deps + migrations)"
	@echo "  make install        - Install all dependencies"
	@echo "  make install-backend  - Install Python dependencies"
	@echo "  make install-frontend - Install Node dependencies"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make up             - Start Docker services (PostgreSQL + Redis)"
	@echo "  make down           - Stop Docker services"
	@echo "  make logs           - View Docker service logs"
	@echo ""
	@echo "Development:"
	@echo "  make api            - Start API server (port 8000)"
	@echo "  make worker         - Start background worker"
	@echo "  make web            - Start web app (port 3000)"
	@echo "  make admin          - Start admin dashboard"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate MSG=\"description\"  - Create new migration"
	@echo "  make db-upgrade     - Apply migrations"
	@echo "  make db-downgrade   - Revert last migration"
	@echo ""
	@echo "Quality:"
	@echo "  make test           - Run all tests"
	@echo "  make lint           - Run linters"
	@echo "  make format         - Format code"
	@echo ""
	@echo "Other:"
	@echo "  make verify         - Verify M0 setup"
	@echo "  make clean          - Clean generated files"

# =============================================================================
# Setup
# =============================================================================

setup:
	@./scripts/setup.sh

install: install-backend install-frontend

install-backend:
	@echo "🐍 Installing Python dependencies..."
	@cd backend && uv sync --all-packages

install-frontend:
	@echo "📦 Installing Node dependencies..."
	@cd frontend && pnpm install

# =============================================================================
# Infrastructure
# =============================================================================

up:
	@echo "🐳 Starting Docker services..."
	@docker compose -f deploy/docker-compose.dev.yml up -d
	@echo "✅ Services started"
	@echo "   PostgreSQL: localhost:5432"
	@echo "   Redis:      localhost:6379"

down:
	@echo "🛑 Stopping Docker services..."
	@docker compose -f deploy/docker-compose.dev.yml down

logs:
	@docker compose -f deploy/docker-compose.dev.yml logs -f

# =============================================================================
# Development Servers
# =============================================================================

api:
	@echo "🚀 Starting API server on http://localhost:8000"
	@echo "📚 API docs: http://localhost:8000/api/docs"
	@cd backend && uv run uvicorn glean_api.main:app --reload --port 8000

worker:
	@echo "⚙️  Starting background worker..."
	@cd backend && uv run arq glean_worker.main.WorkerSettings

web:
	@echo "🌐 Starting web app on http://localhost:3000"
	@cd frontend && pnpm dev:web

admin:
	@echo "🔧 Starting admin dashboard..."
	@cd frontend && pnpm dev:admin

# =============================================================================
# Database
# =============================================================================

db-migrate:
ifndef MSG
	$(error MSG is required. Usage: make db-migrate MSG="migration description")
endif
	@echo "📝 Creating migration: $(MSG)"
	@cd backend/packages/database && uv run alembic revision --autogenerate -m "$(MSG)"

db-upgrade:
	@echo "⬆️  Applying database migrations..."
	@cd backend/packages/database && uv run alembic upgrade head

db-downgrade:
	@echo "⬇️  Reverting last migration..."
	@cd backend/packages/database && uv run alembic downgrade -1

db-reset:
	@echo "🗑️  Resetting database..."
	@docker compose -f deploy/docker-compose.dev.yml down -v
	@docker compose -f deploy/docker-compose.dev.yml up -d
	@sleep 5
	@cd backend/packages/database && uv run alembic upgrade head
	@echo "✅ Database reset complete"

# =============================================================================
# Quality
# =============================================================================

test:
	@echo "🧪 Running tests..."
	@cd backend && uv run pytest

test-cov:
	@echo "🧪 Running tests with coverage..."
	@cd backend && uv run pytest --cov --cov-report=html

lint:
	@echo "🔍 Running linters..."
	@cd backend && uv run ruff check .
	@cd backend && uv run pyright
	@cd frontend && pnpm lint

format:
	@echo "✨ Formatting code..."
	@cd backend && uv run ruff format .
	@cd backend && uv run ruff check --fix .
	@cd frontend && pnpm format 2>/dev/null || cd frontend && npx prettier --write "**/*.{ts,tsx,js,jsx,json}"

# =============================================================================
# Other
# =============================================================================

verify:
	@./scripts/verify-m0.sh

clean:
	@echo "🧹 Cleaning generated files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf backend/.venv 2>/dev/null || true
	@rm -rf frontend/node_modules 2>/dev/null || true
	@rm -rf htmlcov 2>/dev/null || true
	@echo "✅ Clean complete"

# =============================================================================
# Shortcuts
# =============================================================================

# Start everything (run in separate terminals)
dev:
	@echo "To start development, run these in separate terminals:"
	@echo ""
	@echo "  Terminal 1: make api"
	@echo "  Terminal 2: make worker"
	@echo "  Terminal 3: make web"
	@echo ""
	@echo "Or use tmux/screen to run all at once"

