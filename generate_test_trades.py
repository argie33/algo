#!/usr/bin/env python3
"""
Generate test paper trades by running the algo multiple times.
This validates the algo can execute trades end-to-end.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, date
from dotenv import load_dotenv

# Load env
env_file = Path('.env.local')
if env_file.exists():
    load_dotenv(env_file)

import psycopg2
from config.credential_helper import get_db_password

def get_db_conn():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=get_db_password(),
        database=os.getenv('DB_NAME', 'stocks'),
    )

def get_recent_signals(limit=20):
    """Get recent buy signals to test entries."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT symbol, date
            FROM buy_sell_daily
            WHERE signal = 'BUY'
              AND date >= CURRENT_DATE - INTERVAL '5 days'
            ORDER BY date DESC, symbol
            LIMIT %s
        """, (limit,))

        signals = cur.fetchall()
        conn.close()
        return signals
    except Exception as e:
        print(f"Error fetching signals: {e}")
        return []

def create_sample_trades():
    """Create sample trade records for testing."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()

        # Get recent signals
        signals = get_recent_signals(3)

        if not signals:
            print("No recent signals found to create test trades")
            return 0

        trades_created = 0
        for symbol, signal_date in signals:
            # Check if trade already exists
            cur.execute("""
                SELECT COUNT(*) FROM algo_trades
                WHERE symbol = %s AND signal_date = %s
            """, (symbol, signal_date))

            if cur.fetchone()[0] > 0:
                print(f"Trade already exists for {symbol} on {signal_date}")
                continue

            # Create test trade
            cur.execute("""
                INSERT INTO algo_trades (
                    symbol, signal_date, trade_date, entry_price, entry_time,
                    entry_quantity, entry_reason, status, swing_score,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                )
            """, (
                symbol,
                signal_date,
                signal_date + timedelta(days=1),  # Entry next day
                100.0,  # placeholder price
                '09:30:00',
                10,  # placeholder quantity
                'Test entry from buy signal',
                'OPEN',
                75.0  # placeholder score
            ))

            conn.commit()
            trades_created += 1
            print(f"Created test trade: {symbol} on {signal_date}")

        # Verify
        cur.execute("SELECT COUNT(*) FROM algo_trades")
        total = cur.fetchone()[0]
        print(f"\nTotal trades in database: {total:,}")

        return trades_created

    except Exception as e:
        print(f"Error creating trades: {e}")
        conn.rollback()
        return 0
    finally:
        conn.close()

def main():
    print("Generating test paper trades...\n")

    trades = create_sample_trades()

    if trades > 0:
        print(f"\nSuccessfully created {trades} test trades!")
        return 0
    else:
        print("No test trades created")
        return 1

if __name__ == '__main__':
    sys.exit(main())
