# Dockerfile for Conversational BI backend + MCP servers (production)
#
# Architecture:
#   - Stage 1: Build React frontend
#   - Stage 2: Python runtime with 3 isolated venvs:
#       /app/venv          — main app (FastAPI services, boto3>=1.35)
#       /app/venv-mcp-rs   — mcp-redshift server (own boto3, no conflicts)
#       /app/venv-mcp-s3   — mcp-s3 server (own aiobotocore, no conflicts)
#
# This prevents botocore/boto3 version conflicts between the main app
# and MCP server packages which pull incompatible transitive deps.

# ─── Stage 1: Frontend build ────────────────────────────────────────────────
FROM public.ecr.aws/docker/library/node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build

# ─── Stage 2: Python runtime ────────────────────────────────────────────────
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ─── Venv 1: Main application ───────────────────────────────────────────────
RUN python -m venv /app/venv
COPY pyproject.toml ./
COPY src/ ./src/
RUN /app/venv/bin/pip install --no-cache-dir -e . || \
    /app/venv/bin/pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn>=0.34.0" \
    "pydantic>=2.10.0" \
    "numpy>=1.26.0" \
    "httpx>=0.28.0" \
    "boto3>=1.35.0" && \
    /app/venv/bin/pip install --no-cache-dir "strands-agents>=0.1.0" || true
# MCP SDK needed by the adapter layer (which runs in the main venv)
RUN /app/venv/bin/pip install --no-cache-dir "mcp>=1.0.0" || true

# ─── Venv 2: MCP Redshift server (isolated) ─────────────────────────────────
COPY mcps/mcp-redshift/ ./mcps/mcp-redshift/
RUN python -m venv /app/venv-mcp-rs && \
    /app/venv-mcp-rs/bin/pip install --no-cache-dir -e ./mcps/mcp-redshift

# ─── Venv 3: MCP S3 server (isolated) ───────────────────────────────────────
COPY mcps/mcp-s3/ ./mcps/mcp-s3/
RUN python -m venv /app/venv-mcp-s3 && \
    /app/venv-mcp-s3/bin/pip install --no-cache-dir -e ./mcps/mcp-s3

# ─── Copy remaining app code ────────────────────────────────────────────────
COPY --from=frontend-build /frontend/dist ./frontend/dist/
COPY data/ ./data/
COPY run_all.py ./

# ─── Health check ───────────────────────────────────────────────────────────
# NLP on 8001 starts first — should be healthy within 60s
HEALTHCHECK --interval=15s --timeout=10s --retries=5 --start-period=60s \
    CMD curl -f http://localhost:8001/health || exit 1

EXPOSE 8001

# Entrypoint uses the main app venv's python
CMD ["/app/venv/bin/python", "run_all.py"]
