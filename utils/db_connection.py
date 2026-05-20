#!/usr/bin/env python3
"""
Unified database connection factory with connection pool monitoring.

Centralizes all psycopg2.connect() calls to a single source.
Handles retries, pooling, proper credential fallback, and connection tracking.
"""

import psycopg2
import logging
import socket
import os

from config.credential_helper import get_db_config

logger = logging.getLogger(__name__)

# Import connection monitor - integrates pool health tracking
try:
    from algo.algo_connection_monitor import on_connect, on_disconnect
except ImportError:
    # Fallback if monitor unavailable
    def on_connect():
        pass
    def on_disconnect():
        pass


class TrackedConnection:
    """Wraps psycopg2 connection to track pool utilization."""

    def __init__(self, conn):
        self._conn = conn
        on_connect()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        on_disconnect()
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _try_dns_with_servers(hostname: str, nameservers: list = None) -> list:
    """Try DNS resolution with explicitly configured nameservers.

    Uses dnspython if available, falls back to socket if not.
    """
    try:
        import dns.resolver

        if nameservers:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = nameservers
        else:
            resolver = dns.resolver.Resolver()

        answers = resolver.resolve(hostname, 'A')
        return [str(rdata) for rdata in answers]
    except ImportError:
        # dnspython not available, return empty list
        return []
    except Exception as e:
        logger.debug(f"DNS resolution with custom servers failed: {e}")
        return []


def _test_dns_resolution(hostname: str) -> None:
    """Test DNS resolution and log detailed diagnostics.

    This helps identify VPC DNS configuration issues in Lambda.
    """
    try:
        logger.info(f"Testing DNS resolution for: {hostname}")

        # Test socket.getaddrinfo (what psycopg2 uses)
        results = socket.getaddrinfo(hostname, 5432, socket.AF_INET, socket.SOCK_STREAM)
        if results:
            resolved_ips = [r[4][0] for r in results]
            logger.info(f"✓ DNS resolution successful: {hostname} → {resolved_ips}")
        else:
            logger.warning(f"⚠ DNS resolution returned no results for: {hostname}")

    except socket.gaierror as e:
        logger.error(f"✗ DNS resolution failed for {hostname}: {e}")
        logger.error(f"  Error code: {e.errno}, {e.strerror}")

        # Try to diagnose the issue
        logger.info("Attempting diagnostic checks...")

        # Check if we're in Lambda
        if os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
            logger.info("Running in AWS Lambda environment")
            if os.getenv('AWS_LAMBDA_LOG_GROUP_NAME'):
                logger.info(f"Lambda log group: {os.getenv('AWS_LAMBDA_LOG_GROUP_NAME')}")

        # Check DNS configuration
        try:
            with open('/etc/resolv.conf', 'r') as f:
                resolv_content = f.read()
                logger.info(f"System /etc/resolv.conf:\n{resolv_content}")
        except Exception as err:
            logger.debug(f"Could not read /etc/resolv.conf: {err}")

        # Try alternative DNS servers
        logger.info("Testing alternative DNS servers...")
        alt_servers = [
            ('8.8.8.8', "Google Public DNS"),
            ('1.1.1.1', "Cloudflare DNS"),
            ('169.254.169.253', "AWS Route 53 Resolver"),
        ]

        for ip, name in alt_servers:
            logger.info(f"Attempting DNS lookup via {name} ({ip})...")
            try:
                ips = _try_dns_with_servers(hostname, [ip])
                if ips:
                    logger.info(f"  ✓ Resolution via {name} succeeded: {hostname} → {ips}")
                    # If we found a resolution via alternative server, log the IP we can use
                    return
            except Exception as err:
                logger.debug(f"  ✗ DNS resolution via {name} failed: {err}")

        raise


def get_db_connection(max_retries: int = 3, timeout: int = 5):
    """Get a PostgreSQL connection with automatic retry and credential management.

    Tracks connection pool utilization via connection monitor.

    Args:
        max_retries: Number of connection attempts before failing
        timeout: Connection timeout in seconds

    Returns:
        TrackedConnection: Connected database connection (tracks pool health)

    Raises:
        psycopg2.OperationalError: If connection fails after max retries
    """
    config = get_db_config()
    config["connect_timeout"] = timeout

    # Test DNS resolution before attempting connection
    _test_dns_resolution(config["host"])

    last_error = None
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(**config)
            logger.debug(f"Database connection established (attempt {attempt + 1})")
            return TrackedConnection(conn)
        except psycopg2.OperationalError as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning(f"Connection attempt {attempt + 1} failed, retrying: {e}")
            else:
                logger.error(f"Failed to connect to database after {max_retries} attempts: {e}")

    raise last_error or psycopg2.OperationalError("Database connection failed")
