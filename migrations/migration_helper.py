"""
Migration helper module to provide common utilities for all migrations.

This module centralizes path setup and common imports that all migrations need.
Migration files should import from this module instead of doing their own sys.path manipulation.
"""

import sys
from pathlib import Path


# Set up path so migrations can import from utils and other root packages
_migration_root = Path(__file__).parent.parent
if str(_migration_root) not in sys.path:
    sys.path.insert(0, str(_migration_root))

# Common imports that migrations typically need
from utils.db.context import DatabaseContext


__all__ = ["DatabaseContext"]
