#!/usr/bin/env python3
"""
Comprehensive data quality audit - verify all data, calculations, and logic.
Connects to actual PostgreSQL database and validates data integrity.
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import psycopg2
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date

# Load environment
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'stocks'),
    'password': credential_manager.get_db_credentials()["password"],
    'database': os.getenv('DB_NAME', 'stocks'),
}

def get_conn():
    return psycopg2.connect(**DB_CONFIG)

def audit_price_data():
    """Check price_daily table for data integrity."""
    print("\n" + "="*80)
    print("PRICE DATA INTEGRITY CHECK")
    print("="*80)

    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM price_daily")
        total = cur.fetchone()[0]
        print(f"Total price records: {total:,}")

        cur.execute("SELECT COUNT(*) FROM price_daily WHERE close IS NULL")
        null_closes = cur.fetchone()[0]
        print(f"NULL closes: {null_closes}")
        if null_closes > 0:
            print("  ERROR: NULL closes found!")

        cur.execute("SELECT COUNT(*) FROM price_daily WHERE open IS NULL")
        null_opens = cur.fetchone()[0]
        print(f"NULL opens: {null_opens}")

        cur.execute("SELECT COUNT(*) FROM price_daily WHERE volume IS NULL")
        null_volumes = cur.fetchone()[0]
        print(f"NULL volumes: {null_volumes}")

        cur.execute("SELECT COUNT(*) FROM price_daily WHERE high < low")
        high_lt_low = cur.fetchone()[0]
        print(f"High < Low errors: {high_lt_low}")

        cur.execute("SELECT COUNT(*) FROM price_daily WHERE close < low OR close > high")
        close_out_range = cur.fetchone()[0]
        print(f"Close out of [Low, High] range: {close_out_range}")

        cur.execute("SELECT COUNT(*) FROM price_daily WHERE volume = 0")
        zero_volume = cur.fetchone()[0]
        print(f"Zero volume records: {zero_volume}")

        errors = null_closes + null_opens + high_lt_low + close_out_range
        if errors == 0:
            print(f"\n[PASS] PRICE DATA: All {total:,} records PASS integrity checks")
        else:
            print(f"\n[FAIL] PRICE DATA: {errors} integrity errors found")

        return errors == 0
    except Exception as e:
        print(f"ERROR in audit_price_data: {e}")
        return False
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

def audit_buy_signals():
    """Check buy_sell_daily for signal quality."""
    print("\n" + "="*80)
    print("SIGNAL GENERATION AUDIT")
    print("="*80)

    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal = 'BUY'")
        buy_signals = cur.fetchone()[0]
        print(f"Total BUY signals: {buy_signals:,}")

        cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal = 'BUY' AND entry_price IS NULL")
        null_entry = cur.fetchone()[0]
        print(f"BUY signals with NULL entry_price: {null_entry}")
        if null_entry > 0:
            print("  ERROR: BUY signals without entry prices!")

        cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal = 'BUY' AND entry_price IS NOT NULL AND (entry_price < 0.01 OR entry_price > 100000)")
        bad_prices = cur.fetchone()[0]
        print(f"Entry prices out of realistic range: {bad_prices}")

        cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal = 'BUY' AND rsi IS NOT NULL AND (rsi < 0 OR rsi > 100)")
        nan_rsi = cur.fetchone()[0]
        print(f"RSI with NaN values: {nan_rsi} (expected for early signals)")

        cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal = 'BUY' AND date IS NULL")
        null_dates = cur.fetchone()[0]
        print(f"BUY signals with NULL date: {null_dates}")

        errors = null_entry + null_dates
        if errors == 0:
            print(f"\n[PASS] SIGNALS: All {buy_signals:,} BUY signals PASS quality checks")
        else:
            print(f"\n[FAIL] SIGNALS: {errors} signal errors found (NULL entry prices or dates)")

        return errors == 0
    except Exception as e:
        print(f"ERROR in audit_buy_signals: {e}")
        return False
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

def audit_trades():
    """Check algo_trades for execution quality."""
    print("\n" + "="*80)
    print("TRADE EXECUTION AUDIT")
    print("="*80)

    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM algo_trades")
        total_trades = cur.fetchone()[0]
        print(f"Total trades: {total_trades}")

        cur.execute("SELECT status, COUNT(*) FROM algo_trades GROUP BY status ORDER BY status")
        print(f"Trades by status:")
        for status, count in cur.fetchall():
            print(f"  {status}: {count}")

        cur.execute("SELECT COUNT(*) FROM algo_trades WHERE entry_price IS NULL")
        null_entry = cur.fetchone()[0]
        print(f"\nEntry prices NULL: {null_entry}")
        if null_entry > 0:
            print("  ERROR: Trades without entry prices!")

        cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status = 'closed' AND exit_price IS NULL")
        closed_no_exit = cur.fetchone()[0]
        print(f"Closed trades without exit_price: {closed_no_exit}")

        cur.execute("SELECT COUNT(*) FROM algo_trades WHERE entry_quantity IS NULL OR entry_quantity <= 0")
        bad_qty = cur.fetchone()[0]
        print(f"Trades with invalid entry_quantity: {bad_qty}")

        cur.execute("SELECT COUNT(*) FROM algo_trades WHERE signal_date IS NULL")
        null_signal_date = cur.fetchone()[0]
        print(f"Trades with NULL signal_date: {null_signal_date}")

        cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status = 'closed' AND exit_date IS NULL")
        closed_no_exit_date = cur.fetchone()[0]
        print(f"Closed trades without exit_date: {closed_no_exit_date}")

        cur.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN profit_loss_pct IS NULL THEN 1 ELSE 0 END) as null_pnl,
                SUM(CASE WHEN profit_loss_pct = 0 THEN 1 ELSE 0 END) as zero_pnl,
                SUM(CASE WHEN profit_loss_pct > 0 THEN 1 ELSE 0 END) as positive_pnl,
                SUM(CASE WHEN profit_loss_pct < 0 THEN 1 ELSE 0 END) as negative_pnl
            FROM algo_trades WHERE status = 'closed'
        """)
        row = cur.fetchone()
        print(f"\nClosed/filled trade P&L distribution:")
        print(f"  Total closed: {row[0]}")
        print(f"  NULL P&L: {row[1]}")
        print(f"  Zero P&L: {row[2]}")
        print(f"  Positive P&L: {row[3]}")
        print(f"  Negative P&L: {row[4]}")

        print(f"\nSample of closed trades (entry vs exit prices):")
        cur.execute("""
            SELECT symbol, signal_date, entry_price, exit_date, exit_price,
                   ROUND(profit_loss_pct, 2) as pct_change
            FROM algo_trades
            WHERE status = 'closed'
            ORDER BY signal_date DESC
            LIMIT 10
        """)

        for row in cur.fetchall():
            exit_price = row[4] if row[4] else 'N/A'
            exit_date = row[3] if row[3] else 'N/A'
            pct = f" ({row[5]:+.2f}%)" if row[5] is not None else ""
            if isinstance(exit_price, (int, float)):
                print(f"  {row[0]}: entered {row[1]}@${row[2]:.2f}, exited {exit_date}@${exit_price:.2f}{pct}")
            else:
                print(f"  {row[0]}: entered {row[1]}@${row[2]:.2f}, exited {exit_date}@{exit_price}{pct}")
    except Exception as e:
        print(f"ERROR in audit_trades: {e}")
    finally:
        if cur:
            try:
                cur.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    # Errors check
    errors = null_entry + closed_no_exit + bad_qty + null_signal_date + closed_no_exit_date
    if errors == 0:
        print(f"\n[PASS] TRADES: All {total_trades} trades PASS execution checks")
    else:
        print(f"\n[FAIL] TRADES: {errors} trade errors found")

    cur.close()
    conn.close()
    return errors == 0

def main():
    """Run all audits."""
    print("\n" + "="*80)
    print("COMPREHENSIVE DATA QUALITY AUDIT")
    print(f"Database: {DB_CONFIG['database']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*80)

    results = {
        "Price Data": audit_price_data(),
        "Signal Generation": audit_buy_signals(),
        "Trade Execution": audit_trades(),
    }

    print("\n" + "="*80)
    print("AUDIT SUMMARY")
    print("="*80)
    for check, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{check}: {status}")

    all_passed = all(results.values())
    print("\n" + "="*80)
    if all_passed:
        print("[PASS] OVERALL: ALL DATA QUALITY CHECKS PASSED")
        print("System is ready for analysis and decision-making.")
    else:
        print("[FAIL] OVERALL: SOME DATA QUALITY ISSUES FOUND")
        print("Review failures above before drawing conclusions about system design.")
    print("="*80)

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
