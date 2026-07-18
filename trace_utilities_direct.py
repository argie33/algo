#!/usr/bin/env python3
"""Directly import utilities module."""

import os
import sys
import logging
import threading

os.environ["LOCAL_MODE"] = "true"
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.getcwd())

def import_utilities():
    """Run import in a thread to detect hangs."""
    logger.info("Starting utilities import in thread...")
    try:
        import dashboard.utilities
        logger.info("✓ utilities imported successfully")
    except Exception as e:
        logger.error(f"✗ Import failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

thread = threading.Thread(target=import_utilities, daemon=False)
thread.start()
thread.join(timeout=10.0)

if thread.is_alive():
    logger.error("✗ Import hung for 10+ seconds")
    import sys
    sys.exit(1)
else:
    logger.info("Import completed successfully")
