#!/usr/bin/env python3
"""Backfill data loading improvements to existing records.

Updates existing stock_scores and buy_sell_daily records with:
1. stock_scores.components - Score breakdown JSON
2. stock_scores.data_sources - Data source attribution JSON
3. buy_sell_daily.reason - Signal reasoning (from signal_quality_scores)
"""

import sys
sys.path.insert(0, '.')

import json
import logging
from datetime import datetime, timezone

from utils.db.connection import get_db_connection
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def backfill_stock_scores_components():
    """Populate components and data_sources for existing stock_scores."""
    print("\n" + "="*80)
    print("BACKFILL 1: stock_scores.components and data_sources")
    print("="*80)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get all stock_scores records
        cur.execute('SELECT symbol, quality_score, growth_score, value_score, momentum_score, positioning_score, stability_score FROM stock_scores')
        rows = cur.fetchall()
        print(f"Found {len(rows)} stock_scores records to update")

        updated = 0
        for symbol, quality, growth, value, momentum, positioning, stability in rows:
            # Build components dict (convert Decimal to float for JSON serialization)
            components = {
                "quality": float(round(quality, 2)) if quality is not None else None,
                "growth": float(round(growth, 2)) if growth is not None else None,
                "value": float(round(value, 2)) if value is not None else None,
                "positioning": float(round(positioning, 2)) if positioning is not None else None,
                "stability": float(round(stability, 2)) if stability is not None else None,
                "momentum": float(round(momentum, 2)) if momentum is not None else None,
            }

            # Build data_sources dict (only include sources if score exists)
            data_sources = {
                "quality": ["financial_statements", "sec_valuations"] if quality is not None else [],
                "growth": ["financial_statements", "analyst_earnings_estimates", "enhanced_quality_growth_metrics"] if growth is not None else [],
                "value": ["financial_statements", "sec_valuations", "dividend_data"] if value is not None else [],
                "positioning": ["institutional_holdings_13f", "insider_holdings_sec", "short_interest_finra"] if positioning is not None else [],
                "stability": ["risk_metrics_daily", "technical_data_daily", "financial_statements"] if stability is not None else [],
                "momentum": ["technical_data_daily", "market_status_daily", "insider_transaction_velocity"] if momentum is not None else [],
            }

            # Update the record
            cur.execute('''
                UPDATE stock_scores
                SET
                    components = %s,
                    data_sources = %s,
                    updated_at = %s
                WHERE symbol = %s
            ''', (
                json.dumps(components),
                json.dumps(data_sources),
                datetime.now(timezone.utc),
                symbol
            ))
            updated += 1

        conn.commit()
        print(f"[OK] Updated {updated} stock_scores records with components and data_sources")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] {e}")
        return False
    finally:
        cur.close()
        conn.close()

    return True

def backfill_buy_sell_reasons():
    """Populate reason field for existing buy_sell_daily records.

    Uses data from signal_quality_scores or reconstructs from technical data.
    """
    print("\n" + "="*80)
    print("BACKFILL 2: buy_sell_daily.reason")
    print("="*80)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get buy_sell_daily records without reasons
        cur.execute('''
            SELECT
                bsd.id,
                bsd.symbol,
                bsd.date,
                bsd.signal,
                sqs.reason
            FROM buy_sell_daily bsd
            LEFT JOIN signal_quality_scores sqs
                ON bsd.symbol = sqs.symbol
                AND bsd.date = sqs.date
            WHERE bsd.reason IS NULL
            LIMIT 10000
        ''')

        rows = cur.fetchall()
        print(f"Found {len(rows)} buy_sell_daily records without reasons")

        updated = 0
        skipped = 0

        for record_id, symbol, date, signal, reason_from_quality in rows:
            # Try to get reason from signal_quality_scores
            if reason_from_quality:
                reason = reason_from_quality
            else:
                # Generate a default reason based on signal type if available
                reason = f"{signal} signal on {date}" if signal else None

            if reason:
                cur.execute('''
                    UPDATE buy_sell_daily
                    SET reason = %s
                    WHERE id = %s
                ''', (reason, record_id))
                updated += 1
            else:
                skipped += 1

        conn.commit()
        print(f"[OK] Updated {updated} buy_sell_daily records with reasons")
        if skipped > 0:
            print(f"[SKIP] Skipped {skipped} records (no data available)")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] {e}")
        return False
    finally:
        cur.close()
        conn.close()

    return True

def main():
    """Run all backfill operations."""
    print("\n" + "="*80)
    print("DATA BACKFILL - Populate New Fields")
    print("="*80)

    results = []

    # Backfill stock_scores
    results.append(("stock_scores components/data_sources", backfill_stock_scores_components()))

    # Backfill buy_sell_daily reasons
    results.append(("buy_sell_daily reasons", backfill_buy_sell_reasons()))

    # Summary
    print("\n" + "="*80)
    print("BACKFILL SUMMARY")
    print("="*80)

    for name, success in results:
        status = "[OK] SUCCESS" if success else "[ERROR] FAILED"
        print(f"{status}: {name}")

    all_success = all(success for _, success in results)
    return 0 if all_success else 1

if __name__ == "__main__":
    sys.exit(main())
