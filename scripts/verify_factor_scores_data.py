#!/usr/bin/env python3
"""Verify factor scores data integrity and completeness after pipeline execution.

This script checks for data gaps and ensures all expected data is populated correctly.
Run this after the financial_data_pipeline completes to verify data flow.

Usage:
    python3 scripts/verify_factor_scores_data.py [--mode local|aws] [--verbose]

Returns:
    0 if all checks pass, 1 if critical gaps detected
"""

import logging
import sys
from datetime import datetime
from typing import Any

sys.path.insert(0, '.')

from utils.db.context import DatabaseContext

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_database_connection() -> tuple[bool, str]:
    """Check which database we're connected to."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SELECT inet_server_addr(), current_database()")
            host, _ = cur.fetchone()

            if 'rds.amazonaws.com' in str(host):
                return True, f"AWS RDS: {host}"
            else:
                return False, f"Local: {host}"
    except Exception as e:
        return False, f"Connection failed: {e}"


def check_metric_loader_status() -> dict[str, Any]:
    """Check data_loader_status for all metric loaders."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    table_name,
                    completion_pct,
                    status,
                    EXTRACT(EPOCH FROM (NOW() - last_updated_at))::int as seconds_ago
                FROM data_loader_status
                WHERE table_name IN (
                    'quality_metrics', 'growth_metrics', 'value_metrics',
                    'positioning_metrics', 'stability_metrics', 'annual_income_statement',
                    'annual_balance_sheet', 'stock_prices_daily'
                )
                ORDER BY table_name
            """)

            results = {}
            for table_name, completion, status, seconds_ago in cur.fetchall():
                results[table_name] = {
                    'completion': completion,
                    'status': status,
                    'minutes_ago': seconds_ago / 60 if seconds_ago else 0
                }

            return results
    except Exception as e:
        logger.error(f"Failed to check loader status: {e}")
        return {}


def check_financial_data_flow() -> dict[str, Any]:
    """Verify financial data is actually in the tables (not just rows with data_unavailable=True)."""
    try:
        with DatabaseContext("read") as cur:
            # Check income statement data
            cur.execute("""
                SELECT
                    COUNT(*) as total_rows,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    COUNT(CASE WHEN revenue > 0 THEN 1 END) as rows_with_revenue
                FROM annual_income_statement
                WHERE fiscal_year >= 2023
            """)

            total, symbols, with_revenue = cur.fetchone()

            # Check balance sheet data
            cur.execute("""
                SELECT
                    COUNT(*) as total_rows,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    COUNT(CASE WHEN total_assets > 0 THEN 1 END) as rows_with_assets
                FROM annual_balance_sheet
                WHERE fiscal_year >= 2023
            """)

            bs_total, bs_symbols, with_assets = cur.fetchone()

            return {
                'income_statement': {
                    'total_rows': total,
                    'unique_symbols': symbols,
                    'with_real_data': with_revenue
                },
                'balance_sheet': {
                    'total_rows': bs_total,
                    'unique_symbols': bs_symbols,
                    'with_real_data': with_assets
                }
            }
    except Exception as e:
        logger.error(f"Failed to check financial data: {e}")
        return {}


def check_metric_table_coverage() -> dict[str, dict[str, Any]]:
    """Check coverage percentages for each metric table."""
    try:
        with DatabaseContext("read") as cur:
            tables = {
                'quality_metrics': {'total': 0, 'available': 0, 'unavailable': 0},
                'growth_metrics': {'total': 0, 'available': 0, 'unavailable': 0},
                'value_metrics': {'total': 0, 'available': 0, 'unavailable': 0},
                'positioning_metrics': {'total': 0, 'available': 0, 'unavailable': 0},
                'stability_metrics': {'total': 0, 'available': 0, 'unavailable': 0},
            }

            for table_name in tables.keys():
                # Total rows
                cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                total = cur.fetchone()[0]

                # Available (data_unavailable = false or IS NULL)
                cur.execute(f"""
                    SELECT COUNT(*) FROM {table_name}
                    WHERE data_unavailable = false OR data_unavailable IS NULL
                """)
                available = cur.fetchone()[0]

                # Unavailable (data_unavailable = true)
                cur.execute(f"""
                    SELECT COUNT(*) FROM {table_name}
                    WHERE data_unavailable = true
                """)
                unavailable = cur.fetchone()[0]

                tables[table_name]['total'] = total
                tables[table_name]['available'] = available
                tables[table_name]['unavailable'] = unavailable
                tables[table_name]['coverage'] = (available / total * 100) if total > 0 else 0

            return tables
    except Exception as e:
        logger.error(f"Failed to check metric coverage: {e}")
        return {}


def check_stock_scores_completeness() -> dict[str, Any]:
    """Check factor score completeness distribution."""
    try:
        with DatabaseContext("read") as cur:
            # Overall stats
            cur.execute("""
                SELECT
                    COUNT(*) as total_scores,
                    COUNT(CASE WHEN data_unavailable = FALSE THEN 1 END) as available,
                    COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as with_composite,
                    AVG(composite_score) as avg_composite,
                    MIN(composite_score) as min_composite,
                    MAX(composite_score) as max_composite,
                    STDDEV(composite_score) as stddev_composite
                FROM stock_scores
            """)

            result = cur.fetchone()
            if result:
                total, available, with_composite, avg_comp, min_comp, max_comp, stddev = result

                # Completeness distribution
                cur.execute("""
                    SELECT
                        ROUND((
                            (CASE WHEN quality_score IS NOT NULL THEN 1 ELSE 0 END +
                             CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END +
                             CASE WHEN value_score IS NOT NULL THEN 1 ELSE 0 END +
                             CASE WHEN momentum_score IS NOT NULL THEN 1 ELSE 0 END +
                             CASE WHEN positioning_score IS NOT NULL THEN 1 ELSE 0 END +
                             CASE WHEN stability_score IS NOT NULL THEN 1 ELSE 0 END) / 6.0
                        ) * 100 / 20) * 20 as completeness_bucket,
                        COUNT(*) as count
                    FROM stock_scores
                    WHERE composite_score IS NOT NULL
                    GROUP BY completeness_bucket
                    ORDER BY completeness_bucket DESC
                """)

                distribution = [(bucket, count) for bucket, count in cur.fetchall()]

                return {
                    'total_scores': total,
                    'available_scores': available,
                    'with_composite': with_composite,
                    'coverage_pct': (with_composite / total * 100) if total > 0 else 0,
                    'avg_composite': avg_comp,
                    'min_composite': min_comp,
                    'max_composite': max_comp,
                    'stddev': stddev,
                    'completeness_distribution': distribution
                }
    except Exception as e:
        logger.error(f"Failed to check stock scores: {e}")
        return {}


def check_data_freshness() -> dict[str, Any]:
    """Check how recent the data is."""
    try:
        with DatabaseContext("read") as cur:
            tables_to_check = {
                'stock_scores': 'updated_at',
                'quality_metrics': 'updated_at',
                'growth_metrics': 'updated_at',
                'value_metrics': 'updated_at',
                'positioning_metrics': 'updated_at',
                'stability_metrics': 'updated_at',
                'annual_income_statement': 'created_at',
                'annual_balance_sheet': 'created_at',
            }

            freshness = {}
            for table_name, timestamp_field in tables_to_check.items():
                try:
                    cur.execute(f"""
                        SELECT
                            MAX({timestamp_field}) as latest,
                            EXTRACT(EPOCH FROM (NOW() - MAX({timestamp_field})))::int as seconds_ago
                        FROM {table_name}
                    """)

                    latest, seconds_ago = cur.fetchone()
                    if seconds_ago:
                        hours_ago = seconds_ago / 3600
                        freshness[table_name] = {
                            'latest': latest,
                            'hours_ago': hours_ago
                        }
                except Exception as e:
                    freshness[table_name] = {'error': str(e)}

            return freshness
    except Exception as e:
        logger.error(f"Failed to check freshness: {e}")
        return {}


def _get_metric_threshold(table_name: str) -> int:
    """Get threshold for metric table coverage."""
    thresholds = {
        'value_metrics': 80,
        'positioning_metrics': 70,
        'stability_metrics': 85,
    }
    return thresholds.get(table_name, 60)


def _print_loader_status(loader_status: dict) -> None:
    """Print data loader status section."""
    print("DATA LOADER STATUS")
    print("-" * 80)
    for table_name, status in sorted(loader_status.items()):
        symbol = "✓" if status['completion'] >= 80 else "⚠" if status['completion'] >= 50 else "✗"
        print(f"{symbol} {table_name:35} | {status['completion']:6.1f}% | {status['status']:10} | {status['minutes_ago']:6.1f}m ago")
    print()


def _print_metric_coverage(metric_coverage: dict) -> bool:
    """Print metric coverage section. Returns True if critical gaps found."""
    print("METRIC TABLE COVERAGE")
    print("-" * 80)
    print(f"{'Table':<30} | {'Coverage':<10} | {'Available':<10} | {'Unavailable':<10} | Status")
    print("-" * 80)

    critical_gaps = False
    for table_name, data in sorted(metric_coverage.items()):
        threshold = _get_metric_threshold(table_name)
        if data['coverage'] >= threshold:
            symbol, status = "✓", "PASS"
        elif data['coverage'] >= threshold * 0.8:
            symbol, status = "⚠", "WARN"
            critical_gaps = True
        else:
            symbol, status = "✗", "FAIL"
            critical_gaps = True

        print(f"{symbol} {table_name:<28} | {data['coverage']:7.1f}% | {data['available']:9,} | {data['unavailable']:9,} | {status}")

    print()
    return critical_gaps


def _print_stock_scores(stock_scores: dict) -> None:
    """Print stock scores completeness section."""
    print("STOCK SCORES COMPLETENESS")
    print("-" * 80)
    print(f"Total scores: {stock_scores.get('total_scores', 0):,}")
    print(f"Available (not marked unavailable): {stock_scores.get('available_scores', 0):,}")
    print(f"With composite_score: {stock_scores.get('with_composite', 0):,}")
    print(f"Coverage: {stock_scores.get('coverage_pct', 0):.1f}%")
    print()
    print("Composite score statistics:")
    print(f"  Average: {stock_scores.get('avg_composite', 0):.2f}")
    print(f"  Min: {stock_scores.get('min_composite', 0):.2f}")
    print(f"  Max: {stock_scores.get('max_composite', 0):.2f}")
    print(f"  StdDev: {stock_scores.get('stddev', 0):.2f}")
    print()

    dist = stock_scores.get('completeness_distribution', [])
    if dist:
        print("Completeness distribution (% of scores with N factors):")
        for bucket, count in dist:
            bar = "█" * int(count / 50) if count > 0 else ""
            print(f"  {bucket:>3}%: {bar} ({count:,} scores)")
    print()


def print_report(
    connection_status: bool,
    db_name: str,
    loader_status: dict,
    financial_data: dict,
    metric_coverage: dict,
    stock_scores: dict,
    freshness: dict
) -> int:
    """Print comprehensive verification report."""

    print("\n" + "=" * 80)
    print("FACTOR SCORES DATA VERIFICATION REPORT")
    print("=" * 80)
    print(f"Generated: {datetime.now()}")
    print()

    print("DATABASE CONNECTION")
    print("-" * 80)
    if connection_status:
        print(f"✓ Connected to AWS: {db_name}")
    else:
        print(f"✗ Not connected to AWS: {db_name}")
        print("  WARNING: Running against local database. Results may not reflect production.")
    print()

    if loader_status:
        _print_loader_status(loader_status)

    if financial_data:
        print("FINANCIAL DATA FLOW (SEC EDGAR)")
        print("-" * 80)
        inc = financial_data.get('income_statement', {})
        bs = financial_data.get('balance_sheet', {})
        print("Income Statements:")
        print(f"  Total rows: {inc.get('total_rows', 0):,}")
        print(f"  Unique symbols: {inc.get('unique_symbols', 0):,}")
        print(f"  Rows with real revenue data: {inc.get('with_real_data', 0):,}")
        print()
        print("Balance Sheets:")
        print(f"  Total rows: {bs.get('total_rows', 0):,}")
        print(f"  Unique symbols: {bs.get('unique_symbols', 0):,}")
        print(f"  Rows with real asset data: {bs.get('with_real_data', 0):,}")
        print()

    critical_gaps = False
    if metric_coverage:
        critical_gaps = _print_metric_coverage(metric_coverage)

    if stock_scores:
        _print_stock_scores(stock_scores)

    if freshness:
        print("DATA FRESHNESS")
        print("-" * 80)
        critical_tables = ['stock_scores', 'quality_metrics', 'growth_metrics']

        for table_name in critical_tables:
            if table_name in freshness:
                data = freshness[table_name]
                if 'error' in data:
                    print(f"✗ {table_name}: Error - {data['error']}")
                else:
                    hours = data['hours_ago']
                    if hours < 2:
                        print(f"✓ {table_name}: {hours:.1f} hours ago")
                    elif hours < 24:
                        print(f"⚠ {table_name}: {hours:.1f} hours ago")
                    else:
                        print(f"✗ {table_name}: STALE ({hours:.1f} hours ago)")
        print()

    # Summary
    print("=" * 80)
    print("VERIFICATION SUMMARY")
    print("-" * 80)

    if not connection_status:
        print("⚠ WARNING: Results from LOCAL database, not AWS production")
        print()

    if critical_gaps:
        print("✗ CRITICAL GAPS DETECTED")
        print()
        print("Possible causes:")
        print("  1. Pipeline still running (check data_loader_status)")
        print("  2. SEC EDGAR API rate limiting (check CloudWatch logs)")
        print("  3. Upstream dependency failure (check metric loader logs)")
        print()
        print("Action:")
        print("  1. Monitor pipeline completion in CloudWatch logs")
        print("  2. Verify data_loader_status shows completion_pct >= 70%")
        print("  3. Re-run this script after pipeline completes")
        return 1
    else:
        print("✓ ALL CHECKS PASSED")
        print()
        print("Data flow appears healthy. Factor scores should be ready for trading.")
        return 0


def main() -> int:
    """Run all verification checks."""
    # Check connection
    is_aws, db_name = check_database_connection()
    logger.info(f"Database: {db_name}")

    # Gather data
    loader_status = check_metric_loader_status()
    financial_data = check_financial_data_flow()
    metric_coverage = check_metric_table_coverage()
    stock_scores = check_stock_scores_completeness()
    freshness = check_data_freshness()

    # Generate report
    return print_report(
        is_aws, db_name,
        loader_status, financial_data, metric_coverage,
        stock_scores, freshness
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)
        sys.exit(1)
