#!/usr/bin/env python3
"""
Create initial admin user.

Usage:
    # From project root (development)
    python backend/scripts/create-admin.py
    python backend/scripts/create-admin.py --username admin --password AdminPass123! --role super_admin
    python backend/scripts/create-admin.py --username admin --password NewPass123! --force  # Recreate without prompt

    # From backend directory (development)
    cd backend && python scripts/create-admin.py

    # In Docker container
    docker exec -it glean-backend /app/scripts/create-admin-docker.sh
    docker exec -it glean-backend uv run python scripts/create-admin.py --username admin --password MySecurePass!
"""

import argparse
import asyncio
import hashlib
import os
import sys
from pathlib import Path

# Handle both local development and Docker container paths
# In Docker: /app is the working directory (backend), scripts/ is at /app/scripts/
# In development: running from backend/scripts/, backend is parent directory
current_file = Path(__file__).resolve()
script_dir = current_file.parent

if script_dir.name == "scripts":
    # Check if we're in Docker (/app/scripts/) or local development (backend/scripts/)
    # In both cases, parent directory is the backend root
    backend_path = script_dir.parent
    sys.path.insert(0, str(backend_path))

# Imports below need to come after sys.path modification
from sqlalchemy import delete, select  # noqa: E402

from glean_core.services import AdminService  # noqa: E402
from glean_database.models.admin import AdminRole, AdminUser  # noqa: E402
from glean_database.session import get_session_context, init_database  # noqa: E402


def hash_password_sha256(password: str) -> str:
    """
    Hash password using SHA256 to match frontend behavior.

    The frontend hashes passwords with SHA256 before transmission,
    so we need to do the same when creating admin accounts via script.
    """
    return hashlib.sha256(password.encode()).hexdigest()


async def create_admin(username: str, password: str, role: str, force: bool = False) -> bool:
    """Create an admin user. Returns True if successful."""
    # Hash the password with SHA256 to match frontend behavior
    # Frontend sends SHA256(password), so we need to store bcrypt(SHA256(password))
    hashed_password = hash_password_sha256(password)

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
    async with get_session_context() as session:
        service = AdminService(session)

        # Check if admin user already exists
        result = await session.execute(select(AdminUser).where(AdminUser.username == username))
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            if force:
                # Force flag is set, delete without asking
                should_delete = True
            else:
                # Ask user for confirmation (only in interactive mode)
                if sys.stdin.isatty():
                    print(f"⚠️  Admin user '{username}' already exists.")
                    print(f"   ID: {existing_admin.id}")
                    print(f"   Role: {existing_admin.role.value}")
                    response = (
                        input("\n   Do you want to delete and recreate? [y/N]: ").strip().lower()
                    )
                    should_delete = response in ("y", "yes")
                else:
                    # Non-interactive mode (e.g., Docker entrypoint)
                    print(f"⚠️  Admin user '{username}' already exists.")
                    print("   Use --force flag to recreate, or choose a different username.")
                    return False

            if should_delete:
                await session.execute(delete(AdminUser).where(AdminUser.id == existing_admin.id))
                await session.commit()
                print(f"   🗑️  Deleted existing admin user '{username}'.")
            else:
                print("   ❌ Aborted. No changes made.")
                return False

        # Create new admin
        try:
            admin = await service.create_admin_user(
                username=username, password=hashed_password, role=admin_role
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
                print("   Use --force flag to recreate, or choose a different username.")
            else:
                print(f"❌ Error creating admin user: {e}")
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
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force recreate if user already exists (no confirmation prompt)",
    )

    args = parser.parse_args()

    print(f"Creating admin user: {args.username}")
    success = asyncio.run(create_admin(args.username, args.password, args.role, args.force))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
