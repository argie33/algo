#!/usr/bin/env python3
"""
Check Alpaca position sync status.

Diagnoses position drift between database and Alpaca broker.
"""

import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

def check_alpaca_connection():
    """Test Alpaca API connection."""
    logger.info("\n" + "="*70)
    logger.info("1. TESTING ALPACA CONNECTION")
    logger.info("="*70)

    try:
        import requests
        from config.credential_manager import get_credential_manager
        from config.alpaca_config import get_alpaca_base_url

        cm = get_credential_manager()
        creds = cm.get_alpaca_credentials()
        api_key = creds.get('key')
        secret_key = creds.get('secret')

        if not api_key or not secret_key:
            logger.error("[FAIL] Alpaca credentials not found")
            logger.info("   Check AWS Secrets Manager (algo/alpaca) or env vars")
            return False

        logger.info("[OK] Credentials loaded from credential_manager")

        # Test account endpoint with correct base URL
        base_url = get_alpaca_base_url()
        headers = {
            'APCA-API-KEY-ID': api_key,
            'APCA-API-SECRET-KEY': secret_key,
        }

        response = requests.get(
            f'{base_url}/v2/account',
            headers=headers,
            timeout=10
        )

        if response.status_code == 401:
            logger.error("[FAIL] Alpaca API returned 401 Unauthorized")
            logger.info("   Credentials from AWS Secrets Manager are invalid")
            return False
        elif response.status_code != 200:
            logger.error(f"[FAIL] Alpaca API returned {response.status_code}")
            logger.info(f"   Response: {response.text[:200]}")
            return False

        account = response.json()
        logger.info(f"[OK] Connected to Alpaca")
        logger.info(f"  Account: {account.get('account_number', 'N/A')}")
        logger.info(f"  Portfolio: ${float(account.get('portfolio_value', 0)):,.2f}")
        logger.info(f"  Buying Power: ${float(account.get('buying_power', 0)):,.2f}")

        return True
    except Exception as e:
        logger.error(f"[FAIL] Alpaca connection failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def check_alpaca_positions():
    """Check what positions Alpaca shows."""
    logger.info("\n" + "="*70)
    logger.info("2. ALPACA POSITIONS")
    logger.info("="*70)

    try:
        import requests
        from config.credential_manager import get_credential_manager
        from config.alpaca_config import get_alpaca_base_url

        cm = get_credential_manager()
        creds = cm.get_alpaca_credentials()
        headers = {
            'APCA-API-KEY-ID': creds.get('key'),
            'APCA-API-SECRET-KEY': creds.get('secret'),
        }
        base_url = get_alpaca_base_url()

        response = requests.get(
            f'{base_url}/v2/positions',
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            logger.error(f"Failed to fetch positions: {response.status_code}")
            return []

        positions = response.json()
        logger.info(f"Alpaca shows {len(positions)} open position(s)")

        if positions:
            logger.info(f"\n{'Symbol':<8} {'Qty':<8} {'Avg Entry':<12} {'Current':<12} {'Value':<15}")
            logger.info("-" * 60)
            for pos in positions:
                symbol = pos.get('symbol', 'N/A')
                qty = pos.get('qty', 0)

                # Validate avg_fill_price
                avg_fill_raw = pos.get('avg_fill_price')
                if avg_fill_raw is None:
                    logger.warning(f"⚠️  {symbol}: Alpaca returned NO avg_fill_price — position data incomplete")
                    avg_fill_display = "UNKNOWN"
                else:
                    avg_fill = float(avg_fill_raw)
                    avg_fill_display = f"${avg_fill:.2f}"

                # Validate current_price
                current_raw = pos.get('current_price')
                if current_raw is None:
                    logger.warning(f"⚠️  {symbol}: Alpaca returned NO current_price — position data incomplete")
                    current_display = "UNKNOWN"
                else:
                    current = float(current_raw)
                    current_display = f"${current:.2f}"

                # Validate market_value
                value_raw = pos.get('market_value')
                if value_raw is None:
                    logger.warning(f"⚠️  {symbol}: Alpaca returned NO market_value — position data incomplete")
                    value_display = "UNKNOWN"
                else:
                    value = float(value_raw)
                    value_display = f"${value:,.0f}"

                logger.info(f"{symbol:<8} {qty:<8} {avg_fill_display:<12} {current_display:<12} {value_display:<15}")
        else:
            logger.warning("[WARN] Alpaca shows NO open positions")

        return positions
    except Exception as e:
        logger.error(f"Error fetching Alpaca positions: {e}")
        return []


def check_db_positions():
    """Check what positions are in the database."""
    logger.info("\n" + "="*70)
    logger.info("3. DATABASE POSITIONS")
    logger.info("="*70)

    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT symbol, quantity, avg_entry_price, current_price, status
                FROM algo_positions
                WHERE status IN ('open', 'orphaned')
                ORDER BY symbol
            """)

            rows = cur.fetchall()
            logger.info(f"Database shows {len(rows)} position(s)")

            if rows:
                logger.info(f"\n{'Symbol':<8} {'Qty':<8} {'Avg Entry':<12} {'Current':<12} {'Status':<12}")
                logger.info("-" * 60)
                for symbol, qty, avg_entry, current, status in rows:
                    status_marker = "🔴 ORPHANED" if status == 'orphaned' else "✅ OPEN"
                    logger.info(f"{symbol:<8} {qty:<8} ${avg_entry:<11.2f} ${current:<11.2f} {status_marker:<12}")
            else:
                logger.info("No open positions in DB")

        return rows
    except Exception as e:
        logger.error(f"Error reading DB positions: {e}")
        return []


def check_position_drift():
    """Compare Alpaca vs DB positions."""
    logger.info("\n" + "="*70)
    logger.info("4. POSITION DRIFT ANALYSIS")
    logger.info("="*70)

    try:
        alpaca_pos = check_alpaca_positions()
        db_pos = check_db_positions()

        alpaca_symbols = {p['symbol'] for p in alpaca_pos}
        db_symbols = {row[0] for row in db_pos if row[4] == 'open'}  # Only count 'open', not 'orphaned'

        logger.info(f"\nSymbols in Alpaca: {sorted(alpaca_symbols) or 'none'}")
        logger.info(f"Symbols in DB (open): {sorted(db_symbols) or 'none'}")

        missing_from_alpaca = db_symbols - alpaca_symbols
        extra_in_alpaca = alpaca_symbols - db_symbols
        matched = alpaca_symbols & db_symbols

        logger.info(f"\n🔍 Drift Summary:")
        logger.info(f"  Matched: {len(matched)}")
        logger.info(f"  In DB but NOT in Alpaca: {len(missing_from_alpaca)}")
        if missing_from_alpaca:
            logger.warning(f"    {', '.join(sorted(missing_from_alpaca))}")
            logger.warning("    ^ These are being marked ORPHANED and closed!")

        logger.info(f"  In Alpaca but NOT in DB: {len(extra_in_alpaca)}")
        if extra_in_alpaca:
            logger.warning(f"    {', '.join(sorted(extra_in_alpaca))}")
            logger.warning("    ^ These are not being tracked!")

        if missing_from_alpaca or extra_in_alpaca:
            logger.error("\n❌ POSITION DRIFT DETECTED!")
            logger.error("   This will cause reconciliation to close positions")
        elif len(matched) == 0:
            logger.warning("\n⚠️  NO POSITIONS - Algo is flat (expected if recently closed)")
        else:
            logger.info(f"\n✅ Positions are in sync")

    except Exception as e:
        logger.error(f"Error analyzing drift: {e}")


if __name__ == "__main__":
    try:
        logger.info("🔍 Alpaca Position Sync Diagnostic")

        if not check_alpaca_connection():
            logger.error("\n❌ Cannot connect to Alpaca. Fix credentials first.")
            sys.exit(1)

        check_position_drift()

        logger.info("\n" + "="*70)
        logger.info("💡 RECOMMENDATION")
        logger.info("="*70)
        logger.info("""
If you see:
  1. "Position drift detected" → Reconciliation is closing positions
     ACTION: Sync DB with Alpaca or manually verify positions in Alpaca

  2. "In DB but NOT in Alpaca" → Positions were closed/sold in Alpaca
     ACTION: Check Alpaca order history. Were they manually closed?

  3. "In Alpaca but NOT in DB" → Trades happened outside the algo
     ACTION: Either ignore (safe), or manually sync to DB

  4. "No positions" → Algo is flat (expected for now)
     ACTION: Wait for new orchestrator run to generate signals
             Check Phase 1 data freshness first
        """)

        logger.info("="*70 + "\n")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
