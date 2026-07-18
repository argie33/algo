#!/usr/bin/env python3
"""Trace dashboard imports to find what's blocking."""

import os
import sys
import logging
import threading

os.environ["LOCAL_MODE"] = "true"
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.getcwd())

def trace_import(name):
    logger.info(f">>> Importing: {name}")
    return __import__(name, fromlist=[''])

try:
    logger.info("Importing dashboard.api_data_layer...")
    import dashboard.api_data_layer
    logger.info("✓ api_data_layer imported")

    logger.info("Importing dashboard.fetchers_common...")
    import dashboard.fetchers_common
    logger.info("✓ fetchers_common imported")

    logger.info("Importing dashboard.fetchers_config...")
    import dashboard.fetchers_config
    logger.info("✓ fetchers_config imported")

    logger.info("Importing dashboard.fetchers_market...")
    import dashboard.fetchers_market
    logger.info("✓ fetchers_market imported")

    logger.info("Importing dashboard.fetchers...")
    import dashboard.fetchers
    logger.info("✓ fetchers imported")

    logger.info("Importing dashboard.panel_registry...")
    import dashboard.panel_registry
    logger.info("✓ panel_registry imported")

    logger.info("Importing dashboard.renderers...")
    import dashboard.renderers
    logger.info("✓ renderers imported")

    logger.info("Importing dashboard.dashboard module...")
    import dashboard.dashboard
    logger.info("✓ dashboard module imported")

except Exception as e:
    import traceback
    logger.error(f"Error: {type(e).__name__}: {e}")
    traceback.print_exc()
