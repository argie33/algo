#!/usr/bin/env python3
"""Wrapper for weekly stock prices loader - calls loadpricedaily with weekly intervals."""
import os
import sys
from pathlib import Path

os.environ['LOADER_INTERVALS'] = os.getenv('LOADER_INTERVALS', '1wk')
os.environ['LOADER_ASSET_CLASSES'] = os.getenv('LOADER_ASSET_CLASSES', 'stock,etf')
os.environ['LOADER_SYMBOLS'] = os.getenv('LOADER_SYMBOLS', '')
os.environ['LOADER_PARALLELISM'] = os.getenv('LOADER_PARALLELISM', '2')

# Import and run the unified loader
sys.path.insert(0, str(Path(__file__).parent.parent))
from loaders.loadpricedaily import main

sys.exit(main())
