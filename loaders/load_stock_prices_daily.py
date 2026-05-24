#!/usr/bin/env python3
"""Stock prices loader - handles daily, weekly, and monthly via environment variables.

This script is called by ECS task definitions. It wraps the unified loadpricedaily.py
and sets sensible defaults based on the task name/purpose.
"""
import os
import sys
from pathlib import Path

# Set defaults if not already in environment
# These can be overridden by ECS task definition environment variables
if 'LOADER_INTERVALS' not in os.environ:
    os.environ['LOADER_INTERVALS'] = '1d,1wk,1mo'
if 'LOADER_ASSET_CLASSES' not in os.environ:
    os.environ['LOADER_ASSET_CLASSES'] = 'stock,etf'
if 'LOADER_SYMBOLS' not in os.environ:
    os.environ['LOADER_SYMBOLS'] = ''
if 'LOADER_PARALLELISM' not in os.environ:
    os.environ['LOADER_PARALLELISM'] = '2'

# Import and run the unified loader
sys.path.insert(0, str(Path(__file__).parent.parent))
from loaders.loadpricedaily import main

sys.exit(main())
