#!/usr/bin/env python3
"""Diagnose missing factor scores issue."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def main():
    """Check loader status and stock scores coverage."""
    with DatabaseContext("read") as cur:
        # Check loader status for metric tables
        print("\n=== LOADER STATUS ===")
        cur.execute("""
            SELECT
                table_name,
                status,
                completion_pct,
                symbols_loaded,
                symbol_count
            FROM data_loader_status
            WHERE table_name IN (
                'value_metrics', 'stability_metrics', 'quality_metrics',
                'growth_metrics', 'positioning_metrics', 'stock_scores'
            )
            ORDER BY table_name
        """)
        for row in cur.fetchall():
            table_name, status, completion_pct, symbols_loaded, symbol_count = row
            print(f"{table_name:25} | {status:10} | {completion_pct:6.1f}% | {symbols_loaded:5}/{symbol_count:5}")

        # Check stock_scores coverage
        print("\n=== STOCK_SCORES COVERAGE ===")
        cur.execute("""
            SELECT
                COUNT(*) as total_stocks,
                COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as with_score,
                COUNT(CASE WHEN data_completeness < 50 THEN 1 END) as low_completeness,
                COUNT(CASE WHEN data_completeness >= 50 THEN 1 END) as high_completeness
            FROM stock_scores
        """)
        total, with_score, low, high = cur.fetchone()
        print(f"Total stocks: {total}")
        print(f"With scores: {with_score} ({100*with_score/max(1,total):.1f}%)")
        print(f"Low completeness (<50%): {low}")
        print(f"High completeness (>=50%): {high}")

        # Check BREZ specifically
        print("\n=== CHECKING BREZ ===")
        cur.execute("""
            SELECT
                symbol, composite_score, quality_score, growth_score, value_score,
                momentum_score, positioning_score, stability_score, data_completeness
            FROM stock_scores
            WHERE symbol = 'BREZ'
        """)
        row = cur.fetchone()
        if row:
            symbol, comp, qual, grwth, val, mom, pos, stab, complete = row
            print(f"Symbol: {symbol}")
            print(f"  Composite: {comp}")
            print(f"  Quality: {qual}")
            print(f"  Growth: {grwth}")
            print(f"  Value: {val}")
            print(f"  Momentum: {mom}")
            print(f"  Positioning: {pos}")
            print(f"  Stability: {stab}")
            print(f"  Completeness: {complete}%")
        else:
            print("BREZ not found")

        # Check stocks with low completeness
        print("\n=== STOCKS WITH LOW COMPLETENESS (<50%) ===")
        cur.execute("""
            SELECT symbol, composite_score, quality_score, growth_score, value_score,
                   momentum_score, positioning_score, stability_score, data_completeness
            FROM stock_scores
            WHERE data_completeness < 50
            ORDER BY data_completeness ASC
            LIMIT 10
        """)
        for row in cur.fetchall():
            symbol, comp, qual, grwth, val, mom, pos, stab, complete = row
            null_count = sum(1 for v in [qual, grwth, val, mom, pos, stab] if v is None)
            print(f"{symbol:8} complete={complete:5.1f}% nulls={null_count}/6 comp={comp}")


if __name__ == "__main__":
    main()
