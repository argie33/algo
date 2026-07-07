#!/usr/bin/env python3
"""Sync Alpaca positions after account reset.

Run this after manually resetting your Alpaca paper account to verify
clean state and sync the database.

Usage:
    python scripts/sync_alpaca_positions.py
"""

import json
import os
import sys

import boto3  # noqa: F401


def main() -> int:
    print("=" * 70)
    print("ALPACA POSITION SYNC")
    print("=" * 70 + "\n")

    # Load credentials
    try:
        client = boto3.client('secretsmanager', region_name='us-east-1')
        secret = json.loads(client.get_secret_value(SecretId='algo/alpaca')['SecretString'])
        os.environ['APCA_API_KEY_ID'] = secret['APCA_API_KEY_ID']
        os.environ['APCA_API_SECRET_KEY'] = secret['APCA_API_SECRET_KEY']
        print("✓ Credentials loaded from AWS Secrets Manager")
    except Exception as e:
        print(f"✗ Failed to load credentials: {e}")
        return False

    # Verify Alpaca account state
    try:
        import requests
        headers = {
            "APCA-API-KEY-ID": os.environ['APCA_API_KEY_ID'],
            "APCA-API-SECRET-KEY": os.environ['APCA_API_SECRET_KEY'],
        }

        resp = requests.get("https://paper-api.alpaca.markets/v2/positions", headers=headers, timeout=10)
        positions = resp.json()

        if len(positions) > 0:
            print(f"\n✗ ERROR: Alpaca account still has {len(positions)} positions:")
            for pos in positions:
                print(f"    {pos['symbol']}: {float(pos['qty']):.0f} shares")
            print("\n→ Please manually reset your Alpaca paper account first")
            print("  See ALPACA_ACCOUNT_RESET.md for instructions")
            return False

        resp = requests.get("https://paper-api.alpaca.markets/v2/account", headers=headers, timeout=10)
        account = resp.json()
        print(f"✓ Alpaca account clean: ${float(account['portfolio_value']):,.2f}")

    except Exception as e:
        print(f"✗ Failed to check Alpaca: {e}")
        return False

    # Sync database
    try:
        from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager
        from utils.db import DatabaseContext

        sync = AlpacaSyncManager({"api_request_timeout_seconds": 30})

        with DatabaseContext("write") as cur:
            result = sync.sync_alpaca_positions(cur)
            print(f"✓ Sync result: {result['message']}")

    except Exception as e:
        print(f"✗ Sync failed: {e}")
        return False

    # Refresh materialized view
    try:
        with DatabaseContext("write") as cur:
            cur.execute("REFRESH MATERIALIZED VIEW algo_positions_with_risk")
        print("✓ Materialized view refreshed")
    except Exception as e:
        print(f"✗ View refresh failed: {e}")
        return False

    # Verify database state
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
            open_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM algo_positions_with_risk WHERE status = 'open'")
            view_count = cur.fetchone()[0]

            cur.execute(
            "SELECT COUNT(*) FROM algo_trades "
            "WHERE status IN ('open', 'filled', 'active', 'partially_filled') AND exit_date IS NULL"
        )
            trades_count = cur.fetchone()[0]

        print("\n✓ Database state:")
        print(f"    algo_positions (open): {open_count}")
        print(f"    algo_positions_with_risk (open): {view_count}")
        print(f"    algo_trades (open): {trades_count}")

        if open_count == 0 and view_count == 0 and trades_count == 0:
            print("\n✓✓✓ ALL SYSTEMS SYNCED - READY TO TRADE ✓✓✓")
            return True
        else:
            print("\n✗ Sync incomplete - positions still present")
            return False

    except Exception as e:
        print(f"✗ Database verification failed: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
