"""Redis key templates and TTL constants.

Centralized management of all Redis keys used in the application to prevent
conflicts and make maintenance easier.
"""


class RedisKeys:
    """Redis key templates and helper methods."""

    # ============================================================================
    # Auth Related Keys
    # ============================================================================

    # OIDC state for CSRF protection
    # Format: oidc_state:{state}
    # TTL: 5 minutes (300 seconds)
    OIDC_STATE_TTL = 300

    @staticmethod
    def oidc_state(state: str) -> str:
        """
        Get OIDC state key for CSRF protection.

        Args:
            state: Random state token generated during authorization.

        Returns:
            Redis key string.
        """
        return f"oidc_state:{state}"

    # OIDC state binding hash for desktop/cross-site CSRF binding
    # Format: oidc_state_binding:{state}
    # TTL: 5 minutes (300 seconds) - same as state
    OIDC_STATE_BINDING_TTL = 300

    @staticmethod
    def oidc_state_binding(state: str) -> str:
        """Get OIDC state binding hash key for desktop/cross-site CSRF binding."""
        return f"oidc_state_binding:{state}"

    # OIDC nonce for replay attack prevention
    # Format: oidc_nonce:{state}
    # TTL: 5 minutes (300 seconds) - same as state
    OIDC_NONCE_TTL = 300

    @staticmethod
    def oidc_nonce(state: str) -> str:
        """
        Get OIDC nonce key for replay attack prevention.

        Nonce is stored with state as key to simplify cleanup.

        Args:
            state: State token used as key (same as in authorization).

        Returns:
            Redis key string.
        """
        return f"oidc_nonce:{state}"

    # OIDC PKCE code verifier
    # Format: oidc_pkce_verifier:{state}
    # TTL: 5 minutes (300 seconds) - same as state
    OIDC_PKCE_VERIFIER_TTL = 300

    @staticmethod
    def oidc_pkce_verifier(state: str) -> str:
        """
        Get OIDC PKCE verifier key.

        PKCE verifier is stored with state as key to simplify cleanup.

        Args:
            state: State token used as key (same as in authorization).

        Returns:
            Redis key string.
        """
        return f"oidc_pkce_verifier:{state}"

    # OIDC endpoint rate-limit key
    # Format: oidc_rate_limit:{action}:{client_id}
    @staticmethod
    def oidc_rate_limit(action: str, client_id: str) -> str:
        """
        Get OIDC endpoint rate-limit key.

        Args:
            action: Endpoint action (e.g., 'authorize', 'callback').
            client_id: Client identifier, usually an IP address.

        Returns:
            Redis key string.
        """
        return f"oidc_rate_limit:{action}:{client_id}"

    @staticmethod
    def auth_rate_limit(action: str, client_id: str) -> str:
        """Get general auth/admin/token endpoint rate-limit key."""
        return f"auth_rate_limit:{action}:{client_id}"

    @staticmethod
    def revoked_refresh_token(jti: str) -> str:
        """Key marking a consumed or revoked refresh token jti."""
        return f"revoked_refresh:{jti}"

    # ============================================================================
    # Embedding Rebuild Keys
    # ============================================================================

    # Distributed lock for embedding rebuild
    # Prevents concurrent rebuild jobs from running
    # TTL: 10 minutes (generous for the enqueue phase)
    REBUILD_LOCK_KEY = "glean:rebuild_embeddings_lock"
    REBUILD_LOCK_TIMEOUT = 600
    EMBEDDING_MAINTENANCE_THROTTLE_TTL = 240
    EMBEDDING_PENDING_MAINTENANCE_KEY = "glean:embedding_maintenance:pending"
    # Shared sliding-window limiter for embedding provider calls (all jobs).
    EMBEDDING_RATE_LIMIT_KEY = "glean:embedding_rate_limit"

    @staticmethod
    def embedding_validation_maintenance(version: str | None) -> str:
        """Throttle recovery enqueue for one validation generation."""
        return f"glean:embedding_maintenance:validation:{version or 'missing'}"

    @staticmethod
    def vector_cleanup_maintenance(feed_id: str) -> str:
        """Throttle orphan-vector cleanup enqueue for one feed."""
        return f"glean:embedding_maintenance:cleanup:{feed_id}"
