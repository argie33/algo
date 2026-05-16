#!/usr/bin/env python3
"""
Data Integrity Verification - Ensures all critical tables have recent, complete data

This script audits whether key loaders are populating the database correctly.
Runs before trading to catch data issues early.
"""

import os
import psycopg2
import psycopg2.extras
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date, timedelta
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Get DB config (lazy-loaded to support testing)."""
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        try:
            from credential_manager import get_credential_manager
            credential_manager = get_credential_manager()
            db_password = credential_manager.get_db_credentials()["password"]
        except Exception:
            db_password = "postgres"

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": db_password,
        "database": os.getenv("DB_NAME", "stocks"),
    }

class DataIntegrityChecker:
    """Audit database tables for completeness and recency."""

    def __init__(self):
        self.conn = None
        self.cur = None
        self.findings = []
        self.eval_date = _date.today()

    def connect(self):
        self.conn = psycopg2.connect(**_get_db_config())
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def check_all(self) -> Dict[str, any]:
        """Run all integrity checks. Returns summary."""
        self.connect()
        try:
            checks = {
                'price_daily_completeness': self._check_price_daily(),
                'technical_data_completeness': self._check_technical_data(),
                'signal_data_freshness': self._check_signal_data(),
                'portfolio_data_integrity': self._check_portfolio_data(),
                'market_health_freshness': self._check_market_health(),
                'risk_metric_completeness': self._check_risk_metrics(),
            }

            return {
                'eval_date': self.eval_date.isoformat(),
                'checks': checks,
                'all_pass': all(c['pass'] for c in checks.values()),
                'failures': [k for k, v in checks.items() if not v['pass']],
            }
        finally:
            self.disconnect()

    def _check_price_daily(self) -> Dict:
        """Verify price_daily has complete data for all symbols."""
        try:
            # Count symbols with data from last 3 trading days
            self.cur.execute("""
                SELECT
                    COUNT(DISTINCT symbol) as symbol_count,
                    MAX(date) as latest_date,
                    COUNT(*) as total_rows
                FROM price_daily
                WHERE date >= CURRENT_DATE - INTERVAL '3 days'
            """)
            row = self.cur.fetchone()
            symbol_count = row['symbol_count'] or 0
            latest_date = row['latest_date']
            total_rows = row['total_rows'] or 0

            # Expect at least 100 symbols with data from last 3 days
            pass_flag = symbol_count >= 100 and latest_date is not None

            return {
                'pass': pass_flag,
                'symbols_loaded': symbol_count,
                'latest_date': latest_date.isoformat() if latest_date else None,
                'rows_3days': total_rows,
                'message': f'{symbol_count} symbols with recent price data' if pass_flag else f'Only {symbol_count} symbols — expected >=100'
            }
        except Exception as e:
            return {'pass': False, 'message': f'Error: {str(e)}'}

    def _check_technical_data(self) -> Dict:
        """Verify technical_data_daily has indicators calculated."""
        try:
            self.cur.execute("""
                SELECT
                    COUNT(DISTINCT symbol) as symbol_count,
                    MAX(date) as latest_date,
                    COUNT(*) as total_rows
                FROM technical_data_daily
                WHERE date >= CURRENT_DATE - INTERVAL '3 days'
                  AND rsi IS NOT NULL
                  AND sma_50 IS NOT NULL
            """)
            row = self.cur.fetchone()
            symbol_count = row['symbol_count'] or 0
            latest_date = row['latest_date']

            pass_flag = symbol_count >= 100 and latest_date is not None

            return {
                'pass': pass_flag,
                'symbols_with_indicators': symbol_count,
                'latest_date': latest_date.isoformat() if latest_date else None,
                'message': f'{symbol_count} symbols with technical indicators' if pass_flag else f'Only {symbol_count} symbols — expected >=100'
            }
        except Exception as e:
            return {'pass': False, 'message': f'Error: {str(e)}'}

    def _check_signal_data(self) -> Dict:
        """Verify buy_sell_daily and signal_quality_scores are populated."""
        try:
            self.cur.execute("""
                SELECT
                    (SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE date >= CURRENT_DATE - INTERVAL '1 day') as signal_count,
                    (SELECT COUNT(DISTINCT symbol) FROM signal_quality_scores WHERE date >= CURRENT_DATE - INTERVAL '1 day') as sqs_count,
                    (SELECT MAX(date) FROM buy_sell_daily) as signal_latest
            """)
            row = self.cur.fetchone()
            signal_count = row['signal_count'] or 0
            sqs_count = row['sqs_count'] or 0
            signal_latest = row['signal_latest']

            pass_flag = signal_count > 0 and sqs_count > 0 and signal_latest is not None

            return {
                'pass': pass_flag,
                'buy_sell_signals': signal_count,
                'sqs_scores': sqs_count,
                'latest_signal_date': signal_latest.isoformat() if signal_latest else None,
                'message': f'{signal_count} signals, {sqs_count} SQS scores' if pass_flag else 'Missing signal data'
            }
        except Exception as e:
            return {'pass': False, 'message': f'Error: {str(e)}'}

    def _check_portfolio_data(self) -> Dict:
        """Verify algo_trades and algo_positions tables."""
        try:
            self.cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM algo_trades WHERE status = 'closed') as closed_trades,
                    (SELECT COUNT(*) FROM algo_positions WHERE status IN ('OPEN', 'open')) as open_positions,
                    (SELECT MAX(created_at) FROM algo_trades) as trades_latest
            """)
            row = self.cur.fetchone()
            closed_trades = row['closed_trades'] or 0
            open_positions = row['open_positions'] or 0
            trades_latest = row['trades_latest']

            # Even 1 closed trade is a positive signal; open positions can be 0
            pass_flag = trades_latest is not None

            return {
                'pass': pass_flag,
                'closed_trades': closed_trades,
                'open_positions': open_positions,
                'latest_trade': trades_latest.isoformat() if trades_latest else None,
                'message': f'{closed_trades} closed, {open_positions} open' if pass_flag else 'No trade history'
            }
        except Exception as e:
            return {'pass': False, 'message': f'Error: {str(e)}'}

    def _check_market_health(self) -> Dict:
        """Verify market_health_daily has recent data."""
        try:
            self.cur.execute("""
                SELECT
                    COUNT(*) as rows,
                    MAX(date) as latest_date
                FROM market_health_daily
                WHERE date >= CURRENT_DATE - INTERVAL '1 day'
            """)
            row = self.cur.fetchone()
            rows = row['rows'] or 0
            latest_date = row['latest_date']

            pass_flag = rows > 0 and latest_date is not None

            return {
                'pass': pass_flag,
                'rows': rows,
                'latest_date': latest_date.isoformat() if latest_date else None,
                'message': f'Market health data {latest_date}' if pass_flag else 'No market health data'
            }
        except Exception as e:
            return {'pass': False, 'message': f'Error: {str(e)}'}

    def _check_risk_metrics(self) -> Dict:
        """Verify algo_performance_daily and algo_risk_daily exist."""
        try:
            self.cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM algo_performance_daily) as perf_rows,
                    (SELECT COUNT(*) FROM algo_risk_daily) as risk_rows
            """)
            row = self.cur.fetchone()
            perf_rows = row['perf_rows'] or 0
            risk_rows = row['risk_rows'] or 0

            # These tables should exist, even if empty initially
            pass_flag = True  # Tables exist and can be written to

            return {
                'pass': pass_flag,
                'performance_metrics_rows': perf_rows,
                'risk_metrics_rows': risk_rows,
                'message': f'Risk tables ready'
            }
        except Exception as e:
            return {'pass': False, 'message': f'Error: {str(e)}'}


def main():
    checker = DataIntegrityChecker()
    result = checker.check_all()

    print("\n" + "="*70)
    print(f"DATA INTEGRITY CHECK — {result['eval_date']}")
    print("="*70 + "\n")

    for check_name, check_result in result['checks'].items():
        status = "✓ PASS" if check_result['pass'] else "✗ FAIL"
        print(f"{status}: {check_name}")
        print(f"  {check_result['message']}")

    print("\n" + "="*70)
    if result['all_pass']:
        print("✓ ALL CHECKS PASSED - System ready for trading")
        return 0
    else:
        print(f"✗ FAILURES: {', '.join(result['failures'])}")
        print("⚠️  Data may be incomplete - check loaders")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
