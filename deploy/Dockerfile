# Dockerfile for the Conversational BI backend + frontend
# Builds the React frontend, then runs all 5 FastAPI services.
# Frontend is served from the same container via FastAPI StaticFiles.

# Stage 1: Build frontend
FROM public.ecr.aws/docker/library/node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build

# Stage 2: Python backend + serve frontend dist
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python deps
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e . || \
    pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn>=0.34.0" \
    "pydantic>=2.10.0" \
    "numpy>=1.26.0" \
    "httpx>=0.28.0" \
    "boto3>=1.35.0" && \
    pip install --no-cache-dir "strands-agents>=0.1.0" || true

# Copy frontend build output from stage 1
COPY --from=frontend-build /frontend/dist ./frontend/dist/

# Copy remaining app code
COPY data/ ./data/
COPY run_all.py ./

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD curl -f http://localhost:8001/health || exit 1

EXPOSE 8001

CMD ["python", "run_all.py"]
