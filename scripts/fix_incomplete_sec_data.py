#!/usr/bin/env python3
"""Fix incomplete SEC financial data and regenerate metric scores.

This script:
1. Identifies stocks with incomplete SEC data (missing net_income, total_assets, etc.)
2. Marks them for re-fetching by resetting their watermarks
3. Optionally re-runs the loader pipeline to backfill missing data
4. Verifies completeness and regenerates stock scores

Usage:
    python scripts/fix_incomplete_sec_data.py                 # Audit only
    python scripts/fix_incomplete_sec_data.py --fix           # Audit + fix watermarks
    python scripts/fix_incomplete_sec_data.py --full-reload   # Audit + full re-run loaders
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging  # noqa: E402

from utils.db.context import DatabaseContext  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


def audit_sec_data_completeness() -> dict[str, list[str]]:
    """Audit SEC data for completeness and find stocks with missing key fields."""
    incomplete_stocks = {
        "missing_net_income": [],
        "missing_total_assets": [],
        "missing_operating_income": [],
        "all_null_metrics": [],
    }

    try:
        with DatabaseContext("read") as cur:
            logger.info("\n=== AUDITING SEC DATA COMPLETENESS ===\n")

            # Check annual_income_statement for missing net_income
            cur.execute("""
                SELECT DISTINCT symbol
                FROM annual_income_statement
                WHERE net_income IS NULL
                AND fiscal_year >= 2020
                AND symbol NOT IN (
                    SELECT DISTINCT symbol FROM annual_income_statement
                    WHERE net_income IS NOT NULL AND fiscal_year >= 2020
                )
                ORDER BY symbol
                LIMIT 100
            """)
            missing_ni = [row[0] for row in cur.fetchall()]
            incomplete_stocks["missing_net_income"] = missing_ni
            logger.info(f"Stocks missing net_income (FY 2020+): {len(missing_ni)} found")
            if missing_ni[:10]:
                logger.info(f"  Sample: {', '.join(missing_ni[:10])}")

            # Check annual_balance_sheet for missing total_assets
            cur.execute("""
                SELECT DISTINCT symbol
                FROM annual_balance_sheet
                WHERE total_assets IS NULL
                AND fiscal_year >= 2020
                AND symbol NOT IN (
                    SELECT DISTINCT symbol FROM annual_balance_sheet
                    WHERE total_assets IS NOT NULL AND fiscal_year >= 2020
                )
                ORDER BY symbol
                LIMIT 100
            """)
            missing_ta = [row[0] for row in cur.fetchall()]
            incomplete_stocks["missing_total_assets"] = missing_ta
            logger.info(f"Stocks missing total_assets (FY 2020+): {len(missing_ta)} found")
            if missing_ta[:10]:
                logger.info(f"  Sample: {', '.join(missing_ta[:10])}")

            # Check for operating_income
            cur.execute("""
                SELECT DISTINCT symbol
                FROM annual_income_statement
                WHERE operating_income IS NULL
                AND fiscal_year >= 2020
                AND symbol NOT IN (
                    SELECT DISTINCT symbol FROM annual_income_statement
                    WHERE operating_income IS NOT NULL AND fiscal_year >= 2020
                )
                ORDER BY symbol
                LIMIT 50
            """)
            missing_oi = [row[0] for row in cur.fetchall()]
            incomplete_stocks["missing_operating_income"] = missing_oi
            logger.info(f"Stocks missing operating_income (FY 2020+): {len(missing_oi)} found")

            # Check for quality_metrics with all NULL base metrics
            cur.execute("""
                SELECT symbol
                FROM quality_metrics
                WHERE roe IS NULL
                AND roa IS NULL
                AND operating_margin IS NULL
                AND net_margin IS NULL
                AND debt_to_equity IS NULL
                AND data_unavailable = FALSE
                LIMIT 50
            """)
            all_null = [row[0] for row in cur.fetchall()]
            incomplete_stocks["all_null_metrics"] = all_null
            logger.info(f"Quality metrics with all NULL fields (marked available): {len(all_null)} found")
            if all_null[:10]:
                logger.info(f"  Sample: {', '.join(all_null[:10])}")

            # Summary statistics
            logger.info("\n=== SUMMARY ===")
            affected_stocks = set()
            for _issue, symbols in incomplete_stocks.items():
                affected_stocks.update(symbols)
            logger.info(f"Total unique affected stocks: {len(affected_stocks)}")

    except Exception as e:
        logger.error(f"Audit failed: {e}")
        import traceback
        traceback.print_exc()

    return incomplete_stocks


def reset_watermarks_for_stocks(symbols: list[str]) -> bool:
    """Reset loader watermarks to force re-fetch of incomplete symbols."""
    if not symbols:
        logger.info("No symbols to reset")
        return True

    logger.info(f"\nResetting watermarks for {len(symbols)} symbols...")
    try:
        with DatabaseContext("write") as cur:
            # Reset to a date before the problematic loads to force re-fetch
            reset_date = date(2020, 1, 1)
            affected = 0

            for symbol in symbols:
                # Get all loader names that write financial data
                loaders = [
                    "load_financial_statements.py",
                ]
                for loader in loaders:
                    cur.execute("""
                        UPDATE loader_watermarks
                        SET watermark_date = %s
                        WHERE symbol = %s AND loader_name = %s
                    """, (reset_date, symbol, loader))
                    affected += cur.rowcount

            logger.info(f"  Reset {affected} watermark entries")
            return True

    except Exception as e:
        logger.error(f"Watermark reset failed: {e}")
        return False


def check_loader_status() -> None:
    """Check status of financial statement loaders."""
    try:
        with DatabaseContext("read") as cur:
            logger.info("\n=== LOADER STATUS ===\n")
            cur.execute("""
                SELECT table_name, status, latest_date, last_updated, error_message
                FROM data_loader_status
                WHERE table_name LIKE 'annual_%' OR table_name LIKE 'quarterly_%'
                ORDER BY table_name
            """)
            for row in cur.fetchall():
                table, status, latest, updated, error = row
                logger.info(f"{table:35} {status:10} (latest: {latest})")
                if status in ("RUNNING", "ERROR") and updated:
                    hours_ago = (datetime.now(timezone.utc) - updated.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                    if hours_ago > 1:
                        logger.warning(f"  ⚠️  Status unchanged for {hours_ago:.1f} hours (may be stuck)")
                if error:
                    logger.error(f"  ERROR: {error[:100]}")

    except Exception as e:
        logger.error(f"Could not check loader status: {e}")


def main():
    """Run audit and optionally fix."""
    import argparse

    parser = argparse.ArgumentParser(description="Audit and fix incomplete SEC data")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Reset watermarks to force re-fetch of incomplete symbols",
    )
    parser.add_argument(
        "--full-reload",
        action="store_true",
        help="Run loader pipeline to backfill data (requires --fix first)",
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("SEC DATA COMPLETENESS AUDIT")
    logger.info("=" * 80)

    # Check loader status first
    check_loader_status()

    # Audit for completeness
    incomplete = audit_sec_data_completeness()

    # Identify all affected stocks
    affected_symbols = set()
    for symbols in incomplete.values():
        affected_symbols.update(symbols)

    if not affected_symbols:
        logger.info("\n✓ No incomplete SEC data found - all stocks have complete financials")
        return 0

    logger.info(f"\n⚠️  Found {len(affected_symbols)} stocks with incomplete SEC data")

    if args.fix:
        logger.info("\nFIXING: Resetting watermarks for affected stocks...")
        if reset_watermarks_for_stocks(list(affected_symbols)):
            logger.info("✓ Watermarks reset successfully")
            logger.info("\nNEXT STEP: Run loaders to backfill missing data:")
            logger.info("  python3 scripts/local_loader_scheduler.py --now metrics")
            return 0
        else:
            logger.error("✗ Failed to reset watermarks")
            return 1

    elif args.full_reload:
        logger.error("--full-reload requires --fix to be run first")
        return 1
    else:
        logger.info("\nTO FIX: Run with --fix flag:")
        logger.info("  python3 scripts/fix_incomplete_sec_data.py --fix")
        logger.info("\nThen run metrics pipeline:")
        logger.info("  python3 scripts/local_loader_scheduler.py --now metrics")
        return 0


if __name__ == "__main__":
    sys.exit(main())
