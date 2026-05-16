#!/usr/bin/env python3
"""Liquidity validation for position entries.

Validates that symbols meet minimum liquidity thresholds before entry:
- Minimum daily volume (1M shares default)
- Maximum bid-ask spread (0.5% default)
- Minimum market cap ($300M default)
- Minimum float (10M shares default)
- Maximum short interest (30% default)
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
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }


class LiquidityChecks:
    """Validate symbol liquidity before entry."""

    def __init__(self, config=None):
        self.config = config or {}
        self.min_volume = float(self.config.get('min_daily_volume_shares', 1000000.0))
        self.max_spread = float(self.config.get('max_spread_pct', 0.5))
        self.min_market_cap = float(self.config.get('min_market_cap_millions', 300.0))
        self.min_float = float(self.config.get('min_float_millions', 10.0))
        self.max_short_interest = float(self.config.get('max_short_interest_pct', 30.0))

    def run_all(self, symbol: str, entry_price: float, eval_date) -> Tuple[bool, str]:
        """Run all liquidity checks. Returns (passed, reason)."""
        checks = [
            self._check_volume(symbol),
            self._check_spread(symbol, entry_price),
            self._check_market_cap(symbol),
            self._check_float(symbol),
            self._check_short_interest(symbol),
        ]

        for passed, reason in checks:
            if not passed:
                return False, reason

        return True, "All liquidity checks passed"

    def _check_volume(self, symbol: str) -> Tuple[bool, str]:
        """Check minimum daily volume."""
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()
            cur.execute(
                """SELECT avg_volume FROM price_daily
                   WHERE symbol = %s ORDER BY date DESC LIMIT 1""",
                (symbol,)
            )
            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row or row[0] is None:
                return False, "No volume data available"

            avg_vol = float(row[0])
            if avg_vol < self.min_volume:
                return False, f"Avg volume {avg_vol:,.0f} < {self.min_volume:,.0f}"

            return True, f"Volume OK: {avg_vol:,.0f}"
        except Exception as e:
            logger.warning(f"Volume check error: {e}")
            return True, "Volume check skipped (error)"

    def _check_spread(self, symbol: str, entry_price: float) -> Tuple[bool, str]:
        """Check bid-ask spread."""
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()
            cur.execute(
                """SELECT bid, ask FROM price_daily
                   WHERE symbol = %s ORDER BY date DESC LIMIT 1""",
                (symbol,)
            )
            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row or row[0] is None or row[1] is None:
                return True, "No bid-ask data"

            bid, ask = float(row[0]), float(row[1])
            if ask <= bid or bid <= 0:
                return True, "Invalid bid-ask data"

            spread_pct = ((ask - bid) / entry_price) * 100 if entry_price > 0 else 0
            if spread_pct > self.max_spread:
                return False, f"Spread {spread_pct:.2f}% > {self.max_spread}%"

            return True, f"Spread OK: {spread_pct:.2f}%"
        except Exception as e:
            logger.warning(f"Spread check error: {e}")
            return True, "Spread check skipped"

    def _check_market_cap(self, symbol: str) -> Tuple[bool, str]:
        """Check minimum market cap."""
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()
            cur.execute(
                """SELECT market_cap FROM company_profile
                   WHERE ticker = %s LIMIT 1""",
                (symbol,)
            )
            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row or row[0] is None:
                return True, "No market cap data"

            market_cap_m = float(row[0]) / 1_000_000
            if market_cap_m < self.min_market_cap:
                return False, f"Market cap ${market_cap_m:,.0f}M < ${self.min_market_cap:,.0f}M"

            return True, f"Market cap OK: ${market_cap_m:,.0f}M"
        except Exception as e:
            logger.warning(f"Market cap check error: {e}")
            return True, "Market cap check skipped"

    def _check_float(self, symbol: str) -> Tuple[bool, str]:
        """Check minimum shares outstanding (float)."""
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()
            cur.execute(
                """SELECT shares_outstanding FROM company_profile
                   WHERE ticker = %s LIMIT 1""",
                (symbol,)
            )
            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row or row[0] is None:
                return True, "No float data"

            float_m = float(row[0]) / 1_000_000
            if float_m < self.min_float:
                return False, f"Float {float_m:,.1f}M < {self.min_float:,.1f}M"

            return True, f"Float OK: {float_m:,.1f}M"
        except Exception as e:
            logger.warning(f"Float check error: {e}")
            return True, "Float check skipped"

    def _check_short_interest(self, symbol: str) -> Tuple[bool, str]:
        """Check maximum short interest."""
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()
            cur.execute(
                """SELECT short_interest FROM company_profile
                   WHERE ticker = %s LIMIT 1""",
                (symbol,)
            )
            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row or row[0] is None:
                return True, "No short interest data"

            short_pct = float(row[0])
            if short_pct > self.max_short_interest:
                return False, f"Short interest {short_pct:.1f}% > {self.max_short_interest}%"

            return True, f"Short interest OK: {short_pct:.1f}%"
        except Exception as e:
            logger.warning(f"Short interest check error: {e}")
            return True, "Short interest check skipped"


if __name__ == "__main__":
    from algo_config import get_config
    config = get_config()
    lq = LiquidityChecks(config)
    passed, reason = lq.run_all("AAPL", 150.0, None)
    print(f"AAPL liquidity check: {reason}")
