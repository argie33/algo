#!/usr/bin/env python3
"""
Check data loading health - verify all metric tables are fresh and complete.

This tool audits:
1. When each metric table was last updated
2. Coverage % (how many non-unavailable rows)
3. Data completeness by symbol count
4. Alerts if any metric is stale (>30 days) or coverage drops
"""

import sys
sys.path.insert(0, '.')

from datetime import datetime, timezone, timedelta
from utils.db.context import DatabaseContext
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_metric_freshness():
    """Check when each metric table was last updated."""

    tables = [
        ('quality_metrics', 'Quality'),
        ('growth_metrics', 'Growth'),
        ('value_metrics', 'Value'),
        ('positioning_metrics', 'Positioning'),
        ('stability_metrics', 'Stability'),
        ('momentum_metrics', 'Momentum'),
    ]

    print("\n" + "=" * 80)
    print("DATA LOADING HEALTH CHECK")
    print("=" * 80)

    with DatabaseContext("read") as cur:
        for table_name, label in tables:
            # Get freshness and coverage
            cur.execute(f"""
                SELECT
                    MAX(updated_at) as last_updated,
                    COUNT(*) as total_count,
                    COUNT(*) FILTER (WHERE data_unavailable = FALSE OR data_unavailable IS NULL) as available_count
                FROM {table_name}
            """)

            last_updated, total, available = cur.fetchone()

            if last_updated is None:
                status = "EMPTY"
                age_text = "Never"
                coverage = 0
            else:
                # Calculate age
                now = datetime.now(timezone.utc)
                if last_updated.tzinfo is None:
                    # Convert naive timestamp to aware
                    from utils.db.timezone_utils import get_db_timezone
                    tz = get_db_timezone()
                    last_updated = last_updated.replace(tzinfo=tz)

                age = (now - last_updated).total_seconds() / 86400
                coverage = 100 * available / total if total > 0 else 0

                if age < 1:
                    status = "FRESH"
                    age_text = f"{age*24:.1f}h ago"
                elif age < 3:
                    status = "OK"
                    age_text = f"{age:.1f}d ago"
                elif age < 7:
                    status = "STALE"
                    age_text = f"{age:.1f}d ago"
                    logger.warning(f"{label}: Data is {age:.1f} days old (threshold: 7 days)")
                else:
                    status = "CRITICAL"
                    age_text = f"{age:.1f}d ago"
                    logger.error(f"{label}: Data is {age:.1f} days old - NEEDS UPDATE")

            # Color-coded output
            print(f"\n{label:15} {status:10} | Updated: {age_text:12} | Coverage: {coverage:5.1f}% ({available}/{total})")

def check_score_completeness():
    """Check overall stock scores completeness."""

    print("\n" + "=" * 80)
    print("STOCK SCORES COMPLETENESS")
    print("=" * 80)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total_scores,
                COUNT(*) FILTER (WHERE data_unavailable = FALSE OR data_unavailable IS NULL) as available_scores,
                AVG(data_completeness) as avg_completeness,
                COUNT(*) FILTER (WHERE data_completeness >= 70) as scores_at_trading_gate,
                COUNT(*) FILTER (WHERE composite_score IS NULL) as null_composite
            FROM stock_scores
        """)

        total, available, avg_complete, trading_ready, null_composite = cur.fetchone()

        print(f"\nTotal scores: {total}")
        print(f"Available (data_unavailable=FALSE): {available} ({100*available/total:.1f}%)")
        print(f"Null composite scores: {null_composite}")
        print(f"Average completeness: {avg_complete:.1f}%")
        print(f"Scores >= 70% complete (trading gate): {trading_ready} ({100*trading_ready/total:.1f}%)")

def check_individual_factors():
    """Check completeness of individual factor scores."""

    print("\n" + "=" * 80)
    print("INDIVIDUAL FACTOR COMPLETENESS")
    print("=" * 80)

    factors = [
        ('quality_score', 'Quality'),
        ('growth_score', 'Growth'),
        ('value_score', 'Value'),
        ('positioning_score', 'Positioning'),
        ('stability_score', 'Stability'),
        ('momentum_score', 'Momentum'),
    ]

    with DatabaseContext("read") as cur:
        for col_name, label in factors:
            cur.execute(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE {col_name} IS NOT NULL) as has_value,
                    COUNT(*) FILTER (WHERE {col_name} IS NULL) as is_null
                FROM stock_scores
            """)

            total, has_value, is_null = cur.fetchone()
            pct = 100 * has_value / total if total > 0 else 0

            print(f"{label:15} {has_value:6}/{total:6} ({pct:5.1f}%) - {is_null:6} null")

def main():
    print("\n[*] Analyzing data loading health...\n")

    try:
        check_metric_freshness()
        check_score_completeness()
        check_individual_factors()

        print("\n" + "=" * 80)
        print("[OK] Data loading audit complete")
        print("=" * 80 + "\n")

    except Exception as e:
        logger.error(f"Audit failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
