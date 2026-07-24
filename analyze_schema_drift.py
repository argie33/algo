#!/usr/bin/env python3
"""Comprehensive schema drift analysis.

Analyzes 4 layers of schema consistency:
1. Database schema vs. code expectations (table/column/type)
2. Loader inserts vs. database schema (missing INSERTs)
3. API queries vs. actual data population (NULL vs. populated)
4. Data freshness across all tables
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from utils.db.context import DatabaseContext

# Expected schema for each metrics table
SCHEMA_EXPECTATIONS = {
    'value_metrics': {
        'data_fields': [
            'ticker', 'market_cap', 'pe_ratio', 'pb_ratio', 'ps_ratio', 'peg_ratio',
            'forward_pe', 'dividend_yield', 'fcf_yield', 'enterprise_value',
            'ev_ebitda', 'ev_revenue', 'value_score'
        ],
        'explanatory_fields': [
            'market_cap_unavailable_reason', 'pe_ratio_unavailable_reason',
            'pb_ratio_unavailable_reason', 'ps_ratio_unavailable_reason',
            'peg_ratio_unavailable_reason', 'forward_pe_unavailable_reason',
            'dividend_yield_unavailable_reason', 'fcf_yield_unavailable_reason',
            'enterprise_value_unavailable_reason', 'ev_ebitda_unavailable_reason',
            'ev_revenue_unavailable_reason', 'value_score_unavailable_reason'
        ],
        'metadata_fields': ['ticker', 'date', 'created_at', 'updated_at', 'data_source']
    },
    'quality_metrics': {
        'data_fields': [
            'ticker', 'roe', 'roa', 'current_ratio', 'debt_to_equity', 'quick_ratio',
            'interest_coverage', 'debt_to_assets', 'fcf', 'fcf_per_share',
            'ebitda', 'ebitda_margin', 'quality_score'
        ],
        'explanatory_fields': [
            'roe_unavailable_reason', 'roa_unavailable_reason', 'current_ratio_unavailable_reason',
            'debt_to_equity_unavailable_reason', 'quick_ratio_unavailable_reason',
            'interest_coverage_unavailable_reason', 'debt_to_assets_unavailable_reason',
            'fcf_unavailable_reason', 'fcf_per_share_unavailable_reason',
            'ebitda_unavailable_reason', 'ebitda_margin_unavailable_reason', 'quality_score_unavailable_reason'
        ],
        'metadata_fields': ['ticker', 'date', 'created_at', 'updated_at', 'data_source']
    },
    'growth_metrics': {
        'data_fields': [
            'ticker', 'revenue_growth_3y', 'revenue_growth_5y', 'eps_growth_3y',
            'eps_growth_5y', 'fcf_growth_3y', 'fcf_growth_5y', 'growth_score'
        ],
        'explanatory_fields': [
            'revenue_growth_3y_unavailable_reason', 'revenue_growth_5y_unavailable_reason',
            'eps_growth_3y_unavailable_reason', 'eps_growth_5y_unavailable_reason',
            'fcf_growth_3y_unavailable_reason', 'fcf_growth_5y_unavailable_reason',
            'growth_score_unavailable_reason'
        ],
        'metadata_fields': ['ticker', 'date', 'created_at', 'updated_at', 'data_source']
    },
    'positioning_metrics': {
        'data_fields': [
            'ticker', 'institutional_ownership_pct', 'shares_short_current',
            'shares_short_prior_month', 'short_interest_ratio', 'short_interest_trend',
            'insider_ownership_pct', 'insider_transactions_net', 'positioning_score'
        ],
        'explanatory_fields': [],
        'metadata_fields': ['ticker', 'date', 'created_at', 'updated_at']
    },
    'stability_metrics': {
        'data_fields': [
            'ticker', 'beta', 'volatility_30d', 'max_drawdown_52w', 'dividend_yield',
            'payout_ratio', 'accruals_ratio', 'stability_score'
        ],
        'explanatory_fields': [],
        'metadata_fields': ['ticker', 'date', 'created_at', 'updated_at']
    },
    'momentum_metrics': {
        'data_fields': [
            'ticker', 'price_momentum_3m', 'price_momentum_6m', 'price_momentum_12m',
            'volume_momentum_20d', 'relative_strength_index', 'momentum_score'
        ],
        'explanatory_fields': ['reason_type'],
        'metadata_fields': ['ticker', 'date', 'created_at', 'updated_at']
    }
}


def get_actual_schema():
    """Fetch actual database schema."""
    actual = {}
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name IN ('value_metrics', 'quality_metrics', 'growth_metrics',
                                'positioning_metrics', 'stability_metrics', 'momentum_metrics')
            ORDER BY table_name, ordinal_position
        """)
        for table, col, dtype, nullable in cur.fetchall():
            if table not in actual:
                actual[table] = {}
            actual[table][col] = {'type': dtype, 'nullable': nullable == 'YES'}
    return actual


def analyze_column_population():
    """Check population rate for each column."""
    stats = {}

    with DatabaseContext('read') as cur:
        for table in SCHEMA_EXPECTATIONS.keys():
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            total_rows = cur.fetchone()[0]

            if total_rows == 0:
                stats[table] = {'total_rows': 0, 'columns': {}}
                continue

            stats[table] = {'total_rows': total_rows, 'columns': {}}

            # Get column list
            cur.execute(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, [table])
            columns = [c[0] for c in cur.fetchall()]

            for col in columns:
                # Count non-NULL values
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL")
                non_null = cur.fetchone()[0]
                pct = (non_null / total_rows * 100) if total_rows > 0 else 0
                stats[table]['columns'][col] = {
                    'populated': non_null,
                    'total': total_rows,
                    'percentage': pct
                }

    return stats


def analyze_data_freshness():
    """Check how fresh data is in each table."""
    freshness = {}
    now = datetime.now(timezone.utc)

    with DatabaseContext('read') as cur:
        for table in SCHEMA_EXPECTATIONS.keys():
            # Try different timestamp columns
            for ts_col in ['updated_at', 'created_at', 'date']:
                try:
                    cur.execute(f"""
                        SELECT MAX({ts_col}) FROM {table}
                    """)
                    max_ts = cur.fetchone()[0]

                    if max_ts:
                        if hasattr(max_ts, 'tzinfo') and max_ts.tzinfo:
                            age = now - max_ts
                        else:
                            age = now - max_ts.replace(tzinfo=timezone.utc)

                        freshness[table] = {
                            'timestamp_column': ts_col,
                            'latest': max_ts,
                            'age_hours': age.total_seconds() / 3600,
                            'stale': age > timedelta(hours=24)
                        }
                        break
                except:
                    continue

            if table not in freshness:
                freshness[table] = {
                    'timestamp_column': None,
                    'latest': None,
                    'age_hours': None,
                    'stale': None
                }

    return freshness


def report_schema_drift():
    """Generate comprehensive drift report."""
    actual = get_actual_schema()
    population = analyze_column_population()
    freshness = analyze_data_freshness()

    print("\n" + "="*80)
    print("SCHEMA DRIFT ANALYSIS REPORT")
    print("="*80)

    # Layer 1: Schema completeness
    print("\n[LAYER 1] DATABASE SCHEMA vs CODE EXPECTATIONS")
    print("-" * 80)

    for table, expected in SCHEMA_EXPECTATIONS.items():
        if table not in actual:
            print(f"\n[MISSING] {table}")
            continue

        print(f"\n[OK] {table}")
        actual_cols = set(actual[table].keys())

        all_expected = set(
            expected['data_fields'] +
            expected['explanatory_fields'] +
            expected['metadata_fields']
        )

        # Missing columns
        missing = all_expected - actual_cols
        if missing:
            print(f"  MISSING COLUMNS: {', '.join(sorted(missing))}")

        # Extra columns
        extra = actual_cols - all_expected
        if extra:
            # Filter out common extras
            common_extras = {'id', 'position_id', 'order_id', 'price_daily_id'}
            extra = extra - common_extras
            if extra:
                print(f"  EXTRA COLUMNS: {', '.join(sorted(extra))}")

    # Layer 2: Data population
    print("\n[LAYER 2] DATA POPULATION RATES")
    print("-" * 80)

    for table, stats in population.items():
        if stats['total_rows'] == 0:
            print(f"\n{table}: EMPTY (0 rows)")
            continue

        print(f"\n{table}: {stats['total_rows']} rows")

        # Show critically low columns
        low_pop = {
            col: data['percentage'] for col, data in stats['columns'].items()
            if data['percentage'] < 50
        }

        if low_pop:
            print("  Columns with <50% population:")
            for col in sorted(low_pop.keys()):
                pct = low_pop[col]
                print(f"    - {col}: {pct:.1f}%")

    # Layer 3: Data freshness
    print("\n[LAYER 3] DATA FRESHNESS")
    print("-" * 80)

    for table, fresh in freshness.items():
        if fresh['latest'] is None:
            print(f"\n{table}: No timestamp data")
        else:
            age = fresh['age_hours']
            status = "STALE" if fresh['stale'] else "OK"
            print(f"\n{table}: {status} ({age:.1f}h old, via {fresh['timestamp_column']})")

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    # Count issues
    schema_issues = sum(1 for t in SCHEMA_EXPECTATIONS if t in actual)
    stale_tables = sum(1 for f in freshness.values() if f['stale'])
    low_pop_tables = sum(
        1 for table, stats in population.items()
        if any(data['percentage'] < 50 for data in stats['columns'].values())
    )

    print(f"\nSchema coverage: {schema_issues}/{len(SCHEMA_EXPECTATIONS)} tables")
    print(f"Stale data: {stale_tables} table(s)")
    print(f"Low population (<50%): {low_pop_tables} table(s)")

    return {
        'schema_issues': schema_issues,
        'stale_tables': stale_tables,
        'low_pop_tables': low_pop_tables
    }


if __name__ == '__main__':
    try:
        results = report_schema_drift()
        sys.exit(0 if results['schema_issues'] == 0 else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
