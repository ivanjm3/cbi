"""Unit tests for the observability decorator and correlation ID helpers."""

import json
import logging
import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.services.observability import (
    CORRELATION_ID_HEADER,
    extract_correlation_id,
    observability_decorator,
    propagation_headers,
)

# --- Test observability_decorator ---


@pytest.fixture
def app_with_decorated_endpoint():
    """Create a FastAPI app with an endpoint wrapped by the observability decorator."""
    app = FastAPI()

    @app.get("/test")
    @observability_decorator("test_service")
    async def test_endpoint(request: Request):
        return {"message": "ok"}

    @app.get("/error")
    @observability_decorator("test_service")
    async def error_endpoint(request: Request):
        raise ValueError("something went wrong")

    return app


@pytest.fixture
def client(app_with_decorated_endpoint):
    return TestClient(app_with_decorated_endpoint)


def test_decorator_emits_structured_log_on_success(client, caplog):
    """Decorator emits structured JSON with all required fields on success."""
    with caplog.at_level(logging.INFO, logger="observability"):
        response = client.get("/test")

    assert response.status_code == 200

    # Find the observability log entry
    log_entries = [r for r in caplog.records if r.name == "observability"]
    assert len(log_entries) == 1

    log_data = json.loads(log_entries[0].message)
    assert log_data["service_name"] == "test_service"
    assert log_data["operation_name"] == "test_endpoint"
    assert "correlation_id" in log_data
    assert "timestamp" in log_data
    assert "request_duration_ms" in log_data
    assert isinstance(log_data["request_duration_ms"], int)

    # Verify correlation_id is a valid UUID
    uuid.UUID(log_data["correlation_id"])


def test_decorator_generates_correlation_id_when_missing(client, caplog):
    """When no X-Correlation-ID header is present, a new UUID is generated."""
    with caplog.at_level(logging.INFO, logger="observability"):
        client.get("/test")

    log_entries = [r for r in caplog.records if r.name == "observability"]
    log_data = json.loads(log_entries[0].message)

    # Should be a valid UUID
    parsed = uuid.UUID(log_data["correlation_id"])
    assert parsed.version == 4


def test_decorator_uses_provided_correlation_id(client, caplog):
    """When X-Correlation-ID header is provided, it is used in the log."""
    test_id = "abc-123-test-correlation"
    with caplog.at_level(logging.INFO, logger="observability"):
        client.get("/test", headers={CORRELATION_ID_HEADER: test_id})

    log_entries = [r for r in caplog.records if r.name == "observability"]
    log_data = json.loads(log_entries[0].message)

    assert log_data["correlation_id"] == test_id


def test_decorator_emits_error_log_on_exception(client, caplog):
    """Decorator emits structured error log with exception details on failure."""
    with caplog.at_level(logging.ERROR, logger="observability"):
        with pytest.raises(Exception):
            # TestClient raises the exception by default for 500 errors
            client.get("/error", headers={CORRELATION_ID_HEADER: "err-corr-id"})

    error_entries = [
        r for r in caplog.records if r.name == "observability" and r.levelno == logging.ERROR
    ]
    assert len(error_entries) == 1

    log_data = json.loads(error_entries[0].message)
    assert log_data["service_name"] == "test_service"
    assert log_data["operation_name"] == "error_endpoint"
    assert log_data["correlation_id"] == "err-corr-id"
    assert log_data["exception_type"] == "ValueError"
    assert log_data["exception_message"] == "something went wrong"
    assert "stack_trace" in log_data
    assert "request_duration_ms" in log_data
    assert "timestamp" in log_data


def test_decorator_timestamp_is_iso8601(client, caplog):
    """Timestamp field is in ISO 8601 format."""
    from datetime import datetime

    with caplog.at_level(logging.INFO, logger="observability"):
        client.get("/test")

    log_entries = [r for r in caplog.records if r.name == "observability"]
    log_data = json.loads(log_entries[0].message)

    # Should parse without error
    datetime.fromisoformat(log_data["timestamp"])


# --- Test extract_correlation_id ---


def test_extract_correlation_id_from_header():
    """extract_correlation_id returns the header value when present."""
    app = FastAPI()

    @app.get("/extract")
    async def extract_endpoint(request: Request):
        cid = extract_correlation_id(request)
        return {"correlation_id": cid}

    client = TestClient(app)
    resp = client.get("/extract", headers={CORRELATION_ID_HEADER: "my-corr-id"})
    assert resp.json()["correlation_id"] == "my-corr-id"


def test_extract_correlation_id_generates_uuid_when_missing():
    """extract_correlation_id generates a UUID when header is absent."""
    app = FastAPI()

    @app.get("/extract")
    async def extract_endpoint(request: Request):
        cid = extract_correlation_id(request)
        return {"correlation_id": cid}

    client = TestClient(app)
    resp = client.get("/extract")
    cid = resp.json()["correlation_id"]
    # Should be a valid UUID
    uuid.UUID(cid)


# --- Test propagation_headers ---


def test_propagation_headers_returns_correct_dict():
    """propagation_headers builds the expected header dict."""
    headers = propagation_headers("test-123")
    assert headers == {CORRELATION_ID_HEADER: "test-123"}
