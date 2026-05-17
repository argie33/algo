#!/usr/bin/env python3
"""
Database Schema Validation - Verify schema matches code expectations

Checks:
1. All expected tables exist
2. All expected columns exist with correct types
3. Primary keys and constraints are defined
4. Indexes for performance-critical paths exist
5. Foreign key relationships are intact
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
from pathlib import Path

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

def main():
    validator = SchemaValidator()
    success = validator.validate_all()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())

