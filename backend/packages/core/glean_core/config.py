"""
Authentication provider configuration.

This module provides configuration settings for authentication providers
loaded from environment variables.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Find .env file in project root
_env_file = Path(__file__).parent.parent.parent.parent.parent / ".env"


class AuthProviderConfig(BaseSettings):
    """
    Authentication provider configuration from environment variables.

    All settings are prefixed with AUTH_ in environment.
    """

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Local provider (password-based authentication)
    local_enabled: bool = True
    local_allow_registration: bool = True

    # OIDC provider (generic - works with Google, Microsoft, Auth0, Keycloak, etc.)
    oidc_enabled: bool = False
    oidc_provider_name: str = ""  # Display name (e.g., "Google", "Company SSO")
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_issuer: str = ""  # e.g., "https://accounts.google.com"
    oidc_discovery_url: str = ""  # Optional, defaults to {issuer}/.well-known/openid-configuration
    oidc_scopes: str = "openid email profile"  # Space-separated scopes
    oidc_redirect_uri: str = ""  # e.g., "http://localhost:3000/auth/callback"
    oidc_jwks_cache_ttl_seconds: int = 86400
    oidc_rate_limit_window_seconds: int = 60
    oidc_authorize_rate_limit: int = 10
    oidc_callback_rate_limit: int = 5
    oidc_trusted_proxy_ips: str = ""  # Comma-separated trusted proxy IPs or CIDRs
    oidc_client_ip_headers: str = "x-real-ip"  # Priority-ordered, comma-separated


# Global instance
auth_provider_config = AuthProviderConfig()
