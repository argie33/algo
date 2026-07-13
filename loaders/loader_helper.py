"""
Loader helper module to provide common utilities for all data loaders.

This module centralizes path setup for loader scripts so they can import from
utils, algo, and other root packages without doing their own sys.path manipulation.

Usage in loader scripts:
    from loaders.loader_helper import setup_imports, setup_loader_timeouts
    setup_imports()
    setup_loader_timeouts()

    # Now you can import from root packages
    from utils.db.context import DatabaseContext
    from utils import ...
"""

import logging
import socket
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_imports() -> None:
    # Loader files are at /loaders/*.py
    # Project root is at /
    loader_dir = Path(__file__).parent
    project_root = loader_dir.parent

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def setup_loader_timeouts(socket_timeout_sec: float = 30.0) -> None:
    """Configure socket-level timeouts for all network operations in loaders.

    CRITICAL: Fails hard if socket timeout cannot be set. Indefinite hangs in network
    operations would stall data loading, potentially causing stale data to be used for
    trading decisions.

    Args:
        socket_timeout_sec: Socket-level timeout in seconds (default 30s).
                           This prevents indefinite hangs in underlying network libraries
                           that don't respect requests.timeout settings.

    Raises:
        RuntimeError: If socket timeout cannot be set (configuration/system error)

    Note: This should be called early in loader initialization, before any network calls.
    """
    try:
        socket.setdefaulttimeout(socket_timeout_sec)
    except Exception as e:
        raise RuntimeError(
            f"CRITICAL: Could not set socket timeout to {socket_timeout_sec}s: {e}. "
            "Network operations may hang indefinitely, causing data loaders to stall. "
            "Check system configuration and socket.setdefaulttimeout() availability."
        ) from e
