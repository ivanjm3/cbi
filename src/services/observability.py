"""Observability Bus: structured JSON logging and correlation ID propagation.

Provides a decorator for service entry points that emits structured telemetry
including timing, correlation tracking, and exception details. Designed as a
cross-cutting concern applied at every service boundary.

Requirements: 11.2, 11.3, 11.4, 11.5
"""

import functools
import json
import logging
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import Request

logger = logging.getLogger("observability")
logger.setLevel(logging.INFO)

# Header name for correlation ID propagation between services
CORRELATION_ID_HEADER = "X-Correlation-ID"


def _get_correlation_id_from_args(*args: Any, **kwargs: Any) -> str | None:
    """Extract correlation ID from a FastAPI Request object in args/kwargs."""
    # Check kwargs for a request object
    request = kwargs.get("request")
    if isinstance(request, Request):
        return request.headers.get(CORRELATION_ID_HEADER)
    # Check positional args for a Request object
    for arg in args:
        if isinstance(arg, Request):
            return arg.headers.get(CORRELATION_ID_HEADER)
    return None

def observability_decorator(service_name: str) -> Callable:
    """Create a decorator that emits structured JSON telemetry for service entry points.
    Emits a structured log on every invocation with:
    - service_name, operation_name, correlation_id, timestamp (ISO 8601), request_duration_ms
    On unhandled exceptions, additionally emits:
    - exception_type, exception_message, stack_trace
    Generates a new UUID as correlation_id when not present on inbound request.
    Args:
        service_name: Identifier for the service (e.g., "nlp_translator", "orchestrator_hub").
    Returns:
        A decorator function to wrap async service entry points.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract or generate correlation ID
            correlation_id = _get_correlation_id_from_args(*args, **kwargs)
            if not correlation_id:
                correlation_id = str(uuid.uuid4())

            start = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                duration_ms = int((time.monotonic() - start) * 1000)

                # Extract response status code if result is a JSONResponse
                status_code = getattr(result, "status_code", None)

                log_entry = {
                    "service_name": service_name,
                    "operation_name": func.__name__,
                    "correlation_id": correlation_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_duration_ms": duration_ms,
                    "status_code": status_code,
                }
                logger.info(json.dumps(log_entry))

                return result

            except Exception as e:
                duration_ms = int((time.monotonic() - start) * 1000)

                error_log_entry = {
                    "service_name": service_name,
                    "operation_name": func.__name__,
                    "correlation_id": correlation_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_duration_ms": duration_ms,
                    "exception_type": type(e).__name__,
                    "exception_message": str(e),
                    "stack_trace": traceback.format_exc(),
                }
                logger.error(json.dumps(error_log_entry))

                raise

        return wrapper

    return decorator


def extract_correlation_id(request: Request) -> str:
    """Extract correlation ID from an inbound request, generating one if absent.
    Use this helper in route handlers to obtain the correlation ID for
    propagation to downstream service calls.
    Args:
        request: The inbound FastAPI Request.
    Returns:
        The correlation ID string (existing from header, or newly generated UUID).
    """
    correlation_id = request.headers.get(CORRELATION_ID_HEADER)
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
    return correlation_id


def propagation_headers(correlation_id: str) -> dict[str, str]:
    """Build headers dict for propagating correlation ID to downstream calls.

    Use this when making HTTP requests to other services in the system
    to maintain request tracing across the hub-and-spoke architecture.

    Args:
        correlation_id: The correlation ID to propagate.

    Returns:
        A dict with the X-Correlation-ID header set.
    """
    return {CORRELATION_ID_HEADER: correlation_id}
