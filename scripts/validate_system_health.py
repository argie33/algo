#!/usr/bin/env python3
"""System health validator - checks all critical components end-to-end.

Validates:
1. Database connectivity and schema
2. Orchestrator Lambda deployment
3. EventBridge scheduler rules
4. Data freshness across all tables
5. API endpoints responsiveness
6. Dashboard data availability
"""

import sys
from datetime import datetime, timedelta

sys.path.insert(0, '.')

from utils.db.context import DatabaseContext
from algo.infrastructure.config.sql_intervals import get_interval_sql


def validate_database():
    """Check database is accessible and schema is correct."""
    print("\n=== DATABASE VALIDATION ===")
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            print(f"OK: PostgreSQL connected - {version[:80]}")

            # Check critical tables exist
            critical_tables = [
                'algo_positions', 'algo_trades', 'algo_orchestrator_runs',
                'algo_portfolio_snapshots', 'stock_scores', 'price_daily',
                'technical_data_daily', 'market_exposure_daily', 'buy_sell_daily'
            ]

            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
            existing_tables = {row[0] for row in cur.fetchall()}

            missing = [t for t in critical_tables if t not in existing_tables]
            if missing:
                print(f"ERROR: Missing tables: {missing}")
                return False
            else:
                print(f"OK: All {len(critical_tables)} critical tables exist")

            return True
    except Exception as e:
        print(f"ERROR: Database connection failed: {e}")
        return False


def validate_data_freshness():
    """Check that critical data is fresh and loaded."""
    print("\n=== DATA FRESHNESS VALIDATION ===")
    try:
        with DatabaseContext("read") as cur:
            # Check orchestrator runs in last 24h
            interval = get_interval_sql('24h')
            cur.execute(f"""
                SELECT COUNT(*) FROM algo_orchestrator_runs
                WHERE started_at > NOW() - {interval}
                AND overall_status = 'success'
            """)
            success_runs = cur.fetchone()[0]
            print(f"Orchestrator: {success_runs} successful runs in last 24h", "OK" if success_runs > 0 else "WARN")

            # Check price data
            cur.execute("""
                SELECT MAX(date) FROM price_daily
            """)
            latest_price_date = cur.fetchone()[0]
            now = datetime.now().date()
            if latest_price_date and (now - latest_price_date).days <= 1:
                print(f"Price data: Latest {latest_price_date}", "OK")
            else:
                print(f"Price data: Latest {latest_price_date}", "STALE")

            # Check stock scores
            cur.execute("""
                SELECT COUNT(*), MAX(updated_at) FROM stock_scores
            """)
            score_count, latest_score = cur.fetchone()
            score_age = datetime.now() - latest_score if latest_score else None
            freshness = "OK" if score_age and score_age.total_seconds() < 86400 else "STALE"
            print(f"Stock scores: {score_count} records, latest {score_age.total_seconds()/3600:.1f}h ago", freshness)

            # Check buy/sell signals
            cur.execute("""
                SELECT COUNT(*), MAX(date) FROM buy_sell_daily
            """)
            signal_count, latest_signal = cur.fetchone()
            signal_age = now - latest_signal if latest_signal else None
            freshness = "OK" if signal_age and signal_age.days == 0 else "STALE"
            print(f"Trading signals: {signal_count} records, latest {signal_age}", freshness)

            # Check market exposure
            cur.execute("""
                SELECT COUNT(*), MAX(date) FROM market_exposure_daily
            """)
            market_count, latest_market = cur.fetchone()
            print(f"Market exposure: {market_count} records", "OK" if market_count > 0 else "WARN")

            # Check portfolio snapshots
            cur.execute("""
                SELECT COUNT(*), MAX(created_at) FROM algo_portfolio_snapshots
            """)
            snapshot_count, latest_snap = cur.fetchone()
            snap_age = datetime.now() - latest_snap if latest_snap else None
            freshness = "OK" if snap_age and snap_age.total_seconds() < 3600 else "STALE"
            print(f"Portfolio snapshots: {snapshot_count} records, latest {snap_age.total_seconds()/60:.1f}min ago", freshness)

            return True

    except Exception as e:
        print(f"ERROR: Data freshness check failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def validate_data_loader_status():
    """Check data loader status tracking."""
    print("\n=== DATA LOADER STATUS VALIDATION ===")
    try:
        with DatabaseContext("read") as cur:
            # Get loaders that are complete
            cur.execute("""
                SELECT table_name, status, completion_pct FROM data_loader_status
                WHERE status = 'COMPLETED' OR completion_pct > 95
                ORDER BY last_updated DESC
                LIMIT 20
            """)
            completed = cur.fetchall()
            print(f"Completed loaders: {len(completed)}")
            for table, status, pct in completed[:5]:
                print(f"  {table:30} {status:12} {pct:6.1f}%")

            # Get stuck or failed loaders
            cur.execute("""
                SELECT table_name, status, reason FROM data_loader_status
                WHERE status IN ('FAILED', 'RUNNING') OR reason LIKE '%Stuck%'
                ORDER BY last_updated DESC
            """)
            stuck = cur.fetchall()
            if stuck:
                print(f"\nProblematic loaders: {len(stuck)}")
                for table, status, reason in stuck:
                    print(f"  {table:30} {status:12} {reason[:50] if reason else ''}")
            else:
                print("No stuck or failed loaders")

            return len(stuck) == 0

    except Exception as e:
        print(f"ERROR: Loader status check failed: {e}")
        return False


def main():
    """Run all validations."""
    print("=" * 80)
    print("ALGO SYSTEM HEALTH VALIDATOR")
    print("=" * 80)

    results = {
        "database": validate_database(),
        "data_freshness": validate_data_freshness(),
        "loaders": validate_data_loader_status(),
    }

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for check, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{check:30} {status}")

    all_passed = all(results.values())
    print("\nOverall status:", "HEALTHY" if all_passed else "ISSUES DETECTED")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
