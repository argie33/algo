#!/usr/bin/env python3
"""
Centralized logging configuration.

All modules should use get_logger() instead of:
  logging.basicConfig(...)
  logger = logging.getLogger(__name__)

This pattern was repeated identically in 20+ files.
"""

import logging
import sys

# Configure root logger once
_configured = False


def setup_logging(level=logging.INFO, format_str=None):
    """Configure logging with standard format.

    Args:
        level: Logging level (default INFO)
        format_str: Custom format string (default: timestamp [level] module: message)
    """
    global _configured

    if _configured:
        return

    if format_str is None:
        format_str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logging.basicConfig(level=level, format=format_str, stream=sys.stdout)
    _configured = True


def get_logger(name):
    """Get logger instance with standard configuration.

    Usage:
        from utils.logging_setup import get_logger
        logger = get_logger(__name__)
        logger.info("Message")

    Replaces the standard pattern:
        logging.basicConfig(...)
        logger = logging.getLogger(__name__)
    """
    setup_logging()
    return logging.getLogger(name)


setup_logging()
