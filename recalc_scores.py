#!/usr/bin/env python3
"""Recalculate stock_scores from scratch with fresh positioning data."""

import os

os.environ['LOCAL_MODE'] = 'true'

from utils.db import DatabaseContext

# Truncate old data
print("Truncating stock_scores table...")
with DatabaseContext("write") as cur:
    cur.execute("TRUNCATE stock_scores")
print("Done. Running fresh calculation...")

# Run the loader
import sys

from loaders.load_stock_scores import StockScoresLoader
from loaders.runner import run_loader

exit_code = run_loader(StockScoresLoader)
sys.exit(exit_code)
