"""
Loader helper module to provide common utilities for all data loaders.

This module centralizes path setup for loader scripts so they can import from
utils, algo, and other root packages without doing their own sys.path manipulation.

Usage in loader scripts:
    from loaders.loader_helper import setup_imports
    setup_imports()

    # Now you can import from root packages
    from utils.db.context import DatabaseContext
    from utils import ...
"""

import sys
from pathlib import Path

def setup_imports():
    """Set up sys.path for loader scripts to find utils, algo, and other packages."""
    # Loader files are at /loaders/*.py
    # Project root is at /
    loader_dir = Path(__file__).parent
    project_root = loader_dir.parent

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
