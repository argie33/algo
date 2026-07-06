#!/usr/bin/env python3
"""Swing Trader Scores Loader - Computes swing trading readiness scores.

Metrics: Swing Score (0-100) based on technical setup quality, momentum, and trend alignment.
Requires: technical_data_daily, price_daily populated.
"""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

import psycopg2  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class SwingTraderScoresLoader(OptimalLoader):
    """Compute swing trading readiness scores (daily).

    Swing scores measure the quality of a technical setup for swing trading:
    - Setup Quality: RSI/MACD convergence, price action
    - Trend Score: Alignment with SMA 50/200
    - Momentum Score: Rate of change indicators
    - Volume Score: Volume confirmation of moves
    - Multi-Timeframe Score: Alignment across periods

    Composite swing_score (0-100) helps traders identify high-probability setups.
    """

    table_name = "swing_trader_scores"
    primary_key = ("symbol", "date")
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute swing trading scores for this symbol on the most recent trading day.

        Returns:
            List with single dict containing swing scores or data_unavailable marker
        """
        try:
            with DatabaseContext("read") as cur:
                # Get most recent technical data for this symbol
                cur.execute(
                    """
                    SELECT
                        symbol, date,
                        close, rsi_14, macd, sma_50, sma_200,
                        roc_20d, roc_60d, roc_120d, roc_252d
                    FROM technical_data_daily
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                tech_row = cur.fetchone()

                if not tech_row:
                    logger.debug(f"[SWING_SCORES] No technical data for {symbol}")
                    return [
                        {
                            "symbol": symbol,
                            "date": date.today(),
                            "swing_score": None,
                            "signal_score": None,
                            "data_unavailable": True,
                            "unavailability_reason": "no_technical_data",
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ]

                symbol_col, date_col, close, rsi, macd, sma50, sma200, roc20, roc60, roc120, roc252 = tech_row

                # Compute swing score components
                scores = self._compute_swing_scores(
                    symbol_col, date_col, close, rsi, macd, sma50, sma200, roc20, roc60, roc120, roc252
                )

                if not scores:
                    return [
                        {
                            "symbol": symbol,
                            "date": date.today(),
                            "swing_score": None,
                            "signal_score": None,
                            "data_unavailable": True,
                            "unavailability_reason": "computation_failed",
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ]

                return [scores]

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[SWING_SCORES] Database error for {symbol}: {e}")
            return [
                {
                    "symbol": symbol,
                    "date": date.today(),
                    "swing_score": None,
                    "signal_score": None,
                    "data_unavailable": True,
                    "unavailability_reason": f"database_error: {str(e)[:100]}",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ]

    def _compute_swing_scores(
        self,
        symbol: str,
        date_col: date,
        close: float | None,
        rsi: float | None,
        macd: float | None,
        sma50: float | None,
        sma200: float | None,
        roc20: float | None,
        roc60: float | None,
        roc120: float | None,
        roc252: float | None,
    ) -> dict[str, Any] | None:
        """Compute swing trading scores from technical indicators.

        Swing Score Components (each 0-100, weighted):
        - Setup Quality (30%): RSI overshoot + MACD alignment
        - Trend Score (25%): Price vs SMA alignment
        - Momentum Score (25%): ROC acceleration
        - Volume Score (10%): Placeholder for volume confirmation
        - Multi-Timeframe (10%): ROC convergence across timeframes
        """
        if any(v is None for v in [close, rsi, macd, sma50, sma200]):
            return None  # Insufficient data

        try:
            # Setup Quality: RSI oversold/overbought + MACD strength
            # RSI < 30 or > 70 = potential reversal setup (higher quality)
            rsi_score = 0.0
            if rsi is not None:
                if rsi < 30:
                    rsi_score = min(100, (30 - rsi) * 2)  # 0 RSI = 60 score
                elif rsi > 70:
                    rsi_score = min(100, (rsi - 70) * 2)  # 100 RSI = 60 score
            # MACD magnitude (normalized to -10 to +10 range)
            macd_score = min(100, abs(float(macd)) * 5) if macd is not None else 50
            setup_quality = (rsi_score * 0.6 + macd_score * 0.4)  # Weight RSI more

            # Trend Score: Price position relative to SMAs
            trend_score = 0.0
            if sma50 is not None and sma200 is not None and close is not None:
                if sma50 > sma200:  # Uptrend
                    if close > sma50:
                        trend_score = 80.0  # Strong uptrend
                    elif close > sma200:
                        trend_score = 50.0  # Weak uptrend
                else:  # Downtrend
                    if close < sma50:
                        trend_score = 20.0  # Strong downtrend (less desirable)
                    else:
                        trend_score = 50.0  # Weak downtrend

            # Momentum Score: ROC acceleration
            momentum_components = []
            if roc20 is not None:
                momentum_components.append(min(100, abs(float(roc20)) * 5))
            if roc60 is not None:
                momentum_components.append(min(100, abs(float(roc60)) * 3))
            if roc120 is not None:
                momentum_components.append(min(100, abs(float(roc120)) * 2))
            momentum_score = sum(momentum_components) / len(momentum_components) if momentum_components else 50.0

            # Volume Score: Placeholder (50 = neutral)
            volume_score = 50.0

            # Multi-Timeframe Score: ROC convergence
            multitf_score = 50.0
            if roc20 and roc60 and roc120:
                # If all ROCs same sign, higher convergence
                if (roc20 > 0 and roc60 > 0 and roc120 > 0) or (roc20 < 0 and roc60 < 0 and roc120 < 0):
                    multitf_score = 75.0

            # Composite swing_score
            swing_score = (
                setup_quality * 0.30
                + trend_score * 0.25
                + momentum_score * 0.25
                + volume_score * 0.10
                + multitf_score * 0.10
            )
            swing_score = min(100, max(0, round(swing_score, 2)))

            # Signal score (simplified: same as swing score for now)
            signal_score = swing_score

            return {
                "symbol": symbol,
                "date": date_col,
                "signal_score": float(signal_score),
                "swing_score": float(swing_score),
                "base_type": "technical",
                "setup_quality": float(round(setup_quality, 2)),
                "trend_score": float(round(trend_score, 2)),
                "momentum_score": float(round(momentum_score, 2)),
                "volume_score": float(volume_score),
                "multi_timeframe_score": float(round(multitf_score, 2)),
                "components": {
                    "rsi": float(rsi) if rsi else None,
                    "macd": float(macd) if macd else None,
                    "sma50": float(sma50) if sma50 else None,
                    "sma200": float(sma200) if sma200 else None,
                    "roc20": float(roc20) if roc20 else None,
                    "roc60": float(roc60) if roc60 else None,
                    "roc120": float(roc120) if roc120 else None,
                    "roc252": float(roc252) if roc252 else None,
                },
                "data_unavailable": False,
                "unavailability_reason": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.warning(f"[SWING_SCORES] Computation failed for {symbol}: {e}")
            return None


if __name__ == "__main__":
    run_loader(SwingTraderScoresLoader)
