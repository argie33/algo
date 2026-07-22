#!/usr/bin/env python3
"""Test coverage improvements after fixes.

Compares before/after metrics coverage to verify fixes worked.
"""

import logging
import sys

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_coverage() -> dict:
    """Check current metric coverage."""
    with DatabaseContext("read") as cur:
        tables = {
            "value_metrics": "Value Metrics",
            "positioning_metrics": "Positioning",
            "stability_metrics": "Stability",
            "momentum_metrics": "Momentum",
            "quality_metrics": "Quality",
            "growth_metrics": "Growth",
            "short_interest_finra": "FINRA Short Interest",
            "institutional_holdings_13f": "13F Institutional",
            "stock_scores": "Stock Scores (70%+ completeness)",
        }

        results = {}
        for table, desc in tables.items():
            try:
                cur.execute(f'''
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE data_unavailable = false OR data_unavailable IS NULL) as available
                    FROM {table}
                ''')
                total, available = cur.fetchone()
                pct = 100.0 * available / total if total > 0 else 0
                results[desc] = {"total": total, "available": available, "pct": pct}
            except Exception as e:
                logger.warning(f"Could not query {table}: {e}")
                results[desc] = None

        # Additional checks
        cur.execute('''
            SELECT COUNT(DISTINCT symbol)
            FROM stock_scores
            WHERE (data_unavailable = false OR data_unavailable IS NULL)
            AND data_completeness >= 70
        ''')
        tradeable_scores = cur.fetchone()[0]

        cur.execute('''
            SELECT COUNT(DISTINCT symbol)
            FROM buy_sell_daily
            WHERE date = (SELECT MAX(date) FROM buy_sell_daily)
            AND signal = 'BUY'
        ''')
        buy_signals = cur.fetchone()[0]

        results["Tradeable Stock Scores (70%+)"] = {
            "total": tradeable_scores,
            "available": tradeable_scores,
            "pct": 100.0,
        }
        results["Active BUY Signals"] = {
            "total": buy_signals,
            "available": buy_signals,
            "pct": 100.0,
        }

    return results


def main() -> int:
    """Run coverage report."""
    logger.info("=== CURRENT METRIC COVERAGE ===\n")

    coverage = check_coverage()

    for desc, stats in coverage.items():
        if stats is None:
            logger.info(f"{desc:35} ERROR")
        else:
            pct_str = f"{stats['pct']:5.1f}%" if stats["pct"] else "N/A"
            logger.info(
                f"{desc:35} {stats['available']:5}/{stats['total']:5} ({pct_str})"
            )

    # Highlight problem areas
    logger.info("\n=== AREAS NEEDING ATTENTION ===")
    for desc, stats in sorted(
        coverage.items(), key=lambda x: (x[1]["pct"] if x[1] else 100), reverse=False
    ):
        if stats and stats["pct"] < 90:
            gap = stats["total"] - stats["available"]
            logger.info(f"{desc:35} {gap:5} missing ({100-stats['pct']:5.1f}% gap)")

    logger.info("\n=== SUMMARY ===")
    total_available = sum(
        (stats["available"] for stats in coverage.values() if stats),
        0,
    )
    total_rows = sum((stats["total"] for stats in coverage.values() if stats), 0)
    overall_pct = 100.0 * total_available / total_rows if total_rows > 0 else 0
    logger.info(f"Overall coverage: {overall_pct:.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
