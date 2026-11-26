#!/bin/bash
set -e

# Migrate ownership of persistent log directories from earlier root-based
# deployments, then immediately drop privileges to appuser before running
# DB checks, migrations, admin creation, or the main service process.
if [ "$(id -u)" -eq 0 ]; then
    mkdir -p /app/logs
    if [ -n "${LOG_FILE:-}" ]; then
        log_dir="$(dirname "$LOG_FILE")"
        case "$log_dir" in
            /app/logs|/app/logs/*)
                case "$log_dir" in
                    */..|*/../*) ;;
                    *) mkdir -p "$log_dir" ;;
                esac
                ;;
            /*)
                case "$log_dir" in
                    */..|*/../*|/app|/app/*|/tmp|/var|/var/log|/etc|/usr|/bin|/sbin|/lib|/lib64|/home|/root|/proc|/sys|/dev|/run|/opt)
                        ;;
                    *)
                        mkdir -p "$log_dir"
                        if ! chown -Rh appuser:appuser "$log_dir"; then
                            echo "WARNING: Could not update ownership of $log_dir" >&2
                        fi
                        ;;
                esac
                ;;
        esac
    fi

    if ! chown -Rh appuser:appuser /app/logs; then
        echo "WARNING: Could not update ownership of /app/logs" >&2
    fi

    app_home="$(getent passwd appuser | cut -d: -f6)"
    export HOME="${app_home:-/home/appuser}"
    export USER="appuser"
    exec setpriv \
        --reuid="$(id -u appuser)" \
        --regid="$(id -g appuser)" \
        --init-groups \
        --no-new-privs \
        -- "$0" "$@"
fi

# Wait for database to be ready
echo "Waiting for PostgreSQL to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if uv run --no-sync python -c '
import asyncio
import os
from sqlalchemy import text
from glean_database.session import init_database, get_session_context

async def check():
    init_database(os.environ["DATABASE_URL"])
    async with get_session_context() as session:
        await session.execute(text("SELECT 1"))
        return True

asyncio.run(check())
' 2>&1; then
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
    ADMIN_ROLE=${ADMIN_ROLE:-super_admin}

    if [ -z "${ADMIN_PASSWORD:-}" ] || [ "${ADMIN_PASSWORD}" = "Admin123!" ]; then
        echo "ERROR: CREATE_ADMIN is enabled, but ADMIN_PASSWORD is empty or set to the insecure default." >&2
        exit 1
    fi

    echo "Creating admin user..."
    if ADMIN_PASSWORD="$ADMIN_PASSWORD" uv run --no-sync python scripts/create-admin.py --username "$ADMIN_USERNAME" --role "$ADMIN_ROLE" 2>&1; then
        echo ""
        echo "=============================================="
        echo "  Admin Account Created Successfully!"
        echo "=============================================="
        echo "  Username: $ADMIN_USERNAME"
        echo "  Role: $ADMIN_ROLE"
        echo "=============================================="
        echo ""
        echo "  Keep your configured ADMIN_PASSWORD secret safe."
        echo "=============================================="
    fi
fi

# Execute the main command
echo "Starting $@..."
exec "$@"
