#!/usr/bin/env python3
"""
Loader Validation - Verify all critical loaders populate fresh data

Checks:
1. Each critical table has data for today (or latest trading date)
2. Row counts are reasonable (>0 for all tables)
3. No unexpected NULLs in critical columns
4. Data is fresh (< 1 hour old for price data)
5. All required loaders completed successfully
"""

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from config.credential_helper import get_db_config
from config.env_loader import load_env
import os
import sys
from config.credential_helper import get_db_password, get_db_config
import logging
from utils.db_connection import get_db_connection
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

def main():
    validator = LoaderValidator()
    success = validator.validate_all()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())

