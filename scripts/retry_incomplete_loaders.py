#!/usr/bin/env python3
"""Retry incomplete loaders with optimized parallelism to achieve >=95% completion."""

import logging
import sys


# Suppress debug logging
logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

print("=" * 100)
print("LOADER RECOVERY ATTEMPT - ACTUAL AWS RETRY WITH OPTIMIZED SETTINGS")
print("=" * 100)

from utils.db.context import DatabaseContext


print("\n[PHASE 1] Checking incomplete loaders in AWS database...\n")

with DatabaseContext("read") as cur:
    cur.execute(
        """
        SELECT table_name, completion_pct, symbols_loaded, symbol_count
        FROM data_loader_status
        WHERE completion_pct < 95.0
            AND last_updated >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
        ORDER BY completion_pct DESC
    """
    )

    incomplete = cur.fetchall()

    if not incomplete:
        print("No incomplete loaders found. All data loaded!")
        sys.exit(0)

    print("BEFORE RETRY:")
    for table_name, completion_pct, symbols_loaded, symbol_count in incomplete:
        completion_pct = completion_pct or 0
        print(f"  {table_name:30s} {completion_pct:5.1f}% ({symbols_loaded}/{symbol_count})")

print("\n[RETRY] Attempting to recover loaders with reduced parallelism...\n")

# Retry the easiest one first (growth_metrics at 74.3%)
# Start with growth_metrics since it's closest to 95%
loaders_to_retry = [
    ("growth_metrics", 4),  # Reduce from 8 to 4
    ("value_metrics", 2),   # Very aggressive reduction for rate-limited API
    ("positioning_metrics", 2),  # Very aggressive reduction for rate-limited API
]

successful_recoveries = []

for loader_name, parallelism in loaders_to_retry:
    print(f"Retrying {loader_name} with parallelism={parallelism}...")

    try:
        # Dynamically import and run the loader
        import importlib

        module_name = {
            "growth_metrics": "loaders.load_growth_metrics",
            "value_metrics": "loaders.load_value_metrics",
            "positioning_metrics": "loaders.load_positioning_metrics",
        }.get(loader_name)

        if not module_name:
            print(f"  ERROR: Unknown loader {loader_name}")
            continue

        module = importlib.import_module(module_name)

        # Find the loader class
        loader_class_name = (
            "GrowthMetricsLoader"
            if loader_name == "growth_metrics"
            else "ValueMetricsLoader"
            if loader_name == "value_metrics"
            else "PositioningMetricsLoader"
        )

        if not hasattr(module, loader_class_name):
            print(f"  ERROR: Could not find {loader_class_name}")
            continue

        loader_class = getattr(module, loader_class_name)
        loader = loader_class()

        # Get active symbols
        from utils.loaders.helpers import get_active_symbols

        symbols = get_active_symbols()

        # Run with reduced parallelism
        print(f"  Loading {len(symbols)} symbols...")
        result = loader.run(symbols, parallelism=parallelism)

        print(
            f"  Loaded {result.get('rows_inserted', 0)} rows, "
            f"processed {result.get('symbols_processed', 0)} symbols"
        )

        # Check if recovered
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT completion_pct FROM data_loader_status WHERE table_name = %s",
                (loader_name,),
            )
            row = cur.fetchone()
            if row:
                new_completion_pct = row[0] or 0

                if new_completion_pct >= 95.0:
                    print(
                        f"  SUCCESS: Recovered to {new_completion_pct:.1f}% [OK]"
                    )
                    successful_recoveries.append(
                        (loader_name, new_completion_pct)
                    )
                else:
                    print(
                        f"  INCOMPLETE: Only reached {new_completion_pct:.1f}% "
                        "(still below 95%)"
                    )

    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback

        traceback.print_exc()

print("\n" + "=" * 100)
print("RESULTS:\n")

if successful_recoveries:
    print("RECOVERED LOADERS:")
    for loader_name, completion_pct in successful_recoveries:
        print(f"  [OK] {loader_name:30s} {completion_pct:5.1f}%")

    print(f"\nSuccessfully recovered {len(successful_recoveries)} loaders to >=95%")
else:
    print("No loaders recovered to >=95% yet")
    print("Remaining issues may require:")
    print("  - Further parallelism reduction")
    print("  - Longer API throttling wait time")
    print("  - Data source adjustments")

# Final check: show all loaders
print("\nFINAL STATUS (all loaders):\n")

with DatabaseContext("read") as cur:
    cur.execute(
        """
        SELECT table_name, completion_pct, symbols_loaded, symbol_count
        FROM data_loader_status
        WHERE last_updated >= CURRENT_TIMESTAMP - INTERVAL '2 hours'
        ORDER BY completion_pct DESC
    """
    )

    all_loaders = cur.fetchall()

    passing = 0
    failing = 0

    for table_name, completion_pct, _symbols_loaded, _symbol_count in all_loaders:
        completion_pct = completion_pct or 0
        status = "[PASS]" if completion_pct >= 95 else "[FAIL]"

        if completion_pct >= 95:
            passing += 1
        else:
            failing += 1

        print(f"  {status} {table_name:30s} {completion_pct:5.1f}%")

    print(f"\nTOTAL: {passing} passing, {failing} failing")

    if failing == 0:
        print("\nALL LOADERS AT >=95% COMPLETENESS - GOAL REACHED!")
    else:
        print(f"\n{failing} loaders still below 95% threshold")

print("=" * 100 + "\n")
