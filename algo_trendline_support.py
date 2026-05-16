#!/usr/bin/env python3
"""
Minervini Trendline Support Detection

Finds 2-point rising support lines and validates entry near the line.
Support line = two recent lows with an uptrend angle.

HIGH CONFIDENCE ENTRY: Stage 2 + RS > 70 + Volume + Entry near trendline support
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
from credential_helper import get_db_password, get_db_config
from datetime import datetime, timedelta, date as _date
from typing import Dict, Optional, Tuple
import logging
import statistics

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
    "password": get_db_password(),
    "database": os.getenv("DB_NAME", "stocks"),
    }


class TrendlineSupport:
    """Detect and validate 2-point support trendlines."""

    def __init__(self, cur=None, lookback_days=130):
        """
        Args:
            cur: psycopg2 cursor (if None, will create own connection)
            lookback_days: how far back to look for support line (default 130 = 6 months)
        """
        self.cur = cur
        self.conn = None
        self.lookback_days = lookback_days

    def connect(self):
        """Create own database connection if needed."""
        if not self.cur:
            self.conn = psycopg2.connect(**_get_db_config())
            self.cur = self.conn.cursor()

    def disconnect(self):
        """Close own connection if created."""
        if self.conn:
            self.cur.close()
            self.conn.close()
            self.cur = self.conn = None

    def get_price_history(self, symbol: str, end_date: _date, days: int = 130) -> list:
        """Get closing prices for the lookback period."""
        try:
            self.cur.execute(
                """
                SELECT date, low, close FROM price_daily
                WHERE symbol = %s
                  AND date >= %s
                  AND date <= %s
                ORDER BY date ASC
                """,
                (symbol, end_date - timedelta(days=days), end_date),
            )
            return self.cur.fetchall()
        except Exception as e:
            logger.warning(f"Error fetching price history for {symbol}: {e}")
            return []

    def find_support_line(self, symbol: str, eval_date: _date) -> Optional[Dict]:
        """
        Find 2-point rising support line.

        Returns:
            {
                'support_level': float,     # projected support at eval_date
                'low_1_date': date,         # first low
                'low_1_price': float,
                'low_2_date': date,         # second low (more recent, higher)
                'low_2_price': float,
                'angle_degrees': float,     # uptrend angle
                'days_apart': int,          # days between the two lows
                'confidence': float,        # 0-100 score
                'reason': str,              # human readable
            }
        """
        prices = self.get_price_history(symbol, eval_date, self.lookback_days)
        if len(prices) < 20:
            return None

        # Extract lows with dates
        lows = [(p[0], p[1]) for p in prices]  # (date, low)

        # Find swing lows: local minima (lower than neighbors)
        swing_lows = []
        for i in range(2, len(lows) - 2):
            if lows[i][1] < lows[i - 1][1] and lows[i][1] < lows[i + 1][1]:
                if lows[i][1] < lows[i - 2][1] and lows[i][1] < lows[i + 2][1]:
                    swing_lows.append(lows[i])

        if len(swing_lows) < 2:
            return None

        # Find best 2-point support line:
        # - 2nd low should be HIGHER than 1st (rising support)
        # - At least 20 days apart (meaningful time)
        # - Angle should be positive but not too steep
        best_trendline = None
        best_confidence = 0

        for i in range(len(swing_lows) - 1):
            for j in range(i + 1, len(swing_lows)):
                low_1_date, low_1_price = swing_lows[i]
                low_2_date, low_2_price = swing_lows[j]

                # 2nd low must be higher (rising support)
                if low_2_price <= low_1_price:
                    continue

                days_apart = (low_2_date - low_1_date).days
                if days_apart < 20:
                    continue

                # Calculate angle
                price_rise = low_2_price - low_1_price
                angle_degrees = (price_rise / low_1_price) * 100  # % rise

                # Angle should be 1-20% (not too flat, not too steep)
                if angle_degrees < 1 or angle_degrees > 20:
                    continue

                # Calculate support level at eval_date
                days_from_low2 = (eval_date - low_2_date).days
                if days_from_low2 < 0:
                    continue  # eval_date before this trendline

                slope = price_rise / days_apart
                support_at_eval = low_2_price + (slope * days_from_low2)

                # Confidence: how recent is the support line?
                # Recent (0-20 days) = 100, older = lower confidence
                recency_score = max(0, 100 - (days_from_low2 * 3))

                confidence = recency_score * (100 - angle_degrees) / 100

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_trendline = {
                        'support_level': support_at_eval,
                        'low_1_date': low_1_date,
                        'low_1_price': low_1_price,
                        'low_2_date': low_2_date,
                        'low_2_price': low_2_price,
                        'angle_degrees': angle_degrees,
                        'days_apart': days_apart,
                        'days_from_low2': days_from_low2,
                        'confidence': best_confidence,
                    }

        if not best_trendline:
            return None

        best_trendline['reason'] = (
            f"Support line from {best_trendline['low_1_date']} (${best_trendline['low_1_price']:.2f}) "
            f"to {best_trendline['low_2_date']} (${best_trendline['low_2_price']:.2f}), "
            f"angle {best_trendline['angle_degrees']:.1f}%, "
            f"projected at eval_date: ${best_trendline['support_level']:.2f}"
        )

        return best_trendline

    def validate_entry_near_trendline(self, symbol: str, eval_date: _date, entry_price: float) -> Dict:
        """
        Check if entry_price is near (above) the support trendline.

        Returns:
            {
                'near_trendline': True/False,
                'trendline_support': float or None,
                'distance_pct': float,    # % above trendline
                'reason': str,
            }
        """
        trendline = self.find_support_line(symbol, eval_date)

        if not trendline:
            return {
                'near_trendline': False,
                'trendline_support': None,
                'distance_pct': None,
                'reason': 'No valid support trendline found',
            }

        support_level = trendline['support_level']

        # Entry should be near (1-5% above) the support line
        distance_pct = ((entry_price - support_level) / support_level) * 100

        # Accept entries 0.5-5% above support (not on the line, above it)
        near_trendline = 0.5 <= distance_pct <= 5.0

        return {
            'near_trendline': near_trendline,
            'trendline_support': support_level,
            'distance_pct': distance_pct,
            'confidence': trendline['confidence'],
            'reason': (
                f"Entry ${entry_price:.2f} is {distance_pct:.1f}% above support ${support_level:.2f}. "
                f"Trendline: {trendline['reason']}"
            ),
        }

