#!/usr/bin/env python3
"""
Audit Trail Dashboard - Query what happened in the algo

Simple query interface to answer:
- "What trades were made on 2026-05-09?"
- "Why was AAPL not traded?"
- "What signals were generated for MSFT?"
- "Which loaders failed today?"

Run:
    python3 audit_dashboard.py --date 2026-05-09 --symbol AAPL
    python3 audit_dashboard.py --loaders
"""

import argparse
import logging
import os
import psycopg2
from datetime import date, datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

credential_manager = get_credential_manager()

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }


class AuditDashboard:
    """Query audit trail."""

    def __init__(self):
        self.conn = None

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = psycopg2.connect(**_get_db_config())

    def disconnect(self):
        """Close connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def trades_by_date(self, target_date: date) -> List[Dict[str, Any]]:
        """Get all trades for a specific date."""
        try:
            self.connect()
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        created_at,
                        symbol,
                        side,
                        shares,
                        entry_price,
                        entry_reason,
                        status
                    FROM algo_trades
                    WHERE DATE(created_at) = %s
                    ORDER BY created_at DESC
                """, (target_date,))

                columns = [desc[0] for desc in cur.description]
                results = []
                for row in cur.fetchall():
                    results.append(dict(zip(columns, row)))
                return results

        except Exception as e:
            log.error(f"Failed to query trades: {e}")
            return []

    def trades_by_symbol(self, symbol: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get trades for a symbol in last N days."""
        try:
            self.connect()
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        created_at,
                        symbol,
                        side,
                        shares,
                        entry_price,
                        entry_reason,
                        exit_price,
                        exit_reason,
                        pnl,
                        status
                    FROM algo_trades
                    WHERE symbol = %s
                    AND created_at >= NOW() - INTERVAL '%d days'
                    ORDER BY created_at DESC
                """ % (days,), (symbol,))

                columns = [desc[0] for desc in cur.description]
                results = []
                for row in cur.fetchall():
                    results.append(dict(zip(columns, row)))
                return results

        except Exception as e:
            log.error(f"Failed to query trades: {e}")
            return []

    def signals_by_symbol(self, symbol: str, target_date: date) -> List[Dict[str, Any]]:
        """Get all signals generated for a symbol on a date."""
        try:
            self.connect()
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        date,
                        symbol,
                        buy_signal,
                        sell_signal,
                        signal_strength,
                        filter_score,
                        reason
                    FROM buy_sell_daily
                    WHERE symbol = %s
                    AND date = %s
                    LIMIT 5
                """, (symbol, target_date))

                columns = [desc[0] for desc in cur.description]
                results = []
                for row in cur.fetchall():
                    results.append(dict(zip(columns, row)))
                return results

        except Exception as e:
            log.error(f"Failed to query signals: {e}")
            return []

    def loader_status(self) -> List[Dict[str, Any]]:
        """Get current status of all loaders."""
        try:
            self.connect()
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        loader_name,
                        table_name,
                        latest_data_date,
                        row_count_today,
                        status,
                        error_message,
                        last_check_at
                    FROM loader_sla_status
                    WHERE DATE(last_check_at) = CURRENT_DATE
                    ORDER BY status DESC, loader_name
                """)

                columns = [desc[0] for desc in cur.description]
                results = []
                for row in cur.fetchall():
                    results.append(dict(zip(columns, row)))
                return results

        except Exception as e:
            log.warning(f"Failed to query loader status (tables may not exist): {e}")
            return []

    def print_trades(self, trades: List[Dict[str, Any]]):
        """Pretty-print trades."""
        if not trades:
            log.info("No trades found.")
            return

        log.info(f"\n{'='*100}")
        log.info(f"{'TRADES':<20} {len(trades)} found")
        log.info(f"{'='*100}")

        for trade in trades:
            log.info(f"\n  {trade.get('created_at')} | {trade.get('symbol')} {trade.get('side')} {trade.get('shares')} @ ${trade.get('entry_price'):.2f}")
            log.info(f"    Reason: {trade.get('entry_reason')}")
            log.info(f"    Status: {trade.get('status')}")
            if trade.get('pnl'):
                log.info(f"    P&L: ${trade.get('pnl'):.2f}")

    def print_signals(self, signals: List[Dict[str, Any]], symbol: str):
        """Pretty-print signals."""
        if not signals:
            log.info(f"No signals found for {symbol}.")
            return

        log.info(f"\n{'='*100}")
        log.info(f"{'SIGNALS':<20} {symbol}")
        log.info(f"{'='*100}")

        for signal in signals:
            buy = "[BUY]" if signal.get('buy_signal') else "      "
            sell = "[SELL]" if signal.get('sell_signal') else "       "
            log.info(f"\n  {signal.get('date')} | {buy} {sell} Strength: {signal.get('signal_strength'):.2f}")
            log.info(f"    Reason: {signal.get('reason')}")

    def print_loaders(self, loaders: List[Dict[str, Any]]):
        """Pretty-print loader status."""
        if not loaders:
            log.info("No loader status data found.")
            return

        log.info(f"\n{'='*100}")
        log.info(f"{'LOADER STATUS':<20} (today)")
        log.info(f"{'='*100}")

        for loader in loaders:
            status_icon = "✓" if loader.get('status') == 'OK' else "✗"
            log.info(f"\n  {status_icon} {loader.get('loader_name')} ({loader.get('table_name')})")
            log.info(f"    Latest data: {loader.get('latest_data_date')} | Rows: {loader.get('row_count_today')} | Status: {loader.get('status')}")
            if loader.get('error_message'):
                log.info(f"    Error: {loader.get('error_message')}")


def main():
    """CLI interface."""
    parser = argparse.ArgumentParser(
        description="Audit Trail Dashboard - Query what happened in the algo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Trades on a specific date
  python3 audit_dashboard.py --date 2026-05-09

  # Trades for a specific symbol (last 7 days)
  python3 audit_dashboard.py --symbol AAPL

  # Signals generated for MSFT today
  python3 audit_dashboard.py --signals MSFT --date 2026-05-09

  # Current loader status
  python3 audit_dashboard.py --loaders
        """
    )

    parser.add_argument('--date', type=str, help='Date (YYYY-MM-DD), default today')
    parser.add_argument('--symbol', type=str, help='Symbol (e.g., AAPL)')
    parser.add_argument('--signals', type=str, help='Get signals for symbol')
    parser.add_argument('--loaders', action='store_true', help='Get loader status')
    parser.add_argument('--days', type=int, default=7, help='Days to look back (default 7)')

    args = parser.parse_args()

    # Default date to today
    query_date = date.today()
    if args.date:
        try:
            query_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            log.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
            return 1

    dashboard = AuditDashboard()

    try:
        if args.loaders:
            loaders = dashboard.loader_status()
            dashboard.print_loaders(loaders)

        elif args.signals:
            signals = dashboard.signals_by_symbol(args.signals, query_date)
            dashboard.print_signals(signals, args.signals)

        elif args.symbol:
            trades = dashboard.trades_by_symbol(args.symbol, args.days)
            dashboard.print_trades(trades)

        elif args.date or not any([args.symbol, args.signals, args.loaders]):
            # Default: trades for the date
            trades = dashboard.trades_by_date(query_date)
            dashboard.print_trades(trades)

        log.info("")
        return 0

    except KeyboardInterrupt:
        log.info("\nCancelled.")
        return 0
    finally:
        dashboard.disconnect()


if __name__ == "__main__":
    import sys
    sys.exit(main())
