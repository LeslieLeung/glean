#!/bin/bash
set -e

# Wait for database to be ready
echo "Waiting for PostgreSQL to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if uv run --no-sync python -c "
import asyncio
from sqlalchemy import text
from glean_database.session import init_database, get_session_context

async def check():
    init_database('$DATABASE_URL')
    async with get_session_context() as session:
        await session.execute(text('SELECT 1'))
        return True

asyncio.run(check())
" 2>&1; then
        echo "PostgreSQL is ready!"
        break
    fi

    attempt=$((attempt + 1))
    echo "Waiting for PostgreSQL... ($attempt/$max_attempts)"
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "ERROR: Could not connect to PostgreSQL after $max_attempts attempts"
    exit 1
fi

# Run database migrations (only if RUN_MIGRATIONS is set)
if [ "$RUN_MIGRATIONS" = "true" ] || [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "Running database migrations..."
    cd /app/packages/database
    uv run --no-sync alembic upgrade head
    cd /app
else
    echo "Skipping database migrations (RUN_MIGRATIONS not set)"
fi

# Create admin user if requested
if [ "$CREATE_ADMIN" = "true" ] || [ "$CREATE_ADMIN" = "1" ]; then
    ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
    ADMIN_PASSWORD=${ADMIN_PASSWORD:-$(openssl rand -base64 12)}
    ADMIN_ROLE=${ADMIN_ROLE:-super_admin}

    echo "Creating admin user..."
    if uv run --no-sync python scripts/create-admin.py --username "$ADMIN_USERNAME" --password "$ADMIN_PASSWORD" --role "$ADMIN_ROLE" 2>&1; then
        echo ""
        echo "=============================================="
        echo "  Admin Account Created Successfully!"
        echo "=============================================="
        echo "  Username: $ADMIN_USERNAME"
        echo "  Password: $ADMIN_PASSWORD"
        echo "  Role: $ADMIN_ROLE"
        echo "=============================================="
        echo ""
        echo "  Please save these credentials securely!"
        echo "  This password will NOT be shown again."
        echo "=============================================="
    fi
fi

# Execute the main command
echo "Starting $@..."
exec "$@"
