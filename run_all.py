"""Launcher script to start all services for the Ontology NLP Query System.

Starts all 6 FastAPI processes on their designated ports, waits for health
checks, then registers demo agents with the Orchestrator Hub.

Services:
  - NLP Translator:        port 8001
  - Orchestrator Hub:      port 8002
  - Guardrail Layer:       port 8003
  - Visualization Renderer: port 8004
  - Spoke Agent A (JSON):  port 8010
  - Spoke Agent B (CSV):   port 8011
"""

import asyncio
import signal
import subprocess
import sys
import time

import httpx

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
        "name": "NLP Translator",
        "module": "src.services.nlp_api:app",
        "port": 8001,
    },
]

processes: list[subprocess.Popen] = []


def start_services() -> None:
    """Start all services as separate uvicorn processes."""
    print("=" * 60)
    print("  Ontology NLP Query System — Starting All Services")
    print("=" * 60)
    print()

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
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(proc)
        print(f"  ✓ {svc['name']:30s} → http://localhost:{svc['port']}")

    print()


def wait_for_health(timeout: float = 30.0) -> bool:
    """Wait for all services to respond to health checks.

    Args:
        timeout: Maximum seconds to wait.

    Returns:
        True if all services are healthy, False if timeout reached.
    """
    print("Waiting for services to be ready...")
    start = time.time()

    while time.time() - start < timeout:
        all_ready = True
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
