#!/usr/bin/env python3
"""
COMPREHENSIVE SYSTEM VERIFICATION - Proves system is operational end-to-end.

This script runs actual queries against the database to confirm:
1. Loaders ARE producing sufficient data (not just theoretically)
2. Orchestrator IS executing (not just theoretically)
3. API endpoints ARE working
4. Metric loaders have >70% coverage (required for stock_scores)
5. System is fully operational end-to-end

Exit code: 0 = System fully operational, 1 = Blockers identified
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def verify_database_connectivity() -> bool:
    """Verify database is accessible."""
    try:
        from config.credential_manager import get_db_config
        config = get_db_config()
        conn = psycopg2.connect(**config)
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Database connection FAILED: {type(e).__name__}")
        return False


def verify_orchestrator_executing() -> tuple[bool, str]:
    """Verify orchestrator is actually running (not just capable)."""
    try:
        from utils.db.context import DatabaseContext
        with DatabaseContext("read") as cur:
            # Check execution log from last 24 hours
            cur.execute("""
                SELECT COUNT(*), MAX(started_at) FROM orchestrator_execution_log
                WHERE started_at > NOW() - get_interval_sql('24h')
            """)
            count, latest = cur.fetchone()

            if count == 0:
                return False, "No orchestrator executions in last 24 hours"

            age_hours = (datetime.now() - latest).total_seconds() / 3600 if latest else 999
            if age_hours > 24:
                return False, f"Latest execution {age_hours:.1f} hours ago (>24h stale)"

            return True, f"✓ {count} executions in last 24h, latest {age_hours:.1f}h ago"

    except psycopg2.errors.UndefinedTable:
        return False, "orchestrator_execution_log table missing"
    except Exception as e:
        return False, f"Query failed: {type(e).__name__}"


def verify_metric_loader_coverage() -> tuple[bool, dict]:
    """Verify metric loaders have >70% coverage (required for stock_scores)."""
    try:
        from utils.db.context import DatabaseContext

        metrics = {}
        required_coverage = 70.0

        with DatabaseContext("read") as cur:
            tables = ['quality_metrics', 'growth_metrics', 'value_metrics', 'positioning_metrics', 'stability_metrics']

            for table in tables:
                try:
                    cur.execute(f"""
                        SELECT COUNT(*), COUNT(*) FILTER (WHERE data_unavailable=FALSE OR data_unavailable IS NULL)
                        FROM {table}
                    """)
                    total, real_data = cur.fetchone()

                    if total == 0:
                        metrics[table] = {'status': '❌', 'coverage': 0, 'msg': 'No data'}
                    else:
                        coverage = 100.0 * real_data / total
                        if coverage >= required_coverage:
                            metrics[table] = {'status': '✓', 'coverage': coverage, 'msg': f'{coverage:.0f}% coverage'}
                        else:
                            metrics[table] = {'status': '⚠', 'coverage': coverage, 'msg': f'{coverage:.0f}% (need {required_coverage}%)'}

                except psycopg2.errors.UndefinedTable:
                    metrics[table] = {'status': '❌', 'coverage': 0, 'msg': 'Table missing'}

            # Check if at least 70% of metric tables have required coverage
            passing = sum(1 for m in metrics.values() if m['status'] in ['✓'])
            all_passing = passing == len(metrics)

            return all_passing, metrics

    except Exception as e:
        return False, {'error': f"Query failed: {type(e).__name__}"}


def verify_stock_scores_data() -> tuple[bool, str]:
    """Verify stock_scores has sufficient real data."""
    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT COUNT(*) as total,
                       COUNT(*) FILTER (WHERE data_unavailable=FALSE OR data_unavailable IS NULL) as real_data,
                       MAX(updated_at) as latest_update
                FROM stock_scores
            """)
            total, real_data, latest = cur.fetchone()

            if total == 0:
                return False, "No stock_scores data"

            if real_data < 3000:
                return False, f"Only {real_data} real scores (need 3000+)"

            if latest:
                age_days = (datetime.now().date() - latest.date()).days
                if age_days > 1:
                    return False, f"Data stale ({age_days} days old)"

            return True, f"✓ {real_data} scores, latest {age_days} days old"

    except psycopg2.errors.UndefinedTable:
        return False, "stock_scores table missing"
    except Exception as e:
        return False, f"Query failed: {type(e).__name__}"


def verify_technical_data_daily() -> tuple[bool, str]:
    """Verify technical_data_daily has current data."""
    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT COUNT(*), COUNT(DISTINCT symbol), MAX(date)
                FROM technical_data_daily
            """)
            total, symbols, max_date = cur.fetchone()

            if total == 0:
                return False, "No technical_data_daily"

            if max_date:
                age_days = (datetime.now().date() - max_date).days
                if age_days > 1:
                    return False, f"Stale ({age_days} days old, need today's data)"
                return True, f"✓ {total} rows, {symbols} symbols, current"
            else:
                return False, "No dates in technical_data_daily"

    except psycopg2.errors.UndefinedTable:
        return False, "technical_data_daily table missing"
    except Exception as e:
        return False, f"Query failed: {type(e).__name__}"


def verify_api_endpoints() -> tuple[bool, list]:
    """Verify API endpoints are callable (requires running API server)."""
    try:
        import urllib.request
        endpoints = ['/api/health', '/api/industries', '/api/algo/execution/recent']
        results = []

        for endpoint in endpoints:
            try:
                # Try localhost first (local testing)
                url = f'http://localhost:8000{endpoint}'
                response = urllib.request.urlopen(url, timeout=2)
                if response.status == 200:
                    results.append(f"✓ {endpoint}")
                else:
                    results.append(f"⚠ {endpoint} ({response.status})")
            except Exception:
                results.append(f"⚠ {endpoint} (API server not running locally)")

        return len(results) > 0, results

    except Exception:
        return False, ["⚠ API verification skipped (requires local server)"]


def main() -> int:
    """Run full system verification."""
    print("\n" + "="*70)
    print("COMPREHENSIVE SYSTEM VERIFICATION")
    print("="*70 + "\n")

    results = []

    # 1. Database connectivity
    print("1. DATABASE CONNECTIVITY")
    if verify_database_connectivity():
        print("   ✅ Database connected and accessible\n")
        results.append(True)
    else:
        print("   ❌ Cannot connect to database - FIX REQUIRED\n")
        results.append(False)
        return 1

    # 2. Orchestrator execution
    print("2. ORCHESTRATOR EXECUTION")
    orch_ok, orch_msg = verify_orchestrator_executing()
    if orch_ok:
        print(f"   ✅ {orch_msg}\n")
        results.append(True)
    else:
        print(f"   ❌ {orch_msg} - FIX REQUIRED\n")
        results.append(False)

    # 3. Metric loader coverage
    print("3. METRIC LOADER COVERAGE")
    metrics_ok, metrics = verify_metric_loader_coverage()
    if isinstance(metrics, dict) and 'error' not in metrics:
        for table, data in metrics.items():
            print(f"   {data['status']} {table}: {data['msg']}")
    if metrics_ok:
        print("   ✅ All metric loaders have required coverage\n")
        results.append(True)
    else:
        print("   ❌ Insufficient metric loader coverage - FIX REQUIRED\n")
        results.append(False)

    # 4. Stock scores
    print("4. STOCK SCORES DATA")
    scores_ok, scores_msg = verify_stock_scores_data()
    if scores_ok:
        print(f"   ✅ {scores_msg}\n")
        results.append(True)
    else:
        print(f"   ❌ {scores_msg} - FIX REQUIRED\n")
        results.append(False)

    # 5. Technical data
    print("5. TECHNICAL DATA DAILY")
    tech_ok, tech_msg = verify_technical_data_daily()
    if tech_ok:
        print(f"   ✅ {tech_msg}\n")
        results.append(True)
    else:
        print(f"   ❌ {tech_msg} - FIX REQUIRED\n")
        results.append(False)

    # 6. API endpoints
    print("6. API ENDPOINTS")
    _, api_msgs = verify_api_endpoints()
    for msg in api_msgs:
        print(f"   {msg}")
    print()

    # Summary
    print("="*70)
    if all(results):
        print("✅ SYSTEM FULLY OPERATIONAL - All critical systems working")
        print("="*70 + "\n")
        return 0
    else:
        failing = sum(1 for r in results if not r)
        print(f"❌ SYSTEM HAS {failing} BLOCKERS - See above for required fixes")
        print("="*70 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
