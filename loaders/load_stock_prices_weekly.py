#!/usr/bin/env python3
"""Wrapper for weekly stock prices loader - calls loadpricedaily with weekly intervals."""
import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

os.environ['LOADER_INTERVALS'] = os.getenv('LOADER_INTERVALS', '1wk')
os.environ['LOADER_ASSET_CLASSES'] = os.getenv('LOADER_ASSET_CLASSES', 'stock,etf')
os.environ['LOADER_SYMBOLS'] = os.getenv('LOADER_SYMBOLS', '')
os.environ['LOADER_PARALLELISM'] = os.getenv('LOADER_PARALLELISM', '2')

# Import and run the unified loader
try:
    # Ensure we can find the loaders module
    loader_dir = Path(__file__).parent
    repo_dir = loader_dir.parent

    if str(repo_dir) not in sys.path:
        sys.path.insert(0, str(repo_dir))

    # Try importing from loaders package
    from loaders.loadpricedaily import main

    exit_code = main()
    sys.exit(exit_code)
except ImportError as e:
    logger.error(f"Failed to import loadpricedaily: {e}", exc_info=True)
    sys.exit(2)
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    sys.exit(1)
