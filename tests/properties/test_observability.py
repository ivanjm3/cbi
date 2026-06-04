"""Property tests for observability telemetry correctness.

Property 14: Observability Telemetry Correctness
- For any service invocation, the decorator emits correct structured JSON
  with all required fields (service_name, operation_name, correlation_id,
  timestamp, request_duration_ms).
- Generates correlation_id (valid UUID) if missing from inbound request.
- Propagates correlation_id to downstream calls via headers.
- On unhandled exceptions, emits additional fields: exception_type,
  exception_message, stack_trace.

Validates: Requirements 11.2, 11.3, 11.4, 11.5
"""

import json
import logging
import uuid
from datetime import datetime

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from hypothesis import given, HealthCheck, settings
from hypothesis import strategies as st

from src.services.observability import (
    CORRELATION_ID_HEADER,
    extract_correlation_id,
    observability_decorator,
    propagation_headers,
)


# --- Strategies ---

# Service names: non-empty alphanumeric strings with underscores
service_name_strategy = st.from_regex(r"[a-z][a-z0-9_]{0,29}", fullmatch=True)

# Correlation IDs: either valid UUIDs or arbitrary non-empty ASCII strings
# (HTTP headers only support ASCII encoding)
correlation_id_strategy = st.one_of(
    st.uuids().map(str),
    st.text(
        min_size=1,
        max_size=64,
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S"),
            max_codepoint=127,
        ),
    ).filter(lambda s: s.isprintable()),
)

# Exception types with messages for error path testing
exception_message_strategy = st.text(min_size=0, max_size=100)

exception_types_strategy = st.sampled_from([
    ValueError,
    TypeError,
    RuntimeError,
    KeyError,
    IOError,
    AttributeError,
    ZeroDivisionError,
])


# --- Helpers ---


def _create_app_with_service(service_name: str) -> FastAPI:
    """Create a FastAPI app with success and error endpoints decorated with observability."""
    app = FastAPI()

    @app.get("/success")
    @observability_decorator(service_name)
    async def success_endpoint(request: Request):
        return {"status": "ok"}

    return app


def _create_error_app(service_name: str, exception_cls: type, message: str) -> FastAPI:
    """Create a FastAPI app with an endpoint that raises a specific exception."""
    app = FastAPI()

    @app.get("/error")
    @observability_decorator(service_name)
    async def error_endpoint(request: Request):
        raise exception_cls(message)

    return app


# --- Property Tests ---


class TestObservabilityTelemetryCorrectness:
    """Property 14: Observability Telemetry Correctness.

    For any service invocation the decorator emits correct structured JSON
    with all required fields, generates correlation_id if missing, and
    propagates it to downstream calls.
    """

    @given(service_name=service_name_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_success_log_contains_all_required_fields(self, service_name: str) -> None:
        """For any service name, the decorator emits JSON with all required fields on success."""
        app = _create_app_with_service(service_name)
        client = TestClient(app)

        import io

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        obs_logger = logging.getLogger("observability")
        obs_logger.addHandler(handler)

        try:
            response = client.get("/success")
            assert response.status_code == 200

            log_output = log_stream.getvalue()
            assert log_output, "Expected a log entry to be emitted"

            log_data = json.loads(log_output.strip())

            # All required fields present
            assert "service_name" in log_data
            assert "operation_name" in log_data
            assert "correlation_id" in log_data
            assert "timestamp" in log_data
            assert "request_duration_ms" in log_data

            # Correct values
            assert log_data["service_name"] == service_name
            assert log_data["operation_name"] == "success_endpoint"
            assert isinstance(log_data["request_duration_ms"], int)
            assert log_data["request_duration_ms"] >= 0

            # Timestamp is valid ISO 8601
            datetime.fromisoformat(log_data["timestamp"])
        finally:
            obs_logger.removeHandler(handler)

    @given(correlation_id=correlation_id_strategy, service_name=service_name_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_provided_correlation_id_is_used(
        self, correlation_id: str, service_name: str
    ) -> None:
        """For any provided correlation_id, the decorator uses it in the emitted log."""
        app = _create_app_with_service(service_name)
        client = TestClient(app)

        import io

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        obs_logger = logging.getLogger("observability")
        obs_logger.addHandler(handler)

        try:
            response = client.get(
                "/success", headers={CORRELATION_ID_HEADER: correlation_id}
            )
            assert response.status_code == 200

            log_output = log_stream.getvalue()
            log_data = json.loads(log_output.strip())

            assert log_data["correlation_id"] == correlation_id
        finally:
            obs_logger.removeHandler(handler)

    @given(service_name=service_name_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_generates_valid_uuid_when_correlation_id_missing(
        self, service_name: str
    ) -> None:
        """When no correlation_id header is present, a valid UUID4 is generated."""
        app = _create_app_with_service(service_name)
        client = TestClient(app)

        import io

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        obs_logger = logging.getLogger("observability")
        obs_logger.addHandler(handler)

        try:
            response = client.get("/success")
            assert response.status_code == 200

            log_output = log_stream.getvalue()
            log_data = json.loads(log_output.strip())

            # correlation_id must be a valid UUID
            parsed_uuid = uuid.UUID(log_data["correlation_id"])
            assert parsed_uuid.version == 4
        finally:
            obs_logger.removeHandler(handler)

    @given(
        service_name=service_name_strategy,
        exception_cls=exception_types_strategy,
        message=exception_message_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_error_log_contains_exception_fields(
        self, service_name: str, exception_cls: type, message: str
    ) -> None:
        """On unhandled exceptions, error log includes exception_type, exception_message, stack_trace."""
        app = _create_error_app(service_name, exception_cls, message)
        client = TestClient(app, raise_server_exceptions=False)

        import io

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.ERROR)
        obs_logger = logging.getLogger("observability")
        obs_logger.addHandler(handler)

        try:
            client.get("/error")

            log_output = log_stream.getvalue()
            assert log_output, "Expected an error log entry to be emitted"

            log_data = json.loads(log_output.strip())

            # All base fields still present
            assert log_data["service_name"] == service_name
            assert log_data["operation_name"] == "error_endpoint"
            assert "correlation_id" in log_data
            assert "timestamp" in log_data
            assert isinstance(log_data["request_duration_ms"], int)
            assert log_data["request_duration_ms"] >= 0

            # Exception-specific fields
            assert log_data["exception_type"] == exception_cls.__name__
            # Note: str(exception) is used, which for KeyError adds quotes around the key
            assert log_data["exception_message"] == str(exception_cls(message))
            assert "stack_trace" in log_data
            assert len(log_data["stack_trace"]) > 0

            # Timestamp is valid ISO 8601
            datetime.fromisoformat(log_data["timestamp"])
        finally:
            obs_logger.removeHandler(handler)

    @given(
        service_name=service_name_strategy,
        correlation_id=correlation_id_strategy,
        exception_cls=exception_types_strategy,
        message=exception_message_strategy,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_error_log_preserves_provided_correlation_id(
        self,
        service_name: str,
        correlation_id: str,
        exception_cls: type,
        message: str,
    ) -> None:
        """On exception, the provided correlation_id is preserved in the error log."""
        app = _create_error_app(service_name, exception_cls, message)
        client = TestClient(app, raise_server_exceptions=False)

        import io

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.ERROR)
        obs_logger = logging.getLogger("observability")
        obs_logger.addHandler(handler)

        try:
            client.get("/error", headers={CORRELATION_ID_HEADER: correlation_id})

            log_output = log_stream.getvalue()
            log_data = json.loads(log_output.strip())

            assert log_data["correlation_id"] == correlation_id
        finally:
            obs_logger.removeHandler(handler)


class TestCorrelationIdPropagation:
    """Verify correlation ID propagation helpers work correctly for any input.

    This ensures downstream calls can always receive the correlation_id,
    satisfying Requirement 11.4.
    """

    @given(correlation_id=correlation_id_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_propagation_headers_always_contains_correlation_id(
        self, correlation_id: str
    ) -> None:
        """For any correlation_id, propagation_headers returns a dict with the correct header."""
        headers = propagation_headers(correlation_id)

        assert isinstance(headers, dict)
        assert CORRELATION_ID_HEADER in headers
        assert headers[CORRELATION_ID_HEADER] == correlation_id

    @given(correlation_id=correlation_id_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_extract_correlation_id_returns_header_value(
        self, correlation_id: str
    ) -> None:
        """For any correlation_id in the request header, extract_correlation_id returns it."""
        app = FastAPI()

        @app.get("/extract")
        async def extract_endpoint(request: Request):
            cid = extract_correlation_id(request)
            return {"correlation_id": cid}

        client = TestClient(app)
        resp = client.get("/extract", headers={CORRELATION_ID_HEADER: correlation_id})
        assert resp.json()["correlation_id"] == correlation_id

    @given(data=st.data())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_extract_generates_uuid4_when_header_absent(self, data: st.DataObject) -> None:
        """When no header is present, extract_correlation_id generates a valid UUID4."""
        app = FastAPI()

        @app.get("/extract")
        async def extract_endpoint(request: Request):
            cid = extract_correlation_id(request)
            return {"correlation_id": cid}

        client = TestClient(app)
        resp = client.get("/extract")
        cid = resp.json()["correlation_id"]

        # Must be a valid UUID4
        parsed = uuid.UUID(cid)
        assert parsed.version == 4

    @given(correlation_id=correlation_id_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_propagation_round_trip(self, correlation_id: str) -> None:
        """For any correlation_id, propagating via headers and extracting yields the same value."""
        headers = propagation_headers(correlation_id)

        app = FastAPI()

        @app.get("/roundtrip")
        async def roundtrip_endpoint(request: Request):
            cid = extract_correlation_id(request)
            return {"correlation_id": cid}

        client = TestClient(app)
        resp = client.get("/roundtrip", headers=headers)
        assert resp.json()["correlation_id"] == correlation_id


class TestDurationMeasurement:
    """Verify request_duration_ms is always non-negative and reflects actual execution time."""

    @given(service_name=service_name_strategy)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_duration_is_non_negative_integer(self, service_name: str) -> None:
        """request_duration_ms is always a non-negative integer."""
        app = _create_app_with_service(service_name)
        client = TestClient(app)

        import io

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        obs_logger = logging.getLogger("observability")
        obs_logger.addHandler(handler)

        try:
            client.get("/success")

            log_output = log_stream.getvalue()
            log_data = json.loads(log_output.strip())

            assert isinstance(log_data["request_duration_ms"], int)
            assert log_data["request_duration_ms"] >= 0
        finally:
            obs_logger.removeHandler(handler)
