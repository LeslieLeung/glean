#!/usr/bin/env python3
"""
Create initial admin user.

Usage:
    python scripts/create-admin.py
    python scripts/create-admin.py --username admin --password AdminPass123! --role super_admin
    python scripts/create-admin.py --username admin --password NewPass123! --force  # Recreate without prompt
"""

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

import os

from sqlalchemy import delete, select

from glean_core.services import AdminService
from glean_database.models.admin import AdminRole, AdminUser
from glean_database.session import get_session, init_database


def hash_password_sha256(password: str) -> str:
    """
    Hash password using SHA256 to match frontend behavior.

    The frontend hashes passwords with SHA256 before transmission,
    so we need to do the same when creating admin accounts via script.
    """
    return hashlib.sha256(password.encode()).hexdigest()


async def create_admin(
    username: str, password: str, role: str, force: bool = False
) -> None:
    """Create an admin user."""
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
        return

    # Create admin
    async for session in get_session():
        service = AdminService(session)

        # Check if admin user already exists
        result = await session.execute(
            select(AdminUser).where(AdminUser.username == username)
        )
        existing_admin = result.scalar_one_or_none()

        if existing_admin:
            if force:
                # Force flag is set, delete without asking
                should_delete = True
            else:
                # Ask user for confirmation
                print(f"⚠️  Admin user '{username}' already exists.")
                print(f"   ID: {existing_admin.id}")
                print(
                    f"   Role: {existing_admin.role if isinstance(existing_admin.role, str) else existing_admin.role.value}"
                )
                response = (
                    input("\n   Do you want to delete and recreate? [y/N]: ")
                    .strip()
                    .lower()
                )
                should_delete = response in ("y", "yes")

            if should_delete:
                await session.execute(
                    delete(AdminUser).where(AdminUser.id == existing_admin.id)
                )
                await session.commit()
                print(f"   🗑️  Deleted existing admin user '{username}'.")
            else:
                print("   ❌ Aborted. No changes made.")
                return

        # Create new admin
        try:
            admin = await service.create_admin_user(
                username=username, password=hashed_password, role=admin_role
            )
            print("✅ Admin user created successfully!")
            print(f"   Username: {admin.username}")
            print(
                f"   Role: {admin.role if isinstance(admin.role, str) else admin.role.value}"
            )
            print(f"   ID: {admin.id}")
        except Exception as e:
            await session.rollback()
            print(f"❌ Error creating admin user: {e}")
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Create initial admin user")
    parser.add_argument(
        "--username", default="admin", help="Admin username (default: admin)"
    )
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
    asyncio.run(create_admin(args.username, args.password, args.role, args.force))


if __name__ == "__main__":
    main()
