#!/usr/bin/env python3

"""
Options-Based Alpha Signals — IV rank, put/call ratio, implied move.

All signals return bonus points (0-3 pts max) to momentum component.
Gracefully handle missing options data (many small-caps have no options).
"""

import logging
from datetime import date as _date
from typing import Any

import psycopg2


logger = logging.getLogger(__name__)


class SignalOptionsMixin:
    """Options-based signals for bonus alpha scoring."""

    def iv_rank_signal(self, symbol: str, eval_date: _date) -> dict[str, Any]:
        def _fetch_iv(cur):
            cur.execute(
                """
                SELECT current_iv, iv_52w_high, iv_52w_low FROM iv_history
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
                """,
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return {"iv_rank": None, "signal": "neutral", "bonus_pts": 0.0}

            current_iv, iv_high, iv_low = safe_float(row[0], default=0.0, context="row[0]"), safe_float(row[1], default=0.0, context="row[1]"), safe_float(row[2], default=0.0, context="row[2]")

            # Avoid division by zero
            if iv_high == iv_low:
                return {"iv_rank": None, "signal": "neutral", "bonus_pts": 0.0}

            iv_rank = (current_iv - iv_low) / (iv_high - iv_low) * 100

            # Interpret rank
            if iv_rank < 20:
                signal = "compress"  # Compression, potential for expansion
                bonus_pts = 1.5  # Mild bonus (not confirmed breakout yet)
            elif iv_rank > 80:
                signal = "expand"  # Already elevated, mean reversion risk
                bonus_pts = 0.0  # No bonus (adds risk)
            else:
                signal = "neutral"
                bonus_pts = 0.0

            return {
                "iv_rank": round(iv_rank, 1),
                "signal": signal,
                "bonus_pts": bonus_pts,
            }

        try:
            return self._with_cursor(_fetch_iv) or {"iv_rank": None, "signal": "neutral", "bonus_pts": 0.0}  # type: ignore[attr-defined]
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"IV rank signal failed for {symbol}: {e}")
            return {"iv_rank": None, "signal": "neutral", "bonus_pts": 0.0}

    def put_call_ratio_signal(self, symbol: str, eval_date: _date) -> dict[str, Any]:
        """
        Stock-level put/call ratio from options_chains.

        High PC ratio (>2.0) = panic hedging = capitulation if technicals strong.

        Returns:
            {
                'put_call_ratio': float,
                'signal': 'bullish'|'bearish'|'neutral',
                'bonus_pts': float (0-2),
            }
        """

        def _fetch_pc_ratio(cur):
            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN option_type = 'put' THEN volume ELSE 0 END) AS put_vol,
                    SUM(CASE WHEN option_type = 'call' THEN volume ELSE 0 END) AS call_vol
                FROM options_chains
                WHERE symbol = %s AND quote_date = %s
                """,
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row or not row[0] or not row[1]:
                return {"put_call_ratio": None, "signal": "neutral", "bonus_pts": 0.0}

            put_vol, call_vol = safe_float(row[0], default=0.0, context="row[0]"), safe_float(row[1], default=0.0, context="row[1]")
            if call_vol == 0:
                return {"put_call_ratio": None, "signal": "neutral", "bonus_pts": 0.0}

            pc_ratio = put_vol / call_vol

            # Interpret P/C ratio
            if pc_ratio > 2.0:
                signal = "bullish"  # Panic hedging = capitulation
                bonus_pts = 2.0  # Strong signal (if technicals confirm)
            elif pc_ratio < 0.5:
                signal = "bearish"  # All calls, no hedging = complacency
                bonus_pts = 0.0
            else:
                signal = "neutral"
                bonus_pts = 0.0

            return {
                "put_call_ratio": round(pc_ratio, 2),
                "signal": signal,
                "bonus_pts": bonus_pts,
            }

        try:
            return self._with_cursor(_fetch_pc_ratio) or {"put_call_ratio": None, "signal": "neutral", "bonus_pts": 0.0}  # type: ignore[attr-defined]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"P/C ratio signal failed for {symbol}: {e}")
            return {"put_call_ratio": None, "signal": "neutral", "bonus_pts": 0.0}

    def implied_move_signal(
        self,
        symbol: str,
        eval_date: _date,
    ) -> dict[str, Any]:
        """
        Options-implied move = current_IV * sqrt(days_to_expiry / 365)

        Use: Is the implied move consistent with the chart setup's potential?
        If implied_move < base_depth_pct: options underpricing the setup.

        Returns:
            {
                'implied_move_pct': float,
                'vs_base_depth_pct': float,
                'underpriced': bool,
                'bonus_pts': float (0-1.5),
            }
        """

        def _fetch_implied_move(cur):
            cur.execute(
                """
                SELECT DISTINCT ON (symbol, quote_date)
                    iv, days_to_expiration
                FROM options_chains
                WHERE symbol = %s AND quote_date <= %s
                ORDER BY quote_date DESC, days_to_expiration DESC
                LIMIT 1
                """,
                (symbol, eval_date),
            )
            iv_row = cur.fetchone()
            if not iv_row or not iv_row[0]:
                return {
                    "implied_move_pct": None,
                    "vs_base_depth_pct": None,
                    "underpriced": False,
                    "bonus_pts": 0.0,
                }

            current_iv, days_to_exp = float(iv_row[0]), float(iv_row[1])
            if days_to_exp <= 0:
                days_to_exp = 30  # Default to 30 DTE

            implied_move = current_iv * (days_to_exp / 365.0) ** 0.5 * 100

            # Get base depth from technical analysis
            base_type = self.classify_base_type(symbol, eval_date)
            base_depth = float(base_type.get("depth_pct", 0)) if base_type else 0

            underpriced = implied_move < base_depth
            bonus_pts = 1.5 if underpriced else 0.0

            return {
                "implied_move_pct": round(implied_move, 2),
                "vs_base_depth_pct": round(base_depth, 2) if base_depth else None,
                "underpriced": underpriced,
                "bonus_pts": bonus_pts,
            }

        try:
            return self._with_cursor(_fetch_implied_move) or {  # type: ignore[attr-defined]
                "implied_move_pct": None,
                "vs_base_depth_pct": None,
                "underpriced": False,
                "bonus_pts": 0.0,
            }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"Implied move signal failed for {symbol}: {e}")
            return {
                "implied_move_pct": None,
                "vs_base_depth_pct": None,
                "underpriced": False,
                "bonus_pts": 0.0,
            }

    def options_signal(self, symbol: str, eval_date: _date) -> dict[str, Any]:
        """
        Aggregate all options signals for use in momentum component scoring.

        Returns:
            {
                'iv_rank': {...},
                'put_call': {...},
                'implied_move': {...},
                'bonus_pts': float (sum of bonuses, capped at 3),
            }
        """
        iv_sig = self.iv_rank_signal(symbol, eval_date)
        pc_sig = self.put_call_ratio_signal(symbol, eval_date)
        im_sig = self.implied_move_signal(symbol, eval_date)

        total_bonus = min(
            3.0,
            iv_sig.get("bonus_pts", 0) + pc_sig.get("bonus_pts", 0) + im_sig.get("bonus_pts", 0),
        )

        return {
            "iv_rank": iv_sig,
            "put_call": pc_sig,
            "implied_move": im_sig,
            "bonus_pts": total_bonus,
        }
