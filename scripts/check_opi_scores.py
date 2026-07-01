#!/usr/bin/env python3
"""Check OPI and sample stocks for factor scores (Quality, Growth, Value, etc).

Shows which factor scores are missing (null/data_unavailable) vs populated.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from utils.db import DatabaseContext

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def get_stock_scores(symbols: list[str]) -> None:
    """Fetch and display factor scores for given symbols."""
    placeholders = ",".join(["%s"] * len(symbols))

    try:
        with DatabaseContext("read", timeout=10) as cur:
            cur.execute(
                f"""
                SELECT symbol,
                       composite_score,
                       momentum_score,
                       quality_score,
                       growth_score,
                       value_score,
                       positioning_score,
                       stability_score,
                       rs_pct,
                       data_unavailable,
                       updated_at
                FROM stock_scores
                WHERE symbol IN ({placeholders})
                ORDER BY symbol
                """,
                symbols,
            )

            rows = cur.fetchall()
            if not rows:
                logger.error(f"  No stock_scores found for {symbols}")
                return

            logger.info("\n" + "="*100)
            logger.info("STOCK FACTOR SCORES")
            logger.info("="*100)
            logger.info(f"{'Symbol':<10} {'Composite':<12} {'Momentum':<12} {'Quality':<12} {'Growth':<12} {'Value':<12} {'Positioning':<12} {'Stability':<12} {'RS%':<8} {'Status':<15} {'Updated':<20}")
            logger.info("-"*100)

            for row in rows:
                symbol, composite, momentum, quality, growth, value, positioning, stability, rs_pct, data_unavail, updated = row

                # Format each score, showing null as "--"
                def fmt_score(val):
                    if val is None:
                        return "--"
                    return f"{val:>6.1f}" if isinstance(val, (int, float)) else str(val)[:6]

                composite_str = fmt_score(composite)
                momentum_str = fmt_score(momentum)
                quality_str = fmt_score(quality)
                growth_str = fmt_score(growth)
                value_str = fmt_score(value)
                positioning_str = fmt_score(positioning)
                stability_str = fmt_score(stability)
                rs_str = fmt_score(rs_pct)

                # Status indicator
                if data_unavail:
                    status = "UNAVAILABLE"
                elif composite is None:
                    status = "NULL"
                else:
                    status = "OK"

                logger.info(
                    f"{symbol:<10} {composite_str:<12} {momentum_str:<12} {quality_str:<12} "
                    f"{growth_str:<12} {value_str:<12} {positioning_str:<12} {stability_str:<12} "
                    f"{rs_str:<8} {status:<15} {updated!s:<20}"
                )

            # Analysis
            logger.info("\n" + "="*100)
            logger.info("ANALYSIS")
            logger.info("="*100)

            null_count = sum(1 for row in rows if row[1] is None)  # composite_score is index 1
            data_unavail_count = sum(1 for row in rows if row[9])  # data_unavailable is index 9
            ok_count = len(rows) - null_count - data_unavail_count

            logger.info(f"✓ Stocks with scores:        {ok_count}")
            logger.info(f"✗ Stocks with NULL scores:   {null_count}")
            logger.info(f"✗ Stocks data unavailable:   {data_unavail_count}")

            if null_count > 0:
                logger.error("\n⚠ Null scores indicate:")
                logger.error("  - stock_scores loader hasn't run yet, OR")
                logger.error("  - upstream metrics incomplete (quality/growth/value/etc haven't populated)")
                logger.error("  - Check: Are growth_metrics and quality_metrics tables populated?")

            if ok_count == len(rows):
                logger.info("\n✓ All sampled stocks have proper factor scores!")

    except Exception as e:
        logger.error(f"✗ Database error: {e}")
        sys.exit(1)


def main():
    # Sample symbols to check
    symbols = [
        "OPI",  # The REIT with issues
        "AAPL",  # Large cap, should have all metrics
        "MSFT",  # Large cap, should have all metrics
        "VTI",   # ETF - may have different behavior
    ]

    logger.info("\nChecking factor scores for sample stocks...")
    get_stock_scores(symbols)


if __name__ == "__main__":
    main()
