"""
Authentication schemas.

Request and response models for authentication endpoints.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator

from glean_core.auth.password import MAX_BCRYPT_PASSWORD_BYTES


def _validate_password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("Password must be at most 72 bytes")
    return value


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def check_password_bytes(cls, v: str) -> str:
        return _validate_password_bytes(v)


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def check_password_bytes(cls, v: str) -> str:
        return _validate_password_bytes(v)


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Optional refresh token payload for logout revocation."""

    refresh_token: str | None = None
