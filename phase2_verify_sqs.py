#!/usr/bin/env python3
"""
Phase 2 Verification & Completion: SQS Backfill Status & Regeneration

1. Verify trend_template_data backfill completed
2. Check signal_quality_scores current state
3. Run load_algo_metrics_daily to regenerate SQS
4. Report final status
"""

import os
import sys
import psycopg2
import psycopg2.extras
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def get_db_config():
    """Get database configuration from environment."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
        "database": os.getenv("DB_NAME", "stocks"),
    }

def check_backfill_status():
    """Check if trend_template_data backfill is complete."""
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        print("\n" + "="*70)
        print("PHASE 2: SQS BACKFILL VERIFICATION")
        print("="*70 + "\n")

        # Check trend_template_data
        print("1. Checking trend_template_data (should be populated by backfill_trend_sql.py)")
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT date), COUNT(DISTINCT symbol) FROM trend_template_data")
        total, dates, symbols = cur.fetchone()
        print(f"   Total rows: {total:,}")
        print(f"   Unique dates: {dates}")
        print(f"   Unique symbols: {symbols}")

        if total < 100000:
            print("   ⚠️  WARNING: Backfill may be incomplete (expected 1M+ rows)")
            print("   → Run: python3 backfill_trend_sql.py")
        else:
            print("   ✓ Backfill appears complete")

        # Check signal_quality_scores
        print("\n2. Checking signal_quality_scores (before regeneration)")
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT date) FROM signal_quality_scores")
        sqs_rows, sqs_dates = cur.fetchone()
        print(f"   Current SQS rows: {sqs_rows:,}")
        print(f"   Coverage: {sqs_dates} dates")

        # Check buy_sell_daily for expected range
        cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM buy_sell_daily")
        signals_total, min_date, max_date = cur.fetchone()
        print(f"   Expected SQS rows: {signals_total:,} (one per signal)")
        print(f"   Signal date range: {min_date} to {max_date}")

        if sqs_rows < signals_total * 0.5:
            print(f"   ⚠️  MAJOR GAP: Only {sqs_rows:,}/{signals_total:,} rows ({100*sqs_rows/signals_total:.1f}%)")
            print("   → Need to run: python3 load_algo_metrics_daily.py")
        else:
            print("   ✓ SQS coverage looks reasonable")

        cur.close()
        conn.close()

        return total > 100000  # Return True if backfill appears complete

    except Exception as e:
        print(f"ERROR: {e}")
        return False

def run_metrics_regeneration():
    """Run load_algo_metrics_daily to regenerate SQS."""
    print("\n3. Regenerating Signal Quality Scores...")
    print("   Running: python3 load_algo_metrics_daily.py")

    # Import and run the metrics loader
    try:
        from load_algo_metrics_daily import AlgoMetricsLoader
        loader = AlgoMetricsLoader()
        loader.run_all()
        print("   ✓ Metrics regeneration complete")
        return True
    except Exception as e:
        print(f"   ERROR: {e}")
        print("   → Try running manually: python3 load_algo_metrics_daily.py")
        return False

def verify_final_state():
    """Verify final SQS state after regeneration."""
    try:
        conn = psycopg2.connect(**get_db_config())
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        print("\n4. Verifying final state...")

        # Final SQS count
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT date) FROM signal_quality_scores")
        sqs_rows, sqs_dates = cur.fetchone()

        # Expected signal count
        cur.execute("SELECT COUNT(*) FROM buy_sell_daily")
        signal_count = cur.fetchone()[0]

        coverage_pct = 100 * sqs_rows / signal_count if signal_count > 0 else 0

        print(f"   Signal Quality Scores: {sqs_rows:,} rows ({coverage_pct:.1f}% coverage)")
        print(f"   Expected: {signal_count:,} rows (one per signal)")

        if coverage_pct >= 90:
            print(f"   ✅ SQS REGENERATION SUCCESSFUL!")
            print(f"\n   STATUS: Phase 2 COMPLETE")
            return True
        else:
            print(f"   ⚠️  Coverage still low ({coverage_pct:.1f}%)")
            return False

    except Exception as e:
        print(f"   ERROR: {e}")
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    print("\n🔍 PHASE 2: SQS BACKFILL & METRICS REGENERATION")
    print("="*70)

    # Step 1: Check backfill status
    backfill_complete = check_backfill_status()

    if not backfill_complete:
        print("\n⚠️  BACKFILL INCOMPLETE")
        print("   Please run: python3 backfill_trend_sql.py")
        print("   Then run: python3 phase2_verify_sqs.py again")
        sys.exit(1)

    # Step 2: Run metrics regeneration
    regen_ok = run_metrics_regeneration()

    # Step 3: Verify final state
    success = verify_final_state()

    if success:
        print("\n" + "="*70)
        print("✅ PHASE 2 COMPLETE - Ready to move to Phase 3")
        print("="*70)
        sys.exit(0)
    else:
        print("\n" + "="*70)
        print("⚠️  PHASE 2 INCOMPLETE - Check errors above")
        print("="*70)
        sys.exit(1)
