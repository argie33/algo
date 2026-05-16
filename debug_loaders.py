#!/usr/bin/env python3
"""Debug loader execution with detailed logging."""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path('.env.local'))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Test critical loaders
loaders_to_test = [
    ('loadstocksymbols', 'Stock Symbols'),
    ('loadcompanyprofile', 'Company Profile'),
    ('load_income_statement', 'Income Statement'),
    ('load_balance_sheet', 'Balance Sheet'),
    ('load_cash_flow', 'Cash Flow'),
    ('loadsectors', 'Sectors'),
    ('loadtechnicalsdaily', 'Technical Daily'),
    ('loadearningshistory', 'Earnings History'),
]

print("="*70)
print("LOADER DEBUG TEST")
print("="*70)

for module_name, display_name in loaders_to_test:
    print(f"\n{display_name}:")
    try:
        mod = __import__(module_name)
        print(f"  ✓ Import successful")
        
        # Check for main function or class
        if hasattr(mod, 'main'):
            print(f"  ✓ Has main() function")
        if hasattr(mod, 'Loader') or any('Loader' in name for name in dir(mod)):
            loader_class = [name for name in dir(mod) if 'Loader' in name][0]
            print(f"  ✓ Has {loader_class} class")
            
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
    except Exception as e:
        print(f"  ✗ Error: {type(e).__name__}: {e}")

print("\n" + "="*70)
print("Check which loaders are actually missing:")
print("="*70)

import subprocess
result = subprocess.run(['ls', '-1', 'load*.py'], capture_output=True, text=True)
print("Loader files found:")
for line in result.stdout.strip().split('\n'):
    if line:
        print(f"  {line}")

