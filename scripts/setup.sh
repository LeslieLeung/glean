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
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
cd ..

# Setup frontend
echo "Setting up frontend..."
cd frontend
npm install
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
