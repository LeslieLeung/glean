# Glean 拾灵

A personal knowledge management tool for information-heavy consumers.

> ✅ **M0 Phase Complete** - Infrastructure ready! | 🚧 **Next: M1 Phase** - MVP features

## Overview

Glean (拾灵) is a powerful RSS reader and personal knowledge management tool that helps you efficiently manage information consumption through intelligent preference learning and AI-assisted processing.

## Features

- 📰 **RSS Subscription Management** - Subscribe and organize RSS/Atom feeds
- 📚 **Smart Reading** - Intelligent content recommendations based on your preferences
- 🔖 **Bookmarks** - Save and organize content from feeds or external URLs
- 🤖 **AI Enhancement** - Summarization, tagging, and content analysis
- 🔧 **Rule Engine** - Automate content processing with custom rules
- 🔒 **Self-hosted** - Full data ownership with Docker deployment

## Tech Stack

### Backend
- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 + PostgreSQL
- Redis + arq (task queue)
- uv (package management)

### Frontend
- React 18 + TypeScript
- Vite
- Tailwind CSS
- Zustand + TanStack Query
- pnpm + Turborepo

## Quick Start

**One-line setup:**
```bash
./scripts/setup.sh
```

**Start development (3 terminals):**
```bash
# Terminal 1: Backend API
cd backend && uv run uvicorn glean_api.main:app --reload

# Terminal 2: Background Worker  
cd backend && uv run arq glean_worker.main.WorkerSettings

# Terminal 3: Web App
cd frontend && pnpm dev:web
```

**Access:**
- 🌐 Web App: http://localhost:3000
- 📚 API Docs: http://localhost:8000/api/docs
- ❤️ Health: http://localhost:8000/api/health

**Verify:**
```bash
./scripts/verify-m0.sh
```

📖 **Detailed guide:** [QUICKSTART.md](./QUICKSTART.md)

## Project Structure

```
glean/
├── backend/                 # Python backend
│   ├── apps/
│   │   ├── api/            # FastAPI application
│   │   └── worker/         # Background task worker
│   └── packages/
│       ├── database/       # Database models & migrations
│       ├── core/           # Core business logic
│       └── rss/            # RSS parsing utilities
│
├── frontend/               # TypeScript frontend
│   ├── apps/
│   │   ├── web/           # User-facing web app
│   │   └── admin/         # Admin dashboard
│   └── packages/
│       ├── ui/            # Shared UI components
│       ├── api-client/    # API client SDK
│       └── types/         # Shared type definitions
│
├── deploy/                 # Deployment configurations
│   └── docker-compose.dev.yml
│
└── docs/                   # Documentation
```

## Documentation

### 🚀 Getting Started
- [Quick Start](./QUICKSTART.md) - 5-minute setup
- [Setup Guide](./README_SETUP.md) - Detailed instructions
- [M0 Summary](./M0_SUMMARY.md) - What's completed
- [Verify Script](./scripts/verify-m0.sh) - Check your setup

### 📋 Architecture & Planning
- [PRD (Product Requirements)](./docs/glean-prd-v1.2.md)
- [Architecture Design](./docs/glean-architecture.md)
- [M0 Development Guide](./docs/glean-m0-development-guide.md)

## License

This project is licensed under the AGPL-3.0 License - see the [LICENSE](LICENSE) file for details.
