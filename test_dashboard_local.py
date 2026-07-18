#!/usr/bin/env python3
"""Test dashboard startup in local mode to capture errors."""

import os
import sys
import logging

# Set local mode env vars
os.environ["LOCAL_MODE"] = "true"
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, os.getcwd())

try:
    logger.info("=== TEST 1: Import dashboard module ===")
    from dashboard.dashboard import main, run_once, load_all
    logger.info("✓ Imports successful")

    logger.info("\n=== TEST 2: Try loading data ===")
    # This should timeout or throw an error if there's an issue
    import threading
    import time

    data_result = [None]
    error_result = [None]

    def load_data():
        try:
            data_result[0] = load_all()
        except Exception as e:
            error_result[0] = e

    thread = threading.Thread(target=load_data, daemon=False)
    thread.start()
    thread.join(timeout=10.0)

    if thread.is_alive():
        logger.error("✗ load_all() took too long (>10s)")
    elif error_result[0]:
        logger.error(f"✗ load_all() failed: {error_result[0]}")
    else:
        data = data_result[0]
        logger.info(f"✓ load_all() completed: {len(data)} items")

        error_keys = [k for k, v in data.items() if isinstance(v, dict) and '_error' in v]
        if error_keys:
            logger.warning(f"Data contains errors in: {error_keys}")
            for k in error_keys:
                logger.warning(f"  {k}: {data[k].get('_error', 'unknown error')[:100]}")

except Exception as e:
    import traceback
    logger.error(f"✗ Fatal error: {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)

logger.info("\n=== TEST COMPLETE ===")
