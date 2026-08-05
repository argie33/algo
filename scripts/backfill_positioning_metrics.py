#!/usr/bin/env python3
"""Backfill positioning metrics for symbols that now have shares_outstanding.

PURPOSE:
- Re-run positioning metrics loaders for symbols marked data_unavailable
- Uses existing company_info_sec shares_outstanding data
- Recovers short_interest and insider_ownership calculations
- Improves positioning coverage from 82.5% to ~90%+

Run:
    python3 scripts/backfill_positioning_metrics.py [--batch-size 100]
"""

import logging
import sys
from datetime import date, datetime
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from loaders.load_positioning_metrics import PositioningMetricsLoader
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')


def get_symbols_to_backfill() -> list[str]:
    """Identify symbols that were marked data_unavailable but now have shares_outstanding."""
    with DatabaseContext("read") as cur:
        # Find symbols with data_unavailable=TRUE in positioning_metrics
        # but now have shares_outstanding in company_info_sec
        cur.execute("""
            SELECT DISTINCT pm.symbol
            FROM positioning_metrics pm
            JOIN company_info_sec cs ON cs.symbol = pm.symbol
            WHERE pm.data_unavailable = TRUE
            AND cs.shares_outstanding IS NOT NULL
            AND cs.shares_outstanding > 1000
            ORDER BY pm.symbol
        """)
        return [row[0] for row in cur.fetchall()]


def backfill_positioning(batch_size: int = 100) -> dict[str, int]:
    """Re-run positioning loader for symbols that now have required data."""
    symbols_to_backfill = get_symbols_to_backfill()
    logger.info(f"Found {len(symbols_to_backfill)} symbols to backfill")

    if not symbols_to_backfill:
        logger.info("No symbols need backfilling")
        return {"backfilled": 0, "unchanged": 0}

    loader = PositioningMetricsLoader()
    backfilled = 0
    unchanged = 0

    # Process in batches
    for i in range(0, len(symbols_to_backfill), batch_size):
        batch = symbols_to_backfill[i : i + batch_size]
        logger.info(f"Processing batch {i // batch_size + 1}: {len(batch)} symbols")

        try:
            # Prepare loader (load caches)
            if i == 0:
                loader._prepare_batch_context()

            # Re-fetch positioning data for each symbol
            for symbol in batch:
                try:
                    result = loader.fetch_incremental(symbol, since=None)
                    if result:
                        record = result[0]
                        # Insert/update
                        with DatabaseContext("write") as cur:
                            cur.execute(
                                """
                                INSERT INTO positioning_metrics
                                (symbol, institutional_ownership_pct, insider_ownership_pct,
                                 short_interest_pct, data_unavailable, reason, updated_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (symbol) DO UPDATE SET
                                    institutional_ownership_pct = EXCLUDED.institutional_ownership_pct,
                                    insider_ownership_pct = EXCLUDED.insider_ownership_pct,
                                    short_interest_pct = EXCLUDED.short_interest_pct,
                                    data_unavailable = EXCLUDED.data_unavailable,
                                    reason = EXCLUDED.reason,
                                    updated_at = EXCLUDED.updated_at
                                """,
                                (
                                    symbol,
                                    record.get("institutional_ownership_pct"),
                                    record.get("insider_ownership_pct"),
                                    record.get("short_interest_pct"),
                                    record.get("data_unavailable"),
                                    record.get("reason"),
                                    datetime.now(EASTERN_TZ),
                                ),
                            )

                        if not record.get("data_unavailable"):
                            backfilled += 1
                        else:
                            unchanged += 1
                except Exception as e:
                    logger.warning(f"  {symbol}: backfill failed - {e}")
                    unchanged += 1

        except Exception as e:
            logger.error(f"Batch {i // batch_size + 1} failed: {e}")
            raise

    logger.info(f"Backfill complete: {backfilled} recovered, {unchanged} still unavailable")
    return {"backfilled": backfilled, "unchanged": unchanged}


def report_improvements() -> None:
    """Report positioning metrics improvement after backfill."""
    with DatabaseContext("read") as cur:
        # Overall positioning metrics coverage
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE data_unavailable = false OR data_unavailable IS NULL) as available,
                COUNT(*) as total
            FROM positioning_metrics
        """)
        available, total = cur.fetchone()
        new_coverage = (available / total * 100) if total > 0 else 0

        # Individual field coverage
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE institutional_ownership_pct IS NOT NULL) as inst,
                COUNT(*) FILTER (WHERE insider_ownership_pct IS NOT NULL) as insider,
                COUNT(*) FILTER (WHERE short_interest_pct IS NOT NULL) as short,
                COUNT(*) as total
            FROM positioning_metrics
        """)
        inst, insider, short, total = cur.fetchone()

        print("\n" + "=" * 70)
        print("POSITIONING METRICS - AFTER BACKFILL")
        print("=" * 70)
        print(f"\nOVERALL COVERAGE: {available:,} / {total:,} ({new_coverage:.1f}%)")
        print(f"\nCOMPONENT COVERAGE:")
        print(f"  Institutional Ownership: {inst:,} / {total:,} ({inst / total * 100:.1f}%)")
        print(f"  Insider Ownership: {insider:,} / {total:,} ({insider / total * 100:.1f}%)")
        print(f"  Short Interest: {short:,} / {total:,} ({short / total * 100:.1f}%)")

        # Stock scores impact
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE data_unavailable = false OR data_unavailable IS NULL) as available,
                COUNT(*) as total
            FROM stock_scores
        """)
        scores_available, scores_total = cur.fetchone()
        new_score_coverage = (scores_available / scores_total * 100) if scores_total > 0 else 0
        print(f"\nSTOCK SCORES IMPACT:")
        print(f"  Available scores: {scores_available:,} / {scores_total:,} ({new_score_coverage:.1f}%)")


def main() -> int:
    """Entry point."""
    try:
        logger.info("Starting positioning metrics backfill...")
        result = backfill_positioning(batch_size=100)

        # Recompute stock scores to reflect new positioning data
        logger.info("Recomputing stock scores...")
        from loaders.load_stock_scores import StockScoresLoader

        stock_loader = StockScoresLoader()
        # Get all active symbols
        with DatabaseContext("read") as cur:
            cur.execute("SELECT symbol FROM stock_symbols WHERE active = TRUE ORDER BY symbol")
            symbols = [row[0] for row in cur.fetchall()]

        logger.info(f"Re-scoring {len(symbols)} symbols...")
        stock_loader.run(symbols, parallelism=8, backfill_days=0)

        # Report improvements
        report_improvements()

        logger.info("Backfill complete!")
        return 0

    except Exception as e:
        logger.error(f"Backfill failed: {type(e).__name__}: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
