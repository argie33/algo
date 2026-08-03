#!/usr/bin/env python3
"""Health check and diagnostic script for dev_server.

Verifies the dev_server is running and responsive, with detailed diagnostics if not.
"""

import json
import logging
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="[HEALTH] %(message)s")
logger = logging.getLogger(__name__)


def check_port_open(port: int, timeout: float = 1.0) -> bool:
    """Check if port is listening on IPv4 or IPv6."""
    for host, family in [("127.0.0.1", socket.AF_INET), ("::1", socket.AF_INET6)]:
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except Exception as e:
            logger.debug(f"Port check failed for {host}: {e}")
    return False


def get_process_holding_port(port: int) -> Optional[int]:
    """Get PID of process holding a port (Windows only)."""
    if sys.platform != "win32":
        return None

    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        return int(parts[-1])
                    except ValueError:
                        pass
    except Exception as e:
        logger.warning(f"Could not get process for port: {e}")

    return None


def kill_orphaned_server(port: int = 3001) -> bool:
    """Kill any process holding the port."""
    pid = get_process_holding_port(port)
    if not pid:
        return False

    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                timeout=5,
            )
            logger.info(f"Killed orphaned process {pid} on port {port}")
            time.sleep(1)
            return True
    except Exception as e:
        logger.warning(f"Failed to kill process {pid}: {e}")
        return False

    return False


def check_dev_server_health(timeout: int = 5) -> tuple[bool, str]:
    """Check if dev_server is running and responsive.

    Returns: (is_healthy, message)
    """
    port = 3001

    # Check port is open
    if not check_port_open(port):
        return False, f"Port {port} not responding"

    # Try to connect and make a simple request
    try:
        import requests

        response = requests.get(
            f"http://127.0.0.1:{port}/api/algo/health",
            timeout=timeout,
        )
        if response.status_code == 200:
            return True, "Dev server healthy"
        else:
            return False, f"Health check returned {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused (port open but server not responding)"
    except requests.exceptions.Timeout:
        return False, "Health check timed out (server hanging?)"
    except Exception as e:
        return False, f"Health check error: {type(e).__name__}: {e}"


def diagnose_issue() -> None:
    """Run comprehensive diagnostics."""
    logger.info("=" * 60)
    logger.info("DEV SERVER DIAGNOSTICS")
    logger.info("=" * 60)

    # Check port status
    port = 3001
    is_open = check_port_open(port)
    logger.info(f"Port {port} status: {'OPEN' if is_open else 'CLOSED'}")

    if is_open:
        pid = get_process_holding_port(port)
        if pid:
            logger.info(f"Process holding port: PID {pid}")

        # Check health
        is_healthy, msg = check_dev_server_health()
        logger.info(f"Server health: {'✓ HEALTHY' if is_healthy else f'✗ {msg}'}")
    else:
        logger.info("Port is closed - dev_server not running")

    logger.info("=" * 60)
    logger.info("RECOMMENDATIONS:")
    logger.info("=" * 60)

    if not is_open:
        logger.info("1. Start dev_server: python start_dashboard_dev.py")
        logger.info("2. Or manually: python lambda/api/dev_server.py")
    else:
        is_healthy, msg = check_dev_server_health()
        if not is_healthy:
            logger.info(f"Dev server is stuck: {msg}")
            logger.info("Try restarting: Kill process and run start_dashboard_dev.py")
            pid = get_process_holding_port(port)
            if pid:
                logger.info(f"Kill command: taskkill /PID {pid} /F")
        else:
            logger.info("Dev server is running and healthy!")


def main() -> int:
    """Main entry point."""
    parser_help = """
    Usage: python dev_server_health_check.py [--diagnose] [--kill-orphaned]

    --diagnose       Run full diagnostics
    --kill-orphaned  Kill any orphaned processes on port 3001
    """

    if "--diagnose" in sys.argv:
        diagnose_issue()
        return 0

    if "--kill-orphaned" in sys.argv:
        if kill_orphaned_server():
            logger.info("Orphaned server killed successfully")
            return 0
        else:
            logger.info("No orphaned server found")
            return 0

    # Default: just check health
    is_healthy, msg = check_dev_server_health()
    if is_healthy:
        logger.info("✓ Dev server is healthy")
        return 0
    else:
        logger.error(f"✗ Dev server issue: {msg}")
        diagnose_issue()
        return 1


if __name__ == "__main__":
    sys.exit(main())
