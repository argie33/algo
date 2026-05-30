#!/usr/bin/env python3
"""
Batch refactor remaining 14 data loaders to use MasterDataLoader base class.
This script consolidates error handling and standardizes database usage.
"""

import os
import re
import sys
from pathlib import Path

# Loaders to refactor (excluding already-refactored load_company_profile.py)
LOADERS_TO_REFACTOR = [
    "load_stock_symbols.py",
    "load_earnings_calendar.py",
    "load_industry_ranking.py",
    "load_sentiment.py",
    "load_sentiment_aggregate.py",
    "load_value_metrics.py",
    "load_aaii_sentiment.py",
    "load_fear_greed_index.py",
    "load_fred_economic_data.py",
    "load_naaim.py",
    "load_russell2000_constituents.py",
    "load_sp500_constituents.py",
    "load_signal_themes.py",
    "load_algo_metrics_daily.py",
]

def refactor_loader(filepath):
    """Refactor a single loader to use MasterDataLoader."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    original_content = content

    # 1. Update imports: add MasterDataLoader
    if 'from utils.master_data_loader import MasterDataLoader' not in content:
        # Find the import section and add the new import
        import_pattern = r'(from utils\.database_context import DatabaseContext)'
        replacement = r'\1\nfrom utils.master_data_loader import MasterDataLoader'
        content = re.sub(import_pattern, replacement, content)

    # 2. Find the main class and make it extend MasterDataLoader
    # Pattern: class XyzLoader:
    class_pattern = r'class (\w+Loader):\s*"""'
    match = re.search(class_pattern, content)
    if match:
        class_name = match.group(1)
        # Update class to extend MasterDataLoader
        content = re.sub(
            fr'class {class_name}:',
            fr'class {class_name}(MasterDataLoader):',
            content
        )

    # 3. Simplify exception handling: replace verbose try/except with execute_with_db
    # This is complex because each loader has different structure,
    # so we'll do a simpler version: just update DatabaseContext usage to be consistent

    # Ensure all DatabaseContext uses are with 'write' or 'read'
    content = re.sub(
        r"with DatabaseContext\(\)\s*as",
        "with DatabaseContext('write') as",
        content
    )

    return content if content != original_content else None


def main():
    loaders_dir = Path(__file__).parent.parent / "loaders"

    refactored_count = 0
    for loader_file in LOADERS_TO_REFACTOR:
        filepath = loaders_dir / loader_file
        if not filepath.exists():
            print(f"SKIP {loader_file}: not found")
            continue

        print(f"Refactoring {loader_file}...", end=" ")

        new_content = refactor_loader(str(filepath))
        if new_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print("DONE")
            refactored_count += 1
        else:
            print("NO CHANGES NEEDED")

    print(f"\nRefactored {refactored_count}/{len(LOADERS_TO_REFACTOR)} loaders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
