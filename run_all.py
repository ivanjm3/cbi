"""Launcher script to start all services for the Ontology NLP Query System.

Starts all FastAPI processes on their designated ports, waits for health
checks, then registers demo agents with the Orchestrator Hub.

Services:
  - NLP Translator:        port 8001
  - Orchestrator Hub:      port 8002
  - Guardrail Layer:       port 8003
  - Visualization Renderer: port 8004
  - Spoke Agent (JSON/CSV): port 8010 (legacy fallback)
  - Redshift Spoke Agent:  port 8011 (legacy fallback)

MCP Servers (Streamable HTTP):
  - S3 Data Server:        port 8020
  - Redshift Data Server:  port 8021
  - Ontology Server:       port 8022
"""

import asyncio
import signal
import subprocess
import sys
import time

import httpx

# Configure logging before starting services
from src.services.logging_config import configure_logging
configure_logging()

SERVICES = [
    {
        "name": "Orchestrator Hub",
        "module": "src.services.orchestrator_api:app",
        "port": 8002,
    },
    {
        "name": "Guardrail Layer",
        "module": "src.services.guardrail_api:app",
        "port": 8003,
    },
    {
        "name": "Visualization Renderer",
        "module": "src.services.visualization_api:app",
        "port": 8004,
    },
    {
        "name": "Spoke Agent",
        "module": "src.agents.spoke_agent:app",
        "port": 8010,
    },
    {
        "name": "Redshift Spoke Agent",
        "module": "src.agents.redshift_spoke_agent:app",
        "port": 8011,
    },
    {
        "name": "NLP Translator",
        "module": "src.services.nlp_api:app",
        "port": 8001,
    },
]

# MCP Servers — started as Python scripts (not uvicorn) using Streamable HTTP transport
MCP_SERVERS = [
    {
        "name": "MCP S3 Data Server",
        "module": "src.mcp_servers.s3_server",
        "port": 8020,
    },
    {
        "name": "MCP Redshift Data Server",
        "module": "src.mcp_servers.redshift_server",
        "port": 8021,
    },
    {
        "name": "MCP Ontology Server",
        "module": "src.mcp_servers.ontology_server",
        "port": 8022,
    },
]

processes: list[subprocess.Popen] = []


def start_services() -> None:
    """Start all services as separate uvicorn processes and MCP servers."""
    print("=" * 60)
    print("  Ontology NLP Query System — Starting All Services")
    print("=" * 60)
    print()

    # Start MCP servers first (they need to be ready before orchestrator uses them)
    print("  MCP Servers (Streamable HTTP):")
    for mcp in MCP_SERVERS:
        cmd = [
            sys.executable, "-m", mcp["module"],
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
        )
        processes.append(proc)
        print(f"    ✓ {mcp['name']:30s} → http://localhost:{mcp['port']}/mcp")
    print()

    # Start FastAPI services
    print("  FastAPI Services:")
    for svc in SERVICES:
        cmd = [
            sys.executable, "-m", "uvicorn",
            svc["module"],
            "--host", "0.0.0.0",
            "--port", str(svc["port"]),
            "--log-level", "info",
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
        )
        processes.append(proc)
        print(f"    ✓ {svc['name']:30s} → http://localhost:{svc['port']}")

    print()


def wait_for_health(timeout: float = 60.0) -> bool:
    """Wait for all services to respond to health checks.

    Checks FastAPI services via /health endpoints and MCP servers
    via their /mcp endpoint availability.

    Args:
        timeout: Maximum seconds to wait.

    Returns:
        True if all services are healthy, False if timeout reached.
    """
    print("Waiting for services to be ready...")
    start = time.time()

    while time.time() - start < timeout:
        all_ready = True

        # Check MCP servers (they respond on /mcp with Streamable HTTP)
        for mcp in MCP_SERVERS:
            try:
                resp = httpx.get(
                    f"http://localhost:{mcp['port']}/mcp",
                    timeout=2.0,
                )
                # MCP Streamable HTTP endpoint returns 405/406 for GET (expects POST)
                # Any HTTP response means the server is up and listening
                if resp.status_code not in (200, 400, 405, 406):
                    all_ready = False
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                all_ready = False
                break

        if not all_ready:
            time.sleep(1.0)
            continue

        # Check FastAPI services
        for svc in SERVICES:
            try:
                resp = httpx.get(
                    f"http://localhost:{svc['port']}/health",
                    timeout=2.0,
                )
                if resp.status_code != 200:
                    all_ready = False
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                all_ready = False
                break

        if all_ready:
            print("  All services are healthy!")
            return True

        time.sleep(1.0)

    print("  WARNING: Some services did not become healthy within timeout.")
    return False


async def register_agents() -> None:
    """Register demo agents after services are up."""
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
    """Entry point: start services, wait for health, register agents."""
    # Handle Ctrl+C
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    start_services()

    if wait_for_health():
        print("\nRegistering demo agents...")
        asyncio.run(register_agents())
        print("\n" + "=" * 60)
        print("  System Ready!")
        print("=" * 60)
        print()
        print("  Submit queries to: POST http://localhost:8001/query")
        print('  Body: {"query_text": "show me quarterly sales revenue"}')
        print()
        print("  MCP Endpoints (Streamable HTTP):")
        print("    S3 Data:    http://localhost:8020/mcp")
        print("    Redshift:   http://localhost:8021/mcp")
        print("    Ontology:   http://localhost:8022/mcp")
        print()
        print("  Press Ctrl+C to stop all services.")
        print()

        # Keep running until interrupted
        try:
            while True:
                # Check if any process died
                for i, proc in enumerate(processes):
                    if proc.poll() is not None:
                        print(f"  WARNING: {SERVICES[i]['name']} has stopped!")
                time.sleep(5)
        except KeyboardInterrupt:
            shutdown()
    else:
        print("Startup failed. Shutting down...")
        shutdown()


if __name__ == "__main__":
    main()
