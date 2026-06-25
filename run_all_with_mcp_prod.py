"""Production launcher: MCP servers + Adapter + Core services in one container.

Starts all services needed for the full MCP-enabled Conversational BI system.
Designed for App Runner deployment where everything runs in a single container.

Services started:
  - MCP Redshift Server:    port 7010 (streamable-http)
  - MCP S3 Server:          port 7020 (streamable-http)
  - MCP Adapter Layer:      port 8012
  - NLP Translator:         port 8001 (entry point / health check)
  - Orchestrator Hub:       port 8002
  - Guardrail Layer:        port 8003
  - Visualization Renderer: port 8004
  - Spoke Agent (legacy):   port 8010
  - Redshift Spoke Agent:   port 8011
"""

import asyncio
import os
import signal
import subprocess
import sys
import time

import httpx

# Configure logging
from src.services.logging_config import configure_logging
configure_logging()

# ─── Environment Configuration ──────────────────────────────────────────────
# Set MCP feature flags and transport config for in-container deployment
os.environ.setdefault("USE_MCP_ADAPTER", "true")
os.environ.setdefault("USE_MCP_REDSHIFT", "true")
os.environ.setdefault("USE_MCP_S3", "true")

# MCP servers run locally in the same container
os.environ["MCP_ADAPTER_REDSHIFT_TRANSPORT"] = "streamable-http"
os.environ["MCP_ADAPTER_REDSHIFT_HOST"] = "localhost"
os.environ["MCP_ADAPTER_REDSHIFT_PORT"] = "7010"
os.environ["MCP_ADAPTER_S3_TRANSPORT"] = "streamable-http"
os.environ["MCP_ADAPTER_S3_HOST"] = "localhost"
os.environ["MCP_ADAPTER_S3_PORT"] = "7020"

# MCP server env vars
os.environ.setdefault("MCP_REDSHIFT_TRANSPORT", "streamable-http")
os.environ.setdefault("MCP_REDSHIFT_HTTP_PORT", "7010")
os.environ.setdefault("MCP_S3_TRANSPORT", "streamable-http")
os.environ.setdefault("MCP_S3_HTTP_PORT", "7020")

# S3 dataset registry for MCP S3 server
os.environ.setdefault("MCP_S3_DATASET_REGISTRY_PATH", "mcps/mcp-s3/test_registry.yaml")

# ─── Service Definitions ────────────────────────────────────────────────────

# MCP Servers (started first, need time to initialize)
MCP_SERVICES = [
    {
        "name": "MCP Redshift Server",
        "cmd": [sys.executable, "-c", "from mcp_redshift.server import main; main()"],
        "port": 7010,
        "health_path": "/mcp",
        "startup_delay": 3,
    },
    {
        "name": "MCP S3 Server",
        "cmd": [sys.executable, "-c", "from mcp_s3.server import main; main()"],
        "port": 7020,
        "health_path": "/mcp",
        "startup_delay": 3,
    },
]

# MCP Adapter (depends on MCP servers being available)
ADAPTER_SERVICE = {
    "name": "MCP Adapter",
    "module": "src.agents.mcp_adapter.service:app",
    "port": 8012,
}

# Core services
CORE_SERVICES = [
    {"name": "Orchestrator Hub", "module": "src.services.orchestrator_api:app", "port": 8002},
    {"name": "Guardrail Layer", "module": "src.services.guardrail_api:app", "port": 8003},
    {"name": "Visualization Renderer", "module": "src.services.visualization_api:app", "port": 8004},
    {"name": "Spoke Agent (Legacy)", "module": "src.agents.spoke_agent:app", "port": 8010},
    {"name": "Redshift Spoke Agent", "module": "src.agents.redshift_spoke_agent:app", "port": 8011},
    {"name": "NLP Translator", "module": "src.services.nlp_api:app", "port": 8001},
]

processes: list[subprocess.Popen] = []


def start_mcp_servers() -> None:
    """Start MCP servers with their environment."""
    print("─── Starting MCP Servers ───")
    for svc in MCP_SERVICES:
        proc = subprocess.Popen(
            svc["cmd"],
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )
        processes.append(proc)
        print(f"  ✓ {svc['name']:30s} → http://localhost:{svc['port']}")
        time.sleep(svc.get("startup_delay", 2))


def start_adapter() -> None:
    """Start MCP Adapter Layer."""
    print("─── Starting MCP Adapter ───")
    svc = ADAPTER_SERVICE
    cmd = [
        sys.executable, "-m", "uvicorn",
        svc["module"],
        "--host", "0.0.0.0",
        "--port", str(svc["port"]),
        "--log-level", "info",
    ]
    proc = subprocess.Popen(cmd, stdout=sys.stdout, stderr=subprocess.STDOUT)
    processes.append(proc)
    print(f"  ✓ {svc['name']:30s} → http://localhost:{svc['port']}")
    time.sleep(3)


def start_core_services() -> None:
    """Start all core FastAPI services."""
    print("─── Starting Core Services ───")
    for svc in CORE_SERVICES:
        cmd = [
            sys.executable, "-m", "uvicorn",
            svc["module"],
            "--host", "0.0.0.0",
            "--port", str(svc["port"]),
            "--log-level", "info",
        ]
        proc = subprocess.Popen(cmd, stdout=sys.stdout, stderr=subprocess.STDOUT)
        processes.append(proc)
        print(f"  ✓ {svc['name']:30s} → http://localhost:{svc['port']}")


def wait_for_health(timeout: float = 90.0) -> bool:
    """Wait for critical services to be healthy."""
    print("\nWaiting for services to be ready...")
    critical_ports = [8001, 8002, 8012]
    start = time.time()

    while time.time() - start < timeout:
        all_ready = True
        for port in critical_ports:
            try:
                resp = httpx.get(f"http://localhost:{port}/health", timeout=3.0)
                if resp.status_code != 200:
                    all_ready = False
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                all_ready = False
                break

        if all_ready:
            print("  ✓ All critical services healthy!")
            return True
        time.sleep(2.0)

    print("  ⚠ Timeout waiting for services — continuing anyway")
    return False


async def register_agents() -> None:
    """Register agents after services are up."""
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
    """Entry point: start all services in order, register agents."""
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("=" * 60)
    print("  Conversational BI + MCP — Production Launcher")
    print("=" * 60)
    print(f"  MCP Enabled: {os.environ.get('USE_MCP_ADAPTER', 'false')}")
    print()

    # Phase 1: MCP servers
    start_mcp_servers()

    # Phase 2: MCP Adapter (connects to MCP servers)
    start_adapter()

    # Phase 3: Core services
    start_core_services()

    # Phase 4: Health check and agent registration
    if wait_for_health():
        print("\nRegistering agents...")
        asyncio.run(register_agents())

    print("\n" + "=" * 60)
    print("  System Ready! (MCP-enabled)")
    print("=" * 60)
    print("  Entry point: http://localhost:8001/query")
    print("  Health:      http://localhost:8001/health")
    print("  MCP Health:  http://localhost:8012/health")
    print()

    # Keep running
    try:
        while True:
            for i, proc in enumerate(processes):
                if proc.poll() is not None:
                    print(f"  ⚠ Process {i} has stopped (exit={proc.returncode})")
            time.sleep(10)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
