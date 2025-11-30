#!/usr/bin/env python3
"""
Create initial admin user.

Usage:
    # From backend directory (development)
    cd backend && uv run python scripts/create-admin.py
    cd backend && uv run python scripts/create-admin.py --username admin --password AdminPass123! --role super_admin

    # In Docker container
    docker exec -it glean-backend /app/scripts/create-admin-docker.sh
    docker exec -it glean-backend uv run python scripts/create-admin.py --username admin --password MySecurePass!
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Handle both local development and Docker container paths
# In Docker: /app is the working directory
# In development: running from backend/ directory
app_dir = Path(__file__).parent.parent
if app_dir.name == "backend":
    # Running from project root or development
    sys.path.insert(0, str(app_dir))
elif app_dir.name == "app":
    # Running in Docker container
    pass

from glean_core.services import AdminService  # noqa: E402
from glean_database.models.admin import AdminRole  # noqa: E402
from glean_database.session import get_session, init_database  # noqa: E402


async def create_admin(username: str, password: str, role: str) -> bool:
    """Create an admin user. Returns True if successful."""
    # Get database URL from environment
    database_url = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://glean:devpassword@localhost:5432/glean"
    )

    # Initialize database
    init_database(database_url)

    # Parse role
    try:
        admin_role = AdminRole(role)
    except ValueError:
        print(f"Invalid role: {role}")
        print(f"Valid roles: {', '.join([r.value for r in AdminRole])}")
        return False

    # Create admin
    async for session in get_session():
        service = AdminService(session)

        try:
            admin = await service.create_admin_user(
                username=username, password=password, role=admin_role
            )
            print("✅ Admin user created successfully!")
            print(f"   Username: {admin.username}")
            print(f"   Role: {admin.role.value}")
            print(f"   ID: {admin.id}")
            return True
        except Exception as e:
            await session.rollback()
            error_msg = str(e)
            if "duplicate key" in error_msg or "already exists" in error_msg:
                print(f"⚠️  Admin user '{username}' already exists.")
                print("   Use a different username or delete the existing user first.")
                return False
            else:
                print(f"❌ Error creating admin user: {e}")
                raise

    return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Create initial admin user")
    parser.add_argument("--username", default="admin", help="Admin username (default: admin)")
    parser.add_argument(
        "--password", default="Admin123!", help="Admin password (default: Admin123!)"
    )
    parser.add_argument(
        "--role",
        default="super_admin",
        choices=["super_admin", "admin"],
        help="Admin role (default: super_admin)",
    )

    args = parser.parse_args()

    print(f"Creating admin user: {args.username}")
    success = asyncio.run(create_admin(args.username, args.password, args.role))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
