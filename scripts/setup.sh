#!/bin/bash

# Glean Development Environment Setup Script
set -e

echo "Setting up Glean development environment..."

# Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required but not installed. Aborting."; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Node.js is required but not installed. Aborting."; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm is required but not installed. Aborting."; exit 1; }

# Setup backend
echo "Setting up backend..."
cd backend
if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "Syncing dependencies with uv..."
uv sync --all-packages
cd ..

# Setup frontend
echo "Setting up frontend..."
cd frontend
if ! command -v pnpm >/dev/null 2>&1; then
    echo "Installing pnpm..."
    npm install -g pnpm
fi
pnpm install
cd ..

# Setup environment file
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Created .env file from .env.example"
    fi
fi

echo "✓ Setup completed successfully!"
echo ""
echo "To start development:"
echo "  make dev     - Start both backend and frontend"
echo "  make backend - Start backend only"
echo "  make frontend - Start frontend only"
