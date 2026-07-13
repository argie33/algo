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

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class SignalOptionsMixin:
    """Options-based signals for bonus alpha scoring."""

    def _with_cursor(self, operation: Any) -> Any:
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext("read") as cur:
                return operation(cur)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def iv_rank_signal(self, symbol: str, eval_date: _date) -> dict[str, Any]:
        def _fetch_iv(cur: Any) -> dict[str, Any]:
            cur.execute(
                """
                SELECT current_iv, iv_52w_high, iv_52w_low FROM iv_history
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
                """,
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if row is None or len(row) < 1 or row[0] is None:
                return {
                    "iv_rank": None,
                    "signal": None,
                    "bonus_pts": 0.0,
                    "data_unavailable": True,
                    "reason": "iv_history data not found",
                }

            # Validate all three IV values are present (fail-fast on incomplete data)
            if row[1] is None or row[2] is None:
                raise ValueError(
                    f"IV data incomplete for {symbol}: iv_high or iv_low is NULL — "
                    "cannot compute IV rank without complete historical range"
                )

            try:
                current_iv, iv_high, iv_low = (
                    float(row[0]),
                    float(row[1]),
                    float(row[2]),
                )
            except (ValueError, TypeError) as e:
                raise ValueError(f"IV conversion failed for {symbol}: {e}") from e

            # Avoid division by zero
            if iv_high == iv_low:
                raise ValueError(
                    f"IV range invalid for {symbol}: iv_high == iv_low ({iv_high}) — "
                    "cannot compute IV rank without volatility range"
                )

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

        return self._with_cursor(_fetch_iv)  # type: ignore[no-any-return]

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

        def _fetch_pc_ratio(cur: Any) -> dict[str, Any]:
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
            if row is None or len(row) < 2 or row[0] is None or row[1] is None:
                return {
                    "put_call_ratio": None,
                    "signal": None,
                    "bonus_pts": 0.0,
                    "data_unavailable": True,
                    "reason": "options_chains data not found",
                }

            put_vol, call_vol = float(row[0]), float(row[1])
            if call_vol == 0:
                return {
                    "put_call_ratio": None,
                    "signal": None,
                    "bonus_pts": 0.0,
                    "data_unavailable": True,
                    "reason": "no_call_volume_data",
                }

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

        return self._with_cursor(_fetch_pc_ratio)  # type: ignore[no-any-return]

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

        def _fetch_implied_move(cur: Any) -> dict[str, Any]:
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
            if iv_row is None or len(iv_row) < 1 or iv_row[0] is None:
                return {
                    "implied_move_pct": None,
                    "vs_base_depth_pct": None,
                    "underpriced": False,
                    "bonus_pts": 0.0,
                    "data_unavailable": True,
                    "reason": "options_chains data not found",
                }

            current_iv, days_to_exp = float(iv_row[0]), float(iv_row[1])
            if days_to_exp <= 0:
                raise ValueError(
                    f"{symbol}: Invalid days-to-expiration ({days_to_exp}) on {eval_date}. "
                    f"Options chains data is expired or corrupted. "
                    f"Cannot calculate implied move with invalid time value."
                )

            implied_move = current_iv * (days_to_exp / 365.0) ** 0.5 * 100

            # Get base depth from technical analysis — required if we have IV data
            try:
                base_type = self.classify_base_type(symbol, eval_date)  # type: ignore[attr-defined]
                if base_type is None:
                    raise ValueError(
                        f"{symbol}: Base type classification unavailable — "
                        f"cannot evaluate implied move vs base depth. "
                        f"Options signal evaluation requires technical base analysis."
                    )

                base_depth = base_type.get("depth_pct")
                if base_depth is None:
                    raise ValueError(
                        f"{symbol}: Base depth missing from classification — "
                        f"cannot compare implied move to setup depth. "
                        f"Options signal evaluation requires complete base analysis."
                    )

                base_depth = float(base_depth)
            except ValueError:
                raise
            except (TypeError, AttributeError) as e:
                raise ValueError(
                    f"{symbol}: Failed to extract base depth: {e}. "
                    f"Options signal evaluation cannot proceed without technical base context."
                ) from e

            underpriced = implied_move < base_depth
            bonus_pts = 1.5 if underpriced else 0.0

            return {
                "implied_move_pct": round(implied_move, 2),
                "vs_base_depth_pct": round(base_depth, 2),
                "underpriced": underpriced,
                "bonus_pts": bonus_pts,
            }

        return self._with_cursor(_fetch_implied_move)  # type: ignore[no-any-return]
