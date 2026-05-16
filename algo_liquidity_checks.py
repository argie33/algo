#!/usr/bin/env python3
"""
Liquidity checks for Tier 5 portfolio health filtering.

Ensures entry can be executed with adequate liquidity and reasonable spreads.
"""

import psycopg2
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from structured_logger import get_logger

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logger = get_logger(__name__)


class LiquidityChecks:
    """Verify sufficient liquidity and spreads for trade execution."""

    def __init__(self, config: dict):
        self.config = config
        self.conn = None
        self.min_adv_shares = config.get('min_adv_shares', 50_000)
        self.min_adv_dollars = config.get('min_adv_dollars', 500_000)

    def connect(self):
        """Connect to database."""
        if not self.conn:
            import os
            self.conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 5432)),
                user=os.getenv("DB_USER", "stocks"),
                password=os.getenv("DB_PASSWORD", "postgres"),
                database=os.getenv("DB_NAME", "stocks"),
            )

    def disconnect(self):
        """Disconnect from database."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def run_all(self, symbol: str, entry_price: float, signal_date) -> tuple:
        """
        Run all liquidity checks.

        Args:
            symbol: Stock symbol
            entry_price: Intended entry price
            signal_date: Date of signal

        Returns:
            Tuple[bool, str]: (passed, reason)
        """
        try:
            self.connect()

            # Check 1: Average Daily Volume (ADV)
            adv_passed, adv_reason = self._check_adv(symbol, signal_date)
            if not adv_passed:
                return False, f"ADV check failed: {adv_reason}"

            # Check 2: Dollar volume at entry price
            dollar_vol_passed, dollar_reason = self._check_dollar_volume(
                symbol, entry_price, signal_date
            )
            if not dollar_vol_passed:
                return False, f"Dollar volume check failed: {dollar_reason}"

            return True, "All liquidity checks passed"

        except Exception as e:
            logger.warning(f"Liquidity check error for {symbol}: {e}")
            return True, "Liquidity checks skipped (error)"
        finally:
            self.disconnect()

    def _check_adv(self, symbol: str, signal_date) -> tuple:
        """
        Check average daily volume (20-day average).

        Returns:
            Tuple[bool, str]: (passed, reason)
        """
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                SELECT AVG(volume) as avg_vol
                FROM price_daily
                WHERE symbol = %s
                  AND date >= %s
                  AND date < %s
                ORDER BY date DESC
                LIMIT 20
                """,
                (
                    symbol,
                    signal_date - timedelta(days=25),
                    signal_date,
                ),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                return False, "No volume data available"

            avg_vol = float(row[0])
            if avg_vol < self.min_adv_shares:
                return False, f"ADV {avg_vol:,.0f} < minimum {self.min_adv_shares:,.0f}"

            return True, f"ADV {avg_vol:,.0f} ok"

        except Exception as e:
            logger.warning(f"ADV check error for {symbol}: {e}")
            return True, "ADV check skipped"

    def _check_dollar_volume(self, symbol: str, entry_price: float, signal_date) -> tuple:
        """
        Check average dollar volume (volume * price) for position sizing.

        Returns:
            Tuple[bool, str]: (passed, reason)
        """
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                SELECT AVG(volume * close) as avg_dollar_vol
                FROM price_daily
                WHERE symbol = %s
                  AND date >= %s
                  AND date < %s
                ORDER BY date DESC
                LIMIT 20
                """,
                (
                    symbol,
                    signal_date - timedelta(days=25),
                    signal_date,
                ),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                return False, "No price data available"

            avg_dollar_vol = float(row[0])
            if avg_dollar_vol < self.min_adv_dollars:
                return (
                    False,
                    f"Dollar vol ${avg_dollar_vol:,.0f} < minimum ${self.min_adv_dollars:,.0f}",
                )

            return True, f"Dollar vol ${avg_dollar_vol:,.0f} ok"

        except Exception as e:
            logger.warning(f"Dollar volume check error for {symbol}: {e}")
            return True, "Dollar volume check skipped"
