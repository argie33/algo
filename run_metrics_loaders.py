#!/usr/bin/env python3
"""
Run growth and quality metrics loaders for all symbols with financial data.
"""
import subprocess
import sys
import os

# Ensure PYTHONPATH includes root
os.environ['PYTHONPATH'] = os.getcwd()

loaders = [
    'loaders/load_growth_metrics.py',
    'loaders/load_quality_metrics.py',
]

print("Running metrics loaders...")
for loader in loaders:
    print(f"\n{'='*60}")
    print(f"Running: {loader}")
    print(f"{'='*60}\n")

    result = subprocess.run(
        ['python3', loader],
        env=os.environ.copy()
    )

    if result.returncode != 0:
        print(f"\nError running {loader}")
    else:
        print(f"\nCompleted: {loader}")

print("\nAll metrics loaders finished!")
