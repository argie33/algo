#!/usr/bin/env python3
"""Trace utilities.py line by line."""

import os
import sys
import logging

os.environ["LOCAL_MODE"] = "true"
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.getcwd())

# Manually run each step of utilities.py imports
try:
    logger.info("Step 1: Importing standard library modules...")
    import hashlib
    import json
    import logging as logging_module
    import logging.handlers
    import os as os_module
    import threading
    from collections import OrderedDict
    from datetime import datetime, timedelta
    from typing import Any
    from zoneinfo import ZoneInfo
    logger.info("✓ Standard library imports done")

    logger.info("Step 2: Importing rich.console...")
    from rich.console import Console
    logger.info("✓ rich.console imported")

    logger.info("Step 3: Creating Console object...")
    test_console = Console(force_terminal=True, legacy_windows=False, highlight=False)
    logger.info("✓ Console object created")

    logger.info("Step 4: Importing dashboard.error_boundary...")
    from dashboard.error_boundary import has_error
    logger.info("✓ error_boundary imported")

    logger.info("Step 5: Importing utils.validation.framework...")
    from utils.validation.framework import safe_float
    logger.info("✓ safe_float imported")

    logger.info("SUCCESS!")

except Exception as e:
    import traceback
    logger.error(f"Error: {type(e).__name__}: {e}")
    traceback.print_exc()
