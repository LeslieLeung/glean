"""Vector client lifecycle helpers for worker tasks."""

from __future__ import annotations

from typing import Any

from glean_core import get_logger
from glean_vector.clients.vector_store import VectorStoreClient, create_vector_store_client
from glean_vector.config import vector_backend_config

logger = get_logger(__name__)


def ensure_vector_client(ctx: dict[str, Any]) -> tuple[VectorStoreClient | None, str | None]:
    """
    Ensure a usable vector client exists in worker context.

    Returns:
        (client, error_message). error_message is set when client is unavailable.
    """
    client = ctx.get("vector_client")
    if client is not None:
        return client, None

    try:
        client = create_vector_store_client()
        client.connect()
        ctx["vector_client"] = client
        ctx["vector_client_error"] = None
        logger.info(
            "Vector client initialized on demand",
            extra={"backend": vector_backend_config.backend},
        )
        return client, None
    except Exception as exc:
        error_message = str(exc)
        ctx["vector_client"] = None
        ctx["vector_client_error"] = error_message
        logger.warning(
            "Failed to initialize vector client on demand",
            extra={"backend": vector_backend_config.backend, "error": error_message},
        )
        return None, error_message
