"""
Logging middleware.

Adds unique ID to each request and logs request information.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from glean_core import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Logging middleware.

    Adds unique ID to each request and logs request and response information.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Generate request ID
        request_id = str(uuid.uuid4())

        # Record request start time
        start_time = time.time()

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Get user agent
        user_agent = request.headers.get("user-agent", "unknown")

        # Bind context information to logger
        context_logger = logger.bind(
            request_id=request_id,
            method=request.method,
            url=str(request.url),
            client_ip=client_ip,
            user_agent=user_agent,
        )

        # Log request start
        context_logger.info("Request started")

        # Process request
        try:
            response = await call_next(request)

            # Calculate processing time
            process_time = time.time() - start_time

            # Bind response information
            response_logger = context_logger.bind(
                status_code=response.status_code,
                process_time=f"{process_time:.4f}s",
            )

            # Log request completion
            if response.status_code < 400:
                response_logger.info("Request completed")
            else:
                response_logger.warning("Request completed with error status")

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Calculate processing time
            process_time = time.time() - start_time

            # Bind error information
            error_logger = context_logger.bind(
                process_time=f"{process_time:.4f}s",
                error=str(e),
            )

            # Log error
            error_logger.exception("Request failed with exception")

            # Re-raise exception
            raise
