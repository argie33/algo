#!/usr/bin/env python3
"""Diagnostic script to understand positions data inconsistency.

Checks:
1. What's in algo_positions table (DB state)
2. What's in algo_trades (entry source of truth)
3. What's in Alpaca (actual positions)
4. What the positions view returns
5. What the API returns to dashboard
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def diagnose():
    """Run comprehensive diagnostic."""
    import psycopg2.extras
    with DatabaseContext() as db:
        cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        print("\n" + "=" * 80)
        print("POSITIONS DIAGNOSTIC REPORT")
        print("=" * 80)

        # 1. Check algo_positions table directly
        print("\n[1] ALGO_POSITIONS TABLE (raw data)")
        print("-" * 80)
        cur.execute("""
            SELECT
                id, position_id, symbol, quantity, status, created_at, updated_at,
                avg_entry_price, current_price, position_value,
                stop_loss_price, current_stop_price, unrealized_pnl
            FROM algo_positions
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        if rows:
            print(f"Total rows: {len(rows)}")
            for row in rows:
                print(f"  {row['symbol']:6} | qty={row['quantity']:8.2f} | status={row['status']:8} | "
                      f"entry=${row['avg_entry_price']:10.2f} | current=${row['current_price']:10.2f} | "
                      f"value=${row['position_value']:12.2f} | stop=${row['stop_loss_price']}")
        else:
            print("❌ NO ROWS IN algo_positions")

        # 2. Count by status
        print("\n[2] POSITION COUNT BY STATUS")
        print("-" * 80)
        cur.execute("""
            SELECT status, COUNT(*) as count, SUM(position_value) as total_value
            FROM algo_positions
            GROUP BY status
            ORDER BY status
        """)
        for row in cur.fetchall():
            print(f"  {row['status']:10} : {row['count']:3} positions, ${row['total_value']:12.2f} total value")

        # 3. Check algo_trades (entry source of truth)
        print("\n[3] ALGO_TRADES TABLE (open trades)")
        print("-" * 80)
        cur.execute("""
            SELECT
                trade_id, symbol, status, entry_price, entry_quantity,
                entry_date, trade_date, created_at
            FROM algo_trades
            WHERE status IN ('open', 'filled', 'active')
            ORDER BY trade_date DESC
        """)
        trades = cur.fetchall()
        if trades:
            print(f"Total open trades: {len(trades)}")
            for row in trades:
                print(f"  {row['symbol']:6} | qty={row['entry_quantity']:8.2f} | status={row['status']:10} | "
                      f"entry=${row['entry_price']:10.2f} | date={row['trade_date']}")
        else:
            print("❌ NO OPEN TRADES IN algo_trades")

        # 4. Check algo_positions_with_risk view
        print("\n[4] ALGO_POSITIONS_WITH_RISK VIEW (computed view)")
        print("-" * 80)
        try:
            cur.execute("""
                SELECT symbol, quantity, avg_entry_price, current_price,
                       position_value, status, sector, stop_loss_price
                FROM algo_positions_with_risk
                ORDER BY position_value DESC
            """)
            view_rows = cur.fetchall()
            if view_rows:
                print(f"Total rows from view: {len(view_rows)}")
                for row in view_rows:
                    print(f"  {row['symbol']:6} | qty={row['quantity']:8.2f} | value=${row['position_value']:12.2f} | "
                          f"sector={row['sector']:20} | stop=${row['stop_loss_price']}")
            else:
                print("❌ NO ROWS FROM algo_positions_with_risk VIEW")
        except Exception as e:
            print(f"❌ ERROR QUERYING VIEW: {e}")

        # 5. Check price_daily data (required for view join)
        print("\n[5] PRICE_DAILY TABLE (required for view)")
        print("-" * 80)
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) as unique_symbols,
                   COUNT(*) as total_rows,
                   MAX(date) as latest_date
            FROM price_daily
        """)
        row = cur.fetchall()[0]
        print(f"  Unique symbols: {row['unique_symbols']}")
        print(f"  Total rows: {row['total_rows']}")
        print(f"  Latest date: {row['latest_date']}")

        # 6. Check if position symbols have price data
        print("\n[6] POSITIONS WITHOUT PRICE DATA")
        print("-" * 80)
        cur.execute("""
            SELECT DISTINCT ap.symbol
            FROM algo_positions ap
            WHERE status = 'open'
              AND NOT EXISTS (
                SELECT 1 FROM price_daily pd WHERE pd.symbol = ap.symbol
              )
        """)
        missing_prices = [row['symbol'] for row in cur.fetchall()]
        if missing_prices:
            print(f"❌ {len(missing_prices)} positions missing price data:")
            for symbol in missing_prices:
                print(f"     {symbol}")
        else:
            print("OK: All open positions have price data")

        # 7. Check company_profile data (used for sector enrichment)
        print("\n[7] COMPANY PROFILE COVERAGE")
        print("-" * 80)
        cur.execute("""
            SELECT COUNT(DISTINCT ticker) as total_companies,
                   COUNT(DISTINCT CASE WHEN sector IS NOT NULL THEN ticker END) as with_sector
            FROM company_profile
        """)
        row = cur.fetchall()[0]
        print(f"  Total companies: {row['total_companies']}")
        print(f"  With sector: {row['with_sector']}")

        # 8. Check positions missing sector data
        print("\n[8] POSITIONS WITH MISSING SECTOR DATA")
        print("-" * 80)
        cur.execute("""
            SELECT ap.symbol, ap.position_value
            FROM algo_positions ap
            WHERE ap.status = 'open'
              AND NOT EXISTS (
                SELECT 1 FROM company_profile cp WHERE cp.ticker = ap.symbol AND cp.sector IS NOT NULL
              )
              AND NOT EXISTS (
                SELECT 1 FROM algo_trades t WHERE t.symbol = ap.symbol AND t.sector IS NOT NULL
              )
        """)
        no_sector = cur.fetchall()
        if no_sector:
            print(f"❌ {len(no_sector)} positions missing sector data:")
            for row in no_sector:
                print(f"     {row['symbol']} (value=${row['position_value']:.2f})")
        else:
            print("OK: All open positions have sector data")

        # 9. Try Alpaca sync check
        print("\n[9] ALPACA INTEGRATION CHECK")
        print("-" * 80)
        try:
            from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager
            from config.config_loader import ConfigLoader

            config = ConfigLoader.load()
            sync = AlpacaSyncManager(config)

            try:
                account = sync.fetch_alpaca_account()
                print("✓ Alpaca account accessible")
                print(f"  Portfolio value: ${account.get('portfolio_value', 'N/A')}")
                print(f"  Buying power: ${account.get('buying_power', 'N/A')}")
                print(f"  Cash: ${account.get('cash', 'N/A')}")

                # Get live positions from Alpaca
                import requests
                url = f"{sync.alpaca_base_url}/v2/positions"
                headers = {
                    "APCA-API-KEY-ID": sync.alpaca_key,
                    "APCA-API-SECRET-KEY": sync.alpaca_secret,
                    "Accept": "application/json",
                }
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                alpaca_positions = response.json()

                print(f"\n  Alpaca has {len(alpaca_positions)} open positions:")
                for pos in alpaca_positions:
                    print(f"    {pos['symbol']:6} | qty={pos['qty']:8.2f} | entry=${pos['avg_entry_price']:10.2f} | "
                          f"current=${pos['current_price']:10.2f} | value=${float(pos['qty'])*float(pos['current_price']):12.2f}")

                # Check for sync issues
                alpaca_symbols = {pos['symbol'] for pos in alpaca_positions}
                cur.execute("SELECT DISTINCT symbol FROM algo_positions WHERE status = 'open'")
                db_symbols = {row['symbol'] for row in cur.fetchall()}

                orphans = alpaca_symbols - db_symbols
                missing = db_symbols - alpaca_symbols

                if orphans:
                    print(f"\n  ⚠️  ORPHAN POSITIONS (in Alpaca, not in DB): {list(orphans)}")
                if missing:
                    print(f"\n  ⚠️  MISSING POSITIONS (in DB, not in Alpaca): {list(missing)}")
                if not orphans and not missing:
                    print("\n  ✓ Position sync OK - all Alpaca positions are tracked in DB")

            except Exception as e:
                print(f"⚠️  Could not fetch Alpaca positions: {e}")

        except Exception as e:
            print(f"⚠️  Could not initialize Alpaca sync: {e}")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    diagnose()
