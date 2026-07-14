#!/usr/bin/env python3
"""Verify dashboard data quality - checks for issues reported in Session 138.

Monitors:
1. Position count consistency (snapshot vs actual vs API)
2. Growth score coverage
3. Breadth momentum staleness
4. Put/Call ratio data availability

Usage:
    python3 scripts/verify_dashboard_data_quality.py
    python3 scripts/verify_dashboard_data_quality.py --watch 60  # Poll every 60s
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class DashboardDataQualityMonitor:
    """Monitor dashboard data quality metrics."""

    def __init__(self) -> None:
        """Initialize database connection."""
        try:
            self.conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
            self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        except psycopg2.OperationalError as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def check_positions_consistency(self) -> dict:
        """Check if position counts are consistent across data sources."""
        logger.info("=" * 60)
        logger.info("CHECKING: Position Count Consistency")
        logger.info("=" * 60)

        # 1. Get latest portfolio snapshot position_count
        self.cur.execute("""
            SELECT position_count, snapshot_date, updated_at
            FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC LIMIT 1
        """)
        snap = self.cur.fetchone()
        snap_count = snap["position_count"] if snap else None
        snap_date = snap["snapshot_date"] if snap else None
        snap_updated = snap["updated_at"] if snap else None

        # 2. Get actual open positions count
        self.cur.execute("SELECT COUNT(*) as count FROM algo_positions WHERE status = 'open'")
        actual_count = self.cur.fetchone()["count"]

        # 3. Calculate snapshot age
        if snap_updated:
            self.cur.execute("SELECT NOW()::timestamp")
            now = self.cur.fetchone()[0]
            age_seconds = int((now - snap_updated).total_seconds())
            age_minutes = age_seconds / 60
        else:
            age_minutes = None
            age_seconds = None

        # 4. Report findings
        mismatch = snap_count != actual_count if snap_count is not None else False
        status = "❌ MISMATCH" if mismatch else "✅ OK"

        logger.info(f"Latest snapshot: {snap_date}")
        logger.info(f"  - Snapshot position_count: {snap_count}")
        logger.info(f"  - Actual open positions: {actual_count}")
        logger.info(f"  - Age: {age_minutes:.1f} min ({age_seconds}s)")
        logger.info(f"  - Status: {status}")

        if mismatch:
            logger.warning(
                f"Position count mismatch: snapshot={snap_count} vs actual={actual_count}. "
                f"Dashboard will use actual count, but consider running Phase 9 to update snapshot."
            )

        return {
            "snapshot_count": snap_count,
            "actual_count": actual_count,
            "snapshot_age_minutes": age_minutes,
            "snapshot_age_seconds": age_seconds,
            "snapshot_date": str(snap_date) if snap_date else None,
            "mismatch": mismatch,
            "status": status,
        }

    def check_growth_score_coverage(self) -> dict:
        """Check growth_score NULL coverage."""
        logger.info("=" * 60)
        logger.info("CHECKING: Growth Score Coverage")
        logger.info("=" * 60)

        self.cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END) as with_growth,
                SUM(CASE WHEN growth_score IS NULL THEN 1 ELSE 0 END) as null_growth
            FROM stock_scores
        """)
        row = self.cur.fetchone()
        total = row["total"]
        with_growth = row["with_growth"] or 0
        null_growth = row["null_growth"] or 0
        coverage_pct = (with_growth / total * 100) if total > 0 else 0

        status = "✅ OK" if coverage_pct >= 85 else ("⚠️ WARNING" if coverage_pct >= 70 else "❌ LOW")

        logger.info(f"Total stock_scores: {total}")
        logger.info(f"  - With growth_score: {with_growth} ({coverage_pct:.1f}%)")
        logger.info(f"  - NULL growth_score: {null_growth} ({100 - coverage_pct:.1f}%)")
        logger.info(f"  - Status: {status}")

        if coverage_pct < 85:
            logger.warning(
                f"Growth score coverage is {coverage_pct:.1f}%. Expected 85%+. "
                f"This is expected for symbols with incomplete SEC financial data (SPACs, new IPOs)."
            )

        return {
            "total": total,
            "with_growth": with_growth,
            "null_growth": null_growth,
            "coverage_pct": coverage_pct,
            "status": status,
        }

    def check_breadth_momentum_staleness(self) -> dict:
        """Check if breadth_momentum is updating daily."""
        logger.info("=" * 60)
        logger.info("CHECKING: Breadth Momentum Staleness")
        logger.info("=" * 60)

        self.cur.execute("""
            SELECT date, breadth_momentum_10d
            FROM market_health_daily
            ORDER BY date DESC
            LIMIT 10
        """)
        rows = self.cur.fetchall()

        if not rows:
            logger.warning("No market_health_daily rows found")
            return {"status": "❌ NO DATA", "rows": 0}

        # Check for updates
        dates_and_values = [(row["date"], row["breadth_momentum_10d"]) for row in rows]
        logger.info("Recent breadth_momentum values:")
        for date, value in dates_and_values[:5]:
            logger.info(f"  {date}: {value}")

        # Check if stuck (same value for 7+ days)
        if len(dates_and_values) >= 7:
            same_value_count = 1
            for i in range(len(dates_and_values) - 1):
                if (
                    dates_and_values[i][1] is not None
                    and dates_and_values[i + 1][1] is not None
                    and dates_and_values[i][1] == dates_and_values[i + 1][1]
                ):
                    same_value_count += 1
                else:
                    break
            is_stuck = same_value_count >= 7
            status = "❌ STUCK" if is_stuck else "✅ UPDATING"
        else:
            is_stuck = False
            status = "✅ RECENT"

        logger.info(f"  - Status: {status}")

        if is_stuck:
            logger.warning(
                f"Breadth momentum stuck at same value for 7+ days. "
                f"Check market_health_daily loader or orchestrator execution."
            )

        return {
            "rows": len(dates_and_values),
            "latest_value": dates_and_values[0][1] if dates_and_values else None,
            "is_stuck": is_stuck,
            "status": status,
        }

    def check_put_call_ratio_availability(self) -> dict:
        """Check put_call_ratio data availability."""
        logger.info("=" * 60)
        logger.info("CHECKING: Put/Call Ratio Data")
        logger.info("=" * 60)

        self.cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN put_call_ratio IS NOT NULL THEN 1 ELSE 0 END) as with_pcr
            FROM market_health_daily
        """)
        row = self.cur.fetchone()
        total = row["total"]
        with_pcr = row["with_pcr"] or 0

        # This is expected to be NULL - check if it's intentional
        self.cur.execute("""
            SELECT DISTINCT put_call_ratio_data_unavailable
            FROM market_health_daily
            WHERE put_call_ratio_data_unavailable IS NOT NULL
            LIMIT 1
        """)
        unavail_flag = self.cur.fetchone()

        status = "✅ BY DESIGN" if with_pcr == 0 and unavail_flag else "❌ UNEXPECTED"

        logger.info(f"Put/Call ratio in market_health_daily:")
        logger.info(f"  - Total rows: {total}")
        logger.info(f"  - With data: {with_pcr}")
        logger.info(f"  - NULL rows: {total - with_pcr}")
        logger.info(f"  - Unavailable flag present: {bool(unavail_flag)}")
        logger.info(f"  - Status: {status}")

        if status == "✅ BY DESIGN":
            logger.info(
                "Note: Put/Call ratio is intentionally unavailable. "
                "No verified CBOE real-time data source exists (PCRX is Pacira BioSciences stock, not put/call index). "
                "To enable: Set up Polygon.io API integration."
            )

        return {
            "total": total,
            "with_pcr": with_pcr,
            "null_rows": total - with_pcr,
            "unavailable_flag_present": bool(unavail_flag),
            "status": status,
        }

    def run_all_checks(self) -> dict:
        """Run all data quality checks."""
        try:
            results = {
                "timestamp": datetime.now().isoformat(),
                "positions": self.check_positions_consistency(),
                "growth_score": self.check_growth_score_coverage(),
                "breadth_momentum": self.check_breadth_momentum_staleness(),
                "put_call_ratio": self.check_put_call_ratio_availability(),
            }

            logger.info("=" * 60)
            logger.info("SUMMARY")
            logger.info("=" * 60)
            logger.info(f"Positions: {results['positions']['status']}")
            logger.info(f"Growth Score: {results['growth_score']['status']}")
            logger.info(f"Breadth Momentum: {results['breadth_momentum']['status']}")
            logger.info(f"Put/Call Ratio: {results['put_call_ratio']['status']}")
            logger.info("=" * 60)

            return results
        except Exception as e:
            logger.error(f"Error during checks: {e}", exc_info=True)
            raise
        finally:
            self.conn.close()


def main() -> None:
    """Run dashboard data quality checks."""
    parser = argparse.ArgumentParser(description="Verify dashboard data quality")
    parser.add_argument(
        "--watch",
        type=int,
        metavar="SECONDS",
        help="Poll every N seconds (continuous monitoring)",
    )
    args = parser.parse_args()

    if args.watch:
        # Continuous monitoring
        try:
            while True:
                monitor = DashboardDataQualityMonitor()
                monitor.run_all_checks()
                logger.info(f"Next check in {args.watch} seconds...\n")
                time.sleep(args.watch)
        except KeyboardInterrupt:
            logger.info("Monitoring stopped")
            sys.exit(0)
    else:
        # Single check
        monitor = DashboardDataQualityMonitor()
        monitor.run_all_checks()


if __name__ == "__main__":
    main()
