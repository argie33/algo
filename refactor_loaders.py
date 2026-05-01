#!/usr/bin/env python3
"""
Smart Loader Refactoring Script
Converts all loaders to use DatabaseHelper pattern
"""
import os
import re
from pathlib import Path

LOADERS_DIR = Path(".")

# Get all loaders not yet refactored
refactored = {
    "loadpricedaily.py", "loadpriceweekly.py", "loadpricemonthly.py",
    "loadbuyselldaily.py", "loadbuysellweekly.py", "loadbuysellmonthly.py",
    "loadbuysell_etf_daily.py", "loadannualbalancesheet.py"
}

all_loaders = [f.name for f in LOADERS_DIR.glob("load*.py")]
remaining = [l for l in all_loaders if l not in refactored]

print(f"Total loaders: {len(all_loaders)}")
print(f"Already refactored: {len(refactored)}")
print(f"Remaining to refactor: {len(remaining)}")
print("\nLoaders to refactor:")
for loader in sorted(remaining)[:20]:
    print(f"  - {loader}")

# Categorize by type
financial = [l for l in remaining if "balance" in l or "cashflow" in l or "income" in l]
etf = [l for l in remaining if "etf" in l.lower()]
earnings = [l for l in remaining if "earning" in l.lower()]
daily = [l for l in remaining if "daily" in l.lower() or "dayly" in l.lower()]

print(f"\nBy Category:")
print(f"  Financial: {len(financial)}")
print(f"  ETF: {len(etf)}")
print(f"  Earnings: {len(earnings)}")
print(f"  Daily: {len(daily)}")
print(f"  Other: {len(remaining) - len(financial) - len(etf) - len(earnings) - len(daily)}")
