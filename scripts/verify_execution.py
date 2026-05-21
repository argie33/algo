#!/usr/bin/env python3
"""Verify orchestrator execution: check RDS signals and Alpaca trades."""

import json
import os
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    import alpaca_trade_api as tradeapi
except ImportError:
    print("Warning: alpaca_trade_api not installed")


def get_rds_connection():
    """Get RDS connection from environment or Secrets Manager."""
    host = os.getenv("RDS_HOST") or os.getenv("DB_HOST")
    port = os.getenv("RDS_PORT", "5432")
    database = os.getenv("RDS_DATABASE", "algo")
    user = os.getenv("RDS_USER", "admin")
    password = os.getenv("RDS_PASSWORD")

    if not all([host, user, password]):
        print("ERROR: Missing RDS credentials")
        return None

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            connect_timeout=5
        )
        return conn
    except Exception as e:
        print(f"ERROR: Failed to connect to RDS: {e}")
        return None


def verify_signals(conn):
    """Query RDS for signals in buy_sell_daily table."""
    if not conn:
        print("\n❌ RDS Verification: Cannot connect")
        return {}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check total signals today
            cur.execute("""
                SELECT
                    COUNT(*) as total_signals,
                    COUNT(CASE WHEN signal_type = 'BUY' THEN 1 END) as buy_signals,
                    COUNT(CASE WHEN signal_type = 'SELL' THEN 1 END) as sell_signals,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    MAX(created_at) as latest_signal
                FROM buy_sell_daily
                WHERE DATE(created_at) = CURRENT_DATE
            """)
            result = cur.fetchone()

            if result and result['total_signals'] > 0:
                print(f"\n✅ RDS Signals (Today)")
                print(f"   Total: {result['total_signals']}")
                print(f"   Buy: {result['buy_signals']}, Sell: {result['sell_signals']}")
                print(f"   Symbols: {result['unique_symbols']}")
                print(f"   Latest: {result['latest_signal']}")

                # Show sample signals
                cur.execute("""
                    SELECT symbol, signal_type, price, created_at
                    FROM buy_sell_daily
                    WHERE DATE(created_at) = CURRENT_DATE
                    ORDER BY created_at DESC
                    LIMIT 5
                """)
                print(f"\n   Recent signals:")
                for row in cur.fetchall():
                    print(f"      {row['symbol']}: {row['signal_type']} @ ${row['price']:.2f} ({row['created_at']})")

                return {
                    'total': result['total_signals'],
                    'buy': result['buy_signals'],
                    'sell': result['sell_signals'],
                    'symbols': result['unique_symbols']
                }
            else:
                print(f"\n⚠️  RDS Signals: No signals found today")
                return {}
    except Exception as e:
        print(f"\n❌ RDS Query Error: {e}")
        return {}


def verify_alpaca_trades():
    """Check Alpaca account for executed trades."""
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    base_url = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

    if not all([api_key, secret_key]):
        print("\n⚠️  Alpaca Verification: API keys not configured")
        return {}

    try:
        api = tradeapi.REST(api_key, secret_key, base_url)

        # Get account info
        account = api.get_account()
        orders = api.list_orders(status='closed', limit=10)

        print(f"\n✅ Alpaca Account")
        print(f"   Status: {account.status}")
        print(f"   Buying Power: ${account.buying_power:.2f}")
        print(f"   Portfolio Value: ${account.portfolio_value:.2f}")
        print(f"   PnL: ${account.portfolio_value - account.cash:.2f}")

        if orders:
            print(f"\n   Recent Orders ({len(orders)}):")
            for order in orders[:5]:
                print(f"      {order.symbol}: {order.side.upper()} {order.qty} @ ${order.filled_avg_price:.2f} ({order.filled_at})")
            return {'account_status': account.status, 'order_count': len(orders)}
        else:
            print(f"\n   No closed orders found")
            return {'account_status': account.status, 'order_count': 0}

    except Exception as e:
        print(f"\n❌ Alpaca Error: {e}")
        return {}


def main():
    """Run all verification checks."""
    print("=" * 60)
    print(f"EXECUTION VERIFICATION — {datetime.now().isoformat()}")
    print("=" * 60)

    # Verify RDS signals
    conn = get_rds_connection()
    signals = verify_signals(conn)
    if conn:
        conn.close()

    # Verify Alpaca trades
    trades = verify_alpaca_trades()

    # Summary
    print("\n" + "=" * 60)
    if signals.get('total', 0) > 0 and trades.get('order_count', 0) > 0:
        print("✅ END-TO-END SUCCESS: Signals generated and trades executed")
        return 0
    elif signals.get('total', 0) > 0:
        print("⚠️  Signals generated but no trades yet (check Alpaca execution)")
        return 0
    else:
        print("❌ No signals generated (check orchestrator execution)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
