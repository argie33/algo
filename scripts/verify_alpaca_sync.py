#!/usr/bin/env python3
"""Verify Alpaca account state and sync status."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

import psycopg2.extras
import requests

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check_alpaca_connectivity():
    """Test if we can reach Alpaca and get account info."""
    print("\n" + "="*80)
    print("ALPACA CONNECTIVITY & ACCOUNT CHECK")
    print("="*80)

    try:
        from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager

        # Create minimal config for Alpaca sync
        config = {"execution_mode": "paper"}
        sync = AlpacaSyncManager(config)

        # Test 1: Account access
        print("\n[1] Testing Alpaca account access...")
        try:
            account = sync.fetch_alpaca_account()
            print("OK Connected to Alpaca")
            print(f"  Portfolio value: ${account.get('portfolio_value')}")
            print(f"  Cash: ${account.get('cash')}")
            print(f"  Buying power: ${account.get('buying_power')}")
            print(f"  Account status: {account.get('status')}")
        except Exception as e:
            print(f"ERROR Failed to fetch account: {e}")
            return

        # Test 2: Fetch positions from Alpaca
        print("\n[2] Fetching open positions from Alpaca...")
        try:
            url = f"{sync.alpaca_base_url}/v2/positions"
            headers = {
                "APCA-API-KEY-ID": sync.alpaca_key,
                "APCA-API-SECRET-KEY": sync.alpaca_secret,
                "Accept": "application/json",
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            alpaca_positions = response.json()

            if not isinstance(alpaca_positions, list):
                print(f"ERROR Unexpected response type: {type(alpaca_positions)}")
                return

            print(f"OK Got {len(alpaca_positions)} positions from Alpaca")

            if alpaca_positions:
                print("\nAlpaca positions:")
                total_value = 0
                for pos in alpaca_positions:
                    symbol = pos['symbol']
                    qty = float(pos['qty'])
                    entry_price = float(pos['avg_entry_price'])
                    current_price = float(pos['current_price'])
                    pos_value = qty * current_price
                    total_value += pos_value
                    unrealized = (current_price - entry_price) * qty

                    print(f"  {symbol:6} | qty={qty:8.2f} | entry=${entry_price:10.2f} | "
                          f"current=${current_price:10.2f} | value=${pos_value:12.2f} | "
                          f"unrealized=${unrealized:10.2f}")

                print(f"\nTotal portfolio value in Alpaca: ${total_value:,.2f}")
            else:
                print("! No positions in Alpaca")

        except Exception as e:
            print(f"ERROR Failed to fetch positions: {e}")
            return

        # Test 3: Compare with database
        print("\n[3] Comparing Alpaca positions with database...")
        with DatabaseContext() as db:
            cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Get DB positions
            cur.execute("""
                SELECT symbol, quantity, avg_entry_price, position_value, status
                FROM algo_positions
                WHERE status = 'open'
                ORDER BY symbol
            """)
            db_positions = {row['symbol']: row for row in cur.fetchall()}

            # Get Alpaca positions
            alpaca_symbols = {pos['symbol'] for pos in alpaca_positions}
            db_symbols = set(db_positions.keys())

            # Sync issues
            orphan_in_alpaca = alpaca_symbols - db_symbols
            missing_in_alpaca = db_symbols - alpaca_symbols

            if orphan_in_alpaca:
                print(f"\nWARNING ORPHAN POSITIONS (in Alpaca, not in DB): {sorted(orphan_in_alpaca)}")
                print("   -> These won't be tracked by the algo")

            if missing_in_alpaca:
                print(f"\nWARNING MISSING IN ALPACA (in DB, not live): {sorted(missing_in_alpaca)}")
                print("   -> Database positions don't match Alpaca reality")

            if not orphan_in_alpaca and not missing_in_alpaca:
                print("\nOK Position sync OK - DB and Alpaca match perfectly")

            # Detailed comparison
            if orphan_in_alpaca or missing_in_alpaca:
                print("\n[4] SYNC DISCREPANCY DETAILS")
                print("-" * 80)

                if orphan_in_alpaca:
                    print("\nOrphan positions (need to add to DB or close in Alpaca):")
                    for symbol in sorted(orphan_in_alpaca):
                        for pos in alpaca_positions:
                            if pos['symbol'] == symbol:
                                qty = float(pos['qty'])
                                price = float(pos['current_price'])
                                value = qty * price
                                print(f"  {symbol:6} | qty={qty:8.2f} | price=${price:10.2f} | "
                                      f"value=${value:12.2f}")

                if missing_in_alpaca:
                    print("\nMissing in Alpaca (database only - may be closed):")
                    for symbol in sorted(missing_in_alpaca):
                        pos = db_positions[symbol]
                        print(f"  {symbol:6} | qty={pos['quantity']:8.2f} | value=${pos['position_value']:12.2f} | "
                              f"db_status={pos['status']}")

        print("\n" + "="*80)

    except ImportError as e:
        print(f"ERROR Failed to import Alpaca module: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_alpaca_connectivity()
