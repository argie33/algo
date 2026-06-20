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

import socket
import sys
from pathlib import Path
import json
import requests


def setup_imports():
    """Set up sys.path for loader scripts to find utils, algo, and other packages."""
    # Loader files are at /loaders/*.py
    # Project root is at /
    loader_dir = Path(__file__).parent
    project_root = loader_dir.parent

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def setup_loader_timeouts(socket_timeout_sec: float = 30.0):
    """Configure socket-level timeouts for all network operations in loaders.

    Args:
        socket_timeout_sec: Socket-level timeout in seconds (default 30s).
                           This prevents indefinite hangs in underlying network libraries
                           that don't respect requests.timeout settings.

    Note: This should be called early in loader initialization, before any network calls.
    """
    try:
        socket.setdefaulttimeout(socket_timeout_sec)
    except (requests.RequestException, requests.Timeout, json.JSONDecodeError) as e:
        import logging

        logging.warning(f"Could not set socket timeout: {e}")
