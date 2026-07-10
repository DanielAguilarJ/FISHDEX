"""
Correlation ID Middleware
=========================
Assigns a unique request ID to every incoming request for tracing.
The ID is:
  - Read from X-Request-ID header (if the client/proxy provides one)
  - Generated as UUID4 otherwise
  - Stored in request.state.correlation_id
  - Added to the response as X-Request-ID header
  - Available to loggers via a context var
"""

import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ─── Context variable for correlation ID ─────────────────────────────────
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")


class CorrelationFilter(logging.Filter):
    """
    Logging filter that adds ``correlation_id`` to every log record.

    Attach to a handler or to the root logger so that format strings
    containing ``%(correlation_id)s`` are filled automatically.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_ctx.get("-")  # type: ignore[attr-defined]
        return True


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that assigns a unique correlation ID to each request.

    The ID is read from the incoming ``X-Request-ID`` header when present,
    otherwise a new UUID4 is generated.  It is then:

    * stored in ``request.state.correlation_id``
    * set in the ``correlation_id_ctx`` context variable
    * echoed back in the ``X-Request-ID`` response header
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Prefer client/proxy-supplied ID; fall back to a fresh UUID4
        cid = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store on request.state so route handlers can access it
        request.state.correlation_id = cid

        # Set context var for the logging filter
        token = correlation_id_ctx.set(cid)

        try:
            response: Response = await call_next(request)
        finally:
            # Reset context var after the request is done
            correlation_id_ctx.reset(token)

        # Echo correlation ID in the response
        response.headers["X-Request-ID"] = cid
        return response
