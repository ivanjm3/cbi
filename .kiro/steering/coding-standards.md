---
inclusion: auto
---

# Coding Standards

## General Principles

- All services expose the same interface contracts that will be used in production. Phase 1 simplifies implementations, not interfaces.
- Each component is a separate Python module that can be tested independently.
- Prefer explicit error handling over silent failures. Every error returns structured JSON.
- No retries in spoke agents (single-attempt semantics).

## Python Style

- Python 3.11+ with type hints on all function signatures.
- Use `async/await` for all I/O operations.
- Use Pydantic v2 models for all data structures crossing service boundaries.
- Use `dataclasses` for internal-only structures where Pydantic validation isn't needed.
- Follow PEP 8. Max line length 100.
- Imports: stdlib → third-party → local, separated by blank lines.

## FastAPI Conventions

- Each service is a FastAPI app in its own module under `src/services/`.
- Health check endpoint: `GET /health` returning `{"status": "ok"}`.
- All endpoints decorated with `@observability_decorator(service_name)`.
- Correlation ID extracted from `X-Correlation-ID` header; generated if absent.
- Error responses use a consistent envelope: `{"error_code": "...", "error_message": "...", "correlation_id": "...", "service": "...", "timestamp": "..."}`.

## Inter-Service Communication

- Use `httpx.AsyncClient` for HTTP calls between local services.
- Always propagate `X-Correlation-ID` header in downstream calls.
- Default timeout: 30 seconds for agent calls, 10 seconds for internal service calls.
- On timeout: return structured error, do not retry.

## Testing

- Property-based tests in `tests/properties/` using Hypothesis.
- Unit tests in `tests/unit/` using pytest.
- Integration tests in `tests/integration/` using pytest + httpx.
- Mock Bedrock calls in unit/property tests for deterministic results.
- Minimum 100 iterations per property test.
- Tag property tests: `@pytest.mark.property` and include property name in docstring.

## Observability

- Use the shared `observability_decorator` from `src/services/observability.py`.
- All log output is structured JSON to stdout.
- Never log sensitive data (credentials, full query results in production).
- Include correlation_id in all log entries.

## Error Handling

- Never swallow exceptions silently.
- Graceful degradation: if Query History Store is unavailable, skip routing bias and continue.
- Guardrail Layer: on internal failure, return error without forwarding partial output.
- Ontology Store: on malformed input, reject and preserve existing state.

## Configuration

- Service ports and timeouts defined in a shared config module.
- Guardrail rules loaded from `./data/guardrail_rules.json`.
- Ontology definitions loaded from `./data/ontology/`.
- No hardcoded AWS region or credentials; use standard boto3 credential chain.
