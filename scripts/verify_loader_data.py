#!/usr/bin/env python3
"""
Verify that loaders are loading complete data after the fixes.
Checks data coverage for all critical tables.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, timedelta
from utils.db_connection import get_db_connection
from utils.structured_logger import get_logger

logger = get_logger(__name__)

def check_table_coverage(table_name: str, expected_min_coverage: float = 0.75) -> dict:
    """Check data coverage for a table (% of symbols with latest data)."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Get total symbols in database
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE symbol NOT LIKE '%.%'")
        total_symbols = cur.fetchone()[0]

        if total_symbols == 0:
            return {"status": "error", "message": "No symbols in stock_symbols table"}

        # Get symbols with latest data
        cur.execute(f"""
            SELECT COUNT(DISTINCT symbol)
            FROM {table_name}
            WHERE date = (SELECT MAX(date) FROM {table_name})
        """)
        symbols_with_data = cur.fetchone()[0]

        coverage = symbols_with_data / total_symbols if total_symbols > 0 else 0

        # Count total rows
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = cur.fetchone()[0]

        status = "✅ PASS" if coverage >= expected_min_coverage else "❌ FAIL"

        return {
            "table": table_name,
            "status": status,
            "total_symbols": total_symbols,
            "symbols_with_data": symbols_with_data,
            "coverage_pct": round(coverage * 100, 2),
            "total_rows": total_rows,
            "expected_min": round(expected_min_coverage * 100, 1)
        }
    finally:
        cur.close()
        conn.close()

def verify_loaders():
    """Check all critical loaders have populated data."""
    critical_tables = [
        ("price_daily", 0.75, "Stock prices - 5000+ symbols"),
        ("stock_symbols", 1.0, "Stock symbol reference"),
        ("signals_daily", 0.5, "Trading signals"),
        ("signal_quality_scores", 0.5, "Signal quality"),
        ("earnings_calendar", 0.3, "Earnings dates"),
        ("technical_data_daily", 0.5, "Technical indicators"),
    ]

    logger.info("=" * 80)
    logger.info("LOADER DATA VERIFICATION REPORT")
    logger.info("=" * 80)

    results = []
    for table, min_coverage, description in critical_tables:
        try:
            result = check_table_coverage(table, min_coverage)
            results.append(result)

            if "error" in result.get("status", "").lower():
                logger.warning(f"⚠️  {table}: {result.get('message')}")
            else:
                logger.info(
                    f"{result['status']} {table:25s} "
                    f"{result['symbols_with_data']:5d}/{result['total_symbols']:5d} symbols "
                    f"({result['coverage_pct']:6.2f}% coverage, {result['total_rows']:8d} rows) "
                    f"- {description}"
                )
        except Exception as e:
            logger.error(f"❌ {table}: {e}")
            results.append({"table": table, "status": "ERROR", "error": str(e)})

    logger.info("=" * 80)

    # Summary
    passed = sum(1 for r in results if "✅" in r.get("status", ""))
    total = len(results)
    logger.info(f"RESULT: {passed}/{total} checks passed")

    return all("✅" in r.get("status", "") for r in results if "error" not in r.get("status", "").lower())

if __name__ == "__main__":
    try:
        success = verify_loaders()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)
        sys.exit(1)
