"""
Password hashing and verification utilities.

Uses bcrypt for secure password hashing with configurable cost factor.
"""

import asyncio

import bcrypt

MAX_BCRYPT_PASSWORD_BYTES = 72


def hash_password(password: str, rounds: int = 12) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password to hash.
        rounds: Cost factor for bcrypt (default: 12).

    Returns:
        Hashed password string.

    Raises:
        ValueError: If password exceeds bcrypt's 72-byte UTF-8 limit.
    """
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("Password exceeds maximum length of 72 bytes")

    salt = bcrypt.gensalt(rounds=rounds)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify.
        hashed_password: Previously hashed password.

    Returns:
        True if password matches, False otherwise.
    """
    try:
        password_bytes = plain_password.encode("utf-8")
        if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
            return False
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


async def hash_password_async(password: str, rounds: int = 12) -> str:
    """Non-blocking wrapper around hash_password for async request handlers."""
    return await asyncio.to_thread(hash_password, password, rounds)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Non-blocking wrapper around verify_password for async request handlers."""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)
