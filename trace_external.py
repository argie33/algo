#!/usr/bin/env python3
"""Trace fetchers_external imports."""

import os
import sys
import logging

os.environ["LOCAL_MODE"] = "true"
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.getcwd())

try:
    logger.info("1. Importing utils.validation.framework...")
    from utils.validation.framework import safe_float
    logger.info("✓ safe_float imported")

    logger.info("2. Importing dashboard.api_data_layer...")
    from dashboard.api_data_layer import api_call
    logger.info("✓ api_call imported")

    logger.info("3. Importing dashboard.fetchers_common...")
    from dashboard.fetchers_common import format_fetcher_error, get_endpoint_path, record_data_quality_issue
    logger.info("✓ fetchers_common imports done")

    logger.info("4. Importing dashboard.utilities...")
    from dashboard.utilities import CY, G, R, Y
    logger.info("✓ utilities imports done")

    logger.info("5. Importing dashboard.fetcher_validator...")
    from dashboard.fetcher_validator import FetcherValidator
    logger.info("✓ fetcher_validator imported")

    logger.info("SUCCESS: All fetchers_external dependencies imported!")

except Exception as e:
    import traceback
    logger.error(f"Error: {type(e).__name__}: {e}")
    traceback.print_exc()
