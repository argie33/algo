#!/usr/bin/env python3
"""Diagnostic script to verify scores data pipeline end-to-end."""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.db import DatabaseContext

def check_db_data():
    """Check what's actually in the database."""
    print("\n" + "="*70)
    print("DATABASE AUDIT: Scores Tables")
    print("="*70)

    with DatabaseContext("read") as cur:
        # Check stock_scores
        cur.execute("""
            SELECT
                COUNT(*) as total_scores,
                COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as composite_score_count,
                COUNT(CASE WHEN quality_score IS NOT NULL THEN 1 END) as quality_score_count,
                COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END) as value_score_count,
                COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as growth_score_count,
                COUNT(CASE WHEN momentum_score IS NOT NULL THEN 1 END) as momentum_score_count,
                COUNT(CASE WHEN positioning_score IS NOT NULL THEN 1 END) as positioning_score_count,
                COUNT(CASE WHEN stability_score IS NOT NULL THEN 1 END) as stability_score_count,
                AVG(data_completeness) as avg_completeness,
                MIN(updated_at) as oldest_update,
                MAX(updated_at) as newest_update
            FROM stock_scores
        """)
        row = cur.fetchone()
        if row:
            print(f"\nstock_scores table:")
            print(f"  Total rows: {row[0]}")
            print(f"  Composite scores: {row[1]} ({100*row[1]/row[0]:.1f}%)")
            print(f"  Quality scores: {row[2]} ({100*row[2]/row[0]:.1f}%)")
            print(f"  Value scores: {row[3]} ({100*row[3]/row[0]:.1f}%)")
            print(f"  Growth scores: {row[4]} ({100*row[4]/row[0]:.1f}%)")
            print(f"  Momentum scores: {row[5]} ({100*row[5]/row[0]:.1f}%)")
            print(f"  Positioning scores: {row[6]} ({100*row[6]/row[0]:.1f}%)")
            print(f"  Stability scores: {row[7]} ({100*row[7]/row[0]:.1f}%)")
            print(f"  Avg data completeness: {row[8]:.1f}%")
            print(f"  Updated range: {row[9]} to {row[10]}")

        # Check metrics tables
        for table in ['value_metrics', 'quality_metrics', 'growth_metrics', 'positioning_metrics', 'momentum_metrics', 'stability_metrics']:
            cur.execute(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN data_unavailable = TRUE THEN 1 END) as unavailable_count,
                    MAX(updated_at) as latest_update
                FROM {table}
            """)
            row = cur.fetchone()
            if row:
                print(f"\n{table}:")
                print(f"  Total rows: {row[0]}")
                print(f"  Marked unavailable: {row[1]}")
                print(f"  Latest update: {row[2]}")

        # Sample quality_metrics for a stock with data
        print("\n" + "-"*70)
        print("SAMPLE: Quality metrics for AAPL")
        print("-"*70)
        cur.execute("""
            SELECT
                symbol,
                roe,
                roe_unavailable_reason,
                roa,
                roa_unavailable_reason,
                operating_margin,
                operating_margin_unavailable_reason,
                debt_to_equity,
                debt_to_equity_unavailable_reason,
                data_unavailable
            FROM quality_metrics
            WHERE symbol = 'AAPL'
        """)
        row = cur.fetchone()
        if row:
            print(f"\nAAPL quality_metrics row found:")
            print(json.dumps({
                'symbol': row[0],
                'roe': row[1],
                'roe_unavailable_reason': row[2],
                'roa': row[3],
                'roa_unavailable_reason': row[4],
                'operating_margin': row[5],
                'operating_margin_unavailable_reason': row[6],
                'debt_to_equity': row[7],
                'debt_to_equity_unavailable_reason': row[8],
                'data_unavailable': row[9],
            }, indent=2, default=str))
        else:
            print("\nNo AAPL row in quality_metrics")

        # Sample value_metrics for AAPL
        print("\n" + "-"*70)
        print("SAMPLE: Value metrics for AAPL")
        print("-"*70)
        cur.execute("""
            SELECT
                symbol,
                pe_ratio,
                pe_ratio_unavailable_reason,
                pb_ratio,
                pb_ratio_unavailable_reason,
                ps_ratio,
                ps_ratio_unavailable_reason,
                peg_ratio,
                peg_ratio_unavailable_reason,
                ev_ebitda,
                ev_ebitda_unavailable_reason,
                dividend_yield,
                dividend_yield_unavailable_reason,
                data_unavailable
            FROM value_metrics
            WHERE symbol = 'AAPL'
        """)
        row = cur.fetchone()
        if row:
            print(f"\nAAPL value_metrics row found:")
            print(json.dumps({
                'symbol': row[0],
                'pe_ratio': row[1],
                'pe_ratio_unavailable_reason': row[2],
                'pb_ratio': row[3],
                'pb_ratio_unavailable_reason': row[4],
                'ps_ratio': row[5],
                'ps_ratio_unavailable_reason': row[6],
                'peg_ratio': row[7],
                'peg_ratio_unavailable_reason': row[8],
                'ev_ebitda': row[9],
                'ev_ebitda_unavailable_reason': row[10],
                'dividend_yield': row[11],
                'dividend_yield_unavailable_reason': row[12],
                'data_unavailable': row[13],
            }, indent=2, default=str))
        else:
            print("\nNo AAPL row in value_metrics")


if __name__ == "__main__":
    try:
        check_db_data()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
