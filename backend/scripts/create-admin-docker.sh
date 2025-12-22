#!/bin/bash
# Script to create admin user in Docker container
# Usage: docker exec -it glean-backend /app/scripts/create-admin-docker.sh [username] [password] [role]

set -e

USERNAME=${1:-admin}
PASSWORD=${2:-$(openssl rand -base64 12)}
ROLE=${3:-super_admin}

cd /app

echo "Creating admin user..."
if uv run python scripts/create-admin.py --username "$USERNAME" --password "$PASSWORD" --role "$ROLE"; then
    echo ""
    echo "=============================================="
    echo "  Admin Account Created Successfully!"
    echo "=============================================="
    echo "  Username: $USERNAME"
    echo "  Password: $PASSWORD"
    echo "  Role: $ROLE"
    echo "=============================================="
    echo ""
    echo "  Please save these credentials securely!"
    echo "=============================================="
fi
