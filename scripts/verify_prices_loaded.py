#!/usr/bin/env python3
"""Quick health check: verify prices are loaded before trading.

Usage:
    python scripts/verify_prices_loaded.py     # Check status
    python scripts/verify_prices_loaded.py || exit 1  # Fail if incomplete (for CI/CD)

Exit Codes:
    0 = Prices OK (>=75% coverage)
    1 = Prices incomplete (<75% coverage) or database error
"""

import sys
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)


def check_price_coverage():
    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    symbols_loaded,
                    symbol_count,
                    ROUND(100.0 * symbols_loaded / NULLIF(symbol_count, 0), 1) as coverage_pct,
                    status,
                    error_message,
                    last_updated,
                    execution_started
                FROM data_loader_status
                WHERE table_name = 'price_daily'
                ORDER BY last_updated DESC
                LIMIT 1
            """)
            row = cur.fetchone()

            if not row:
                return False, 0.0, 0, 0, "NOT_FOUND", "price_daily not in data_loader_status"

            symbols_loaded, total, coverage, status, error, last_updated, exec_started = row
            success = coverage >= 75.0 if coverage else False

            return success, coverage or 0.0, symbols_loaded or 0, total or 0, status or "UNKNOWN", error

    except Exception as e:
        logger.error(f"[ERROR] Database check failed: {e}")
        return False, 0.0, 0, 0, "ERROR", str(e)


def main():
    """Run health check and print results."""
    success, coverage, loaded, total, status, error = check_price_coverage()

    if success:
        print(f"✅ PRICES OK: {loaded}/{total} symbols ({coverage:.1f}% coverage)")
        print(f"   Status: {status}")
        if loaded < total:
            missing = total - loaded
            print(f"   Missing: {missing} symbols ({100 - coverage:.1f}%) — minor incompleteness")
        return 0

    else:
        print(f"❌ PRICES INCOMPLETE: {loaded}/{total} symbols ({coverage:.1f}% coverage)")
        if coverage == 0:
            print(f"   Status: {status}")
            if error:
                print(f"   Error: {error[:150]}")
            print()
            print("   🔴 CRITICAL: No prices loaded. Dashboard will show '--' for all data.")
            print()
            print("   Recovery options:")
            print("   1. Quick check (local orchestrator):")
            print("      python scripts/run_local_orchestrator.py --morning")
            print()
            print("   2. Retry via AWS (recommended for production):")
            print("      python scripts/recover_incomplete_loader.py")
            print()
            print("   3. Manual trigger (if scripts not available):")
            print("      aws lambda invoke --function-name algo-trigger-loaders \\")
            print('        --payload \'{"loader_name":"price_daily"}\' /tmp/result.json')
        else:
            missing = total - loaded
            print(f"   Missing: {missing} symbols ({100 - coverage:.1f}%) — need >= 75% to proceed")
            print()
            print("   Recovery:")
            print("      python scripts/recover_incomplete_loader.py")

        return 1


if __name__ == "__main__":
    sys.exit(main())
