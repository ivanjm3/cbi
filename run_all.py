"""Launcher script to start all services for the Ontology NLP Query System.

Starts all FastAPI processes on their designated ports, waits for health
checks, then registers demo agents with the Orchestrator Hub.

Services:
  - NLP Translator:        port 8001  ← started FIRST (health check target)
  - Orchestrator Hub:      port 8002
  - Guardrail Layer:       port 8003
  - Visualization Renderer: port 8004
  - Scheduling API:        port 8005
  - MCP Redshift Server:   port 7010  (streamable-http, started in background)
  - MCP S3 Server:         port 7020  (streamable-http, started in background)
  - MCP Adapter Layer:     port 8012
  - Spoke Agent (JSON/CSV): port 8010
  - Redshift Spoke Agent:  port 8011
"""

import asyncio
import os
import signal
import subprocess
import sys
import time

# ─── MCP Configuration ───────────────────────────────────────────────────────
# MCP servers run as separate processes inside the container (streamable-http).
# The MCP Adapter connects to them on localhost.
os.environ.setdefault("USE_MCP_ADAPTER", "true")
os.environ.setdefault("USE_MCP_REDSHIFT", "true")
os.environ.setdefault("USE_MCP_S3", "true")
# Force localhost for MCP servers since they run locally alongside this process
os.environ["MCP_ADAPTER_REDSHIFT_TRANSPORT"] = "streamable-http"
os.environ["MCP_ADAPTER_REDSHIFT_HOST"] = "localhost"
os.environ["MCP_ADAPTER_REDSHIFT_PORT"] = "7010"
os.environ["MCP_ADAPTER_S3_TRANSPORT"] = "streamable-http"
os.environ["MCP_ADAPTER_S3_HOST"] = "localhost"
os.environ["MCP_ADAPTER_S3_PORT"] = "7020"
# MCP server transport settings
os.environ.setdefault("MCP_REDSHIFT_TRANSPORT", "streamable-http")
os.environ.setdefault("MCP_REDSHIFT_HTTP_PORT", "7010")
os.environ.setdefault("MCP_S3_TRANSPORT", "streamable-http")
os.environ.setdefault("MCP_S3_HTTP_PORT", "7020")
os.environ.setdefault("MCP_S3_DATASET_REGISTRY_PATH", "mcps/mcp-s3/test_registry.yaml")

# Propagate the active AWS profile (e.g. an SSO profile from `aws configure sso`)
# to the MCP S3 server so credential resolution doesn't fall back to stale
# static keys in ~/.aws/credentials. Set AWS_PROFILE before running, e.g.:
#   AWS_PROFILE=PowerUserAccess-654654478821 python run_all.py
_aws_profile = os.environ.get("AWS_PROFILE")
if _aws_profile:
    os.environ.setdefault("MCP_S3_AWS_PROFILE", _aws_profile)
# ─────────────────────────────────────────────────────────────────────────────

import httpx

# Configure logging before starting services
from src.services.logging_config import configure_logging
configure_logging()

# ─── Service Definitions ─────────────────────────────────────────────────────

# NLP Translator starts FIRST — this is App Runner's health check target.
# It must be up within ~60s for the deployment to succeed.
NLP_SERVICE = {
    "name": "NLP Translator",
    "module": "src.services.nlp_api:app",
    "port": 8001,
}

# Core services (start alongside NLP)
CORE_SERVICES = [
    {"name": "Orchestrator Hub",       "module": "src.services.orchestrator_api:app", "port": 8002},
    {"name": "Guardrail Layer",        "module": "src.services.guardrail_api:app",    "port": 8003},
    {"name": "Visualization Renderer", "module": "src.services.visualization_api:app","port": 8004},
    {"name": "Scheduling API",         "module": "src.services.scheduling_api:app",   "port": 8005},
    {"name": "Spoke Agent",            "module": "src.agents.spoke_agent:app",        "port": 8010},
    {"name": "Redshift Spoke Agent",   "module": "src.agents.redshift_spoke_agent:app","port": 8011},
]

# MCP servers — started as plain subprocesses using isolated venvs.
# In the container, each venv has its own Python with its own deps.
# Locally (dev), falls back to sys.executable if venv paths don't exist.
_MCP_RS_PYTHON = "/app/venv-mcp-rs/bin/python" if os.path.exists("/app/venv-mcp-rs/bin/python") else sys.executable
_MCP_S3_PYTHON = "/app/venv-mcp-s3/bin/python" if os.path.exists("/app/venv-mcp-s3/bin/python") else sys.executable

MCP_SERVER_PROCS = [
    {
        "name": "MCP Redshift Server",
        "cmd": [_MCP_RS_PYTHON, "-c", "from mcp_redshift.server import main; main()"],
        "port": 7010,
        "env_extra": {
            "MCP_REDSHIFT_TRANSPORT": "streamable-http",
            "MCP_REDSHIFT_HTTP_PORT": "7010",
        },
    },
    {
        "name": "MCP S3 Server",
        "cmd": [_MCP_S3_PYTHON, "-c", "from mcp_s3.server import main; main()"],
        "port": 7020,
        "env_extra": {
            "MCP_S3_TRANSPORT": "streamable-http",
            "MCP_S3_HTTP_PORT": "7020",
            "MCP_S3_DATASET_REGISTRY_PATH": "mcps/mcp-s3/test_registry.yaml",
        },
    },
]

# MCP Adapter service
MCP_ADAPTER_SERVICE = {
    "name": "MCP Adapter",
    "module": "src.agents.mcp_adapter.service:app",
    "port": 8012,
}

processes: list[subprocess.Popen] = []


def _start_uvicorn(svc: dict) -> subprocess.Popen:
    cmd = [
        sys.executable, "-m", "uvicorn",
        svc["module"],
        "--host", "0.0.0.0",
        "--port", str(svc["port"]),
        "--log-level", "info",
    ]
    return subprocess.Popen(cmd, stdout=sys.stdout, stderr=subprocess.STDOUT)


def _wait_for_port(port: int, timeout: float = 30.0) -> bool:
    """Poll until a port is accepting HTTP connections."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = httpx.get(f"http://localhost:{port}/health", timeout=2.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def _wait_for_mcp(port: int, timeout: float = 45.0) -> bool:
    """Poll until an MCP server's /mcp endpoint responds."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = httpx.get(f"http://localhost:{port}/mcp", timeout=3.0)
            # Any response (200 or 405/406) means the server is up
            if resp.status_code in (200, 405, 406):
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def start_services() -> None:
    """Start all services in the correct order."""
    print("=" * 60)
    print("  Conversational BI + MCP Servers — Production")
    print("=" * 60)
    print()

    # Phase 1: Start NLP Translator FIRST (health check target)
    print("  [1/4] Starting NLP Translator (health check target)...")
    proc = _start_uvicorn(NLP_SERVICE)
    processes.append(proc)
    print(f"        ✓ NLP Translator → http://localhost:8001")
    print()

    # Phase 2: Start all other core services in parallel
    print("  [2/4] Starting core services...")
    for svc in CORE_SERVICES:
        proc = _start_uvicorn(svc)
        processes.append(proc)
        print(f"        ✓ {svc['name']:30s} → http://localhost:{svc['port']}")
    print()

    # Phase 3: Start MCP servers (non-blocking — health check already up)
    print("  [3/4] Starting MCP servers...")
    for mcp_svc in MCP_SERVER_PROCS:
        env = os.environ.copy()
        env.update(mcp_svc.get("env_extra", {}))
        proc = subprocess.Popen(
            mcp_svc["cmd"],
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
            env=env,
        )
        processes.append(proc)
        print(f"        ✓ {mcp_svc['name']:30s} → http://localhost:{mcp_svc['port']}")
    print()

    # Phase 4: Wait for MCP servers, then start MCP Adapter
    print("  [4/4] Waiting for MCP servers, then starting MCP Adapter...")


def wait_for_nlp_health(timeout: float = 60.0) -> bool:
    """Wait for NLP service on 8001 to be healthy."""
    return _wait_for_port(8001, timeout)


def start_mcp_adapter_when_ready() -> None:
    """Wait for MCP servers then start the adapter. Runs in background thread."""
    import threading

    def _run():
        # Wait for MCP servers (give them up to 60s after they were launched)
        mcp_redshift_up = _wait_for_mcp(7010, timeout=60.0)
        mcp_s3_up = _wait_for_mcp(7020, timeout=60.0)

        if mcp_redshift_up:
            print("        ✓ MCP Redshift Server ready on port 7010")
        else:
            print("        ⚠ MCP Redshift Server not ready after 60s — adapter will use fallback")

        if mcp_s3_up:
            print("        ✓ MCP S3 Server ready on port 7020")
        else:
            print("        ⚠ MCP S3 Server not ready after 60s — adapter will use fallback")

        # Start MCP Adapter
        proc = _start_uvicorn(MCP_ADAPTER_SERVICE)
        processes.append(proc)
        print(f"        ✓ MCP Adapter started on port 8012")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


async def register_agents() -> None:
    """Register demo agents after services are up."""
    # Wait a bit for orchestrator to be fully ready
    await asyncio.sleep(5)
    from src.services.register_agents import register_agents as do_register
    await do_register()


def shutdown(signum=None, frame=None) -> None:
    """Gracefully terminate all child processes."""
    print("\nShutting down all services...")
    for proc in processes:
        proc.terminate()
    for proc in processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("All services stopped.")
    sys.exit(0)


def main() -> None:
    """Entry point."""
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    start_services()

    # Wait for NLP health check (App Runner needs this within ~60s)
    print()
    print("  Waiting for NLP Translator to be healthy...")
    if wait_for_nlp_health(timeout=60.0):
        print("  ✓ NLP Translator healthy — App Runner health check will pass")
    else:
        print("  ⚠ NLP Translator not yet healthy — continuing anyway")

    # Start MCP Adapter in background once MCP servers are ready
    start_mcp_adapter_when_ready()

    # Register agents in background
    import threading
    def _register():
        # Wait for orchestrator
        time.sleep(15)
        if _wait_for_port(8002, timeout=60.0):
            asyncio.run(register_agents())
            print("\n  ✓ Agents registered")
    threading.Thread(target=_register, daemon=True).start()

    print()
    print("=" * 60)
    print("  System starting up (MCP-enabled)")
    print("  Entry point: http://localhost:8001/query")
    print("=" * 60)
    print()

    # Keep running, monitor processes
    try:
        while True:
            for i, proc in enumerate(processes):
                if proc.poll() is not None:
                    print(f"  ⚠ Process stopped (exit={proc.returncode}), restarting...")
            time.sleep(10)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()

