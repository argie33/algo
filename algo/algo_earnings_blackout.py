#!/usr/bin/env python3
"""Earnings date awareness and blackout enforcement.

Prevents entries ±N days around earnings announcements to avoid whipsaws.
Default: ±7 days from earnings date is a blackout period.
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date
from typing import Dict, Any
import logging
from credential_helper import get_db_password, get_db_config

logger = logging.getLogger(__name__)

try:
    from algo_alerts import AlertManager
except ImportError:
    class AlertManager:
        def critical(self, *args, **kwargs): pass

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime (uses centralized credential_helper)."""
    return get_db_config()


class EarningsBlackout:
    """Enforce earnings date blackout windows."""

    def __init__(self, config=None):
        self.config = config or {}
        self.days_before = int(self.config.get('earnings_blackout_days_before', 7))
        self.days_after = int(self.config.get('earnings_blackout_days_after', 7))

    def run(self, symbol: str, eval_date: _date) -> Dict[str, Any]:
        """Check if eval_date is in earnings blackout window. Returns dict with 'pass' key.

        If earnings_calendar table doesn't exist (not yet implemented), passes through.
        """
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()

            # Check if earnings exists within the blackout window
            cur.execute(
                """SELECT earnings_date FROM earnings_calendar
                   WHERE symbol = %s
                   AND earnings_date >= %s
                   AND earnings_date <= %s
                   ORDER BY earnings_date LIMIT 1""",
                (
                    symbol,
                    eval_date - timedelta(days=self.days_before),
                    eval_date + timedelta(days=self.days_after),
                )
            )
            row = cur.fetchone()
            cur.close()
            conn.close()

            if row:
                earnings_date = row[0]
                days_until = (earnings_date - eval_date).days
                return {
                    'pass': False,
                    'reason': f'Earnings on {earnings_date} ({abs(days_until)}d away)',
                }

            return {
                'pass': True,
                'reason': f'No earnings in ±{self.days_before}/{self.days_after}d window',
            }
        except psycopg2.errors.UndefinedTable:
            logger.info(f"Earnings calendar not yet populated; skipping blackout for {symbol}")
            return {'pass': True, 'reason': 'Earnings calendar not available (pass-through)'}
        except Exception as e:
            logger.error(f"Earnings blackout check error for {symbol}: {e} — FAILING CLOSED (blocking trade)")
            return {'pass': False, 'reason': f'Earnings check failed: {str(e)[:50]} (fail-closed for safety)'}

    def get_upcoming_earnings(self, symbol: str, days_ahead: int = 30) -> list:
        """Get upcoming earnings for symbol."""
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()

            cur.execute(
                """SELECT earnings_date FROM earnings_calendar
                   WHERE symbol = %s
                   AND earnings_date >= %s
                   AND earnings_date <= %s
                   ORDER BY earnings_date""",
                (
                    symbol,
                    _date.today(),
                    _date.today() + timedelta(days=days_ahead),
                )
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()

            return [{'date': row[0]} for row in rows]
        except Exception as e:
            logger.warning(f"Failed to fetch earnings for {symbol}: {e}")
            return []


if __name__ == "__main__":
    from algo_config import get_config
    config = get_config()
    eb = EarningsBlackout(config)

    # Test
    result = eb.run("AAPL", _date(2026, 5, 15))
    print(f"AAPL earnings check (2026-05-15): {result}")

    upcoming = eb.get_upcoming_earnings("AAPL")
    print(f"AAPL upcoming earnings: {upcoming}")

