#!/bin/bash
# =============================================================================
# Launcher: Start the full Conversational BI system WITH MCP servers
# =============================================================================
#
# Starts everything in one shot:
#   1. MCP Redshift server (port 7010)
#   2. MCP S3 server (port 7020)
#   3. MCP Adapter Layer (port 8012)
#   4. All core services via run_all.py (ports 8001-8011)
#
# Prerequisites:
#   pip install -e ".[dev]"
#   cd mcps/mcp-redshift && pip install -e . && cd ../..
#   cd mcps/mcp-s3 && pip install -e . && cd ../..
#
# Usage:   bash run_all_with_mcp.sh
# Stop:    Ctrl+C
# =============================================================================

echo ""
echo "============================================================"
echo "  Conversational BI + MCP Servers — Full Stack Launcher"
echo "============================================================"
echo ""

# Propagate AWS profile to ALL child processes (S3, Redshift, OntologyStore, etc.)
export AWS_PROFILE=PowerUserAccess-654654478821

# Track PIDs for cleanup
PIDS=()

cleanup() {
    echo ""
    echo "Shutting down all services..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    wait 2>/dev/null
    echo "Done."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# --- MCP Redshift Server (port 7010) ---
echo "[1/4] Starting MCP Redshift server on port 7010..."
MCP_REDSHIFT_TRANSPORT=streamable-http \
MCP_REDSHIFT_HTTP_PORT=7010 \
AWS_PROFILE=PowerUserAccess-654654478821 \
python -c "from mcp_redshift.server import main; main()" &
PIDS+=($!)
sleep 4

# --- MCP S3 Server (port 7020) ---
echo "[2/4] Starting MCP S3 server on port 7020..."
MCP_S3_TRANSPORT=streamable-http \
MCP_S3_HTTP_PORT=7020 \
MCP_S3_DATASET_REGISTRY_PATH="mcps/mcp-s3/test_registry.yaml" \
AWS_PROFILE=PowerUserAccess-654654478821 \
python -c "from mcp_s3.server import main; main()" &
PIDS+=($!)
sleep 4

# --- MCP Adapter Layer (port 8012) ---
echo "[3/4] Starting MCP Adapter on port 8012..."
MCP_ADAPTER_REDSHIFT_TRANSPORT=streamable-http \
MCP_ADAPTER_REDSHIFT_HOST=localhost \
MCP_ADAPTER_REDSHIFT_PORT=7010 \
MCP_ADAPTER_S3_TRANSPORT=streamable-http \
MCP_ADAPTER_S3_HOST=localhost \
MCP_ADAPTER_S3_PORT=7020 \
python -m uvicorn src.agents.mcp_adapter.service:app --host 0.0.0.0 --port 8012 --log-level info &
PIDS+=($!)
sleep 5

# --- Core System (ports 8001-8011) with MCP flag enabled ---
echo "[4/4] Starting core system with USE_MCP_ADAPTER=true..."
echo ""
export USE_MCP_ADAPTER=true
export MCP_ADAPTER_REDSHIFT_TRANSPORT=streamable-http
export MCP_ADAPTER_REDSHIFT_HOST=localhost
export MCP_ADAPTER_REDSHIFT_PORT=7010
export MCP_ADAPTER_S3_TRANSPORT=streamable-http
export MCP_ADAPTER_S3_HOST=localhost
export MCP_ADAPTER_S3_PORT=7020
python run_all.py &
PIDS+=($!)

echo ""
echo "============================================================"
echo "  All services launching. Ctrl+C to stop everything."
echo ""
echo "  Ports:"
echo "    8001  NLP Translator (entry point)"
echo "    8002  Orchestrator Hub"
echo "    8003  Guardrail Layer"
echo "    8004  Visualization Renderer"
echo "    8010  S3 Spoke Agent (legacy fallback)"
echo "    8011  Redshift Spoke Agent (legacy fallback)"
echo "    8012  MCP Adapter Layer"
echo "    7010  MCP Redshift Server"
echo "    7020  MCP S3 Server"
echo ""
echo "  Test:"
echo "    curl -X POST http://localhost:8001/query \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"query_text\": \"show me quarterly sales revenue\"}'"
echo ""
echo "  Health checks:"
echo "    curl http://localhost:8012/health"
echo "    curl http://localhost:7010/mcp  (MCP Redshift)"
echo "    curl http://localhost:7020/mcp  (MCP S3)"
echo "============================================================"
echo ""

# Wait for all background processes
wait
