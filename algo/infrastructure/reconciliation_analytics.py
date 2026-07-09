#!/usr/bin/env python3
"""Analytics computation for trade reconciliation.

Extracted from DailyReconciliation to separate analytics concerns from
position reconciliation logic.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ReconciliationAnalytics:
    """Computes analytics metrics from reconciliation data.

    Responsibilities:
    - Daily performance metrics (win rate, P&L, Sharpe ratio)
    - Closed trade analysis (R-multiples, profit factors, etc.)
    - Trade streak tracking
    """

    def __init__(self) -> None:
        """Initialize analytics computer."""

    def compute_analytics_metrics(self, cur: Any) -> dict[str, Any]:
        """Compute daily analytics: Information Coefficient (IC) and expectancy.

        Returns dict with:
        - ic: {valid, ic, trade_count, alert}
        - expectancy: {valid, expectancy, win_rate, kelly_fraction, alert}

        These metrics help monitor strategy performance and edge.
        """
        result: dict[str, Any] = {
            "ic": {"valid": False},
            "expectancy": {"valid": False},
        }

        # Compute Information Coefficient (correlation between signal quality and P&L)
        try:
            cur.execute("""
                SELECT
                    CORR(signal_quality_score::FLOAT, profit_loss_pct) as ic,
                    COUNT(*) as trade_count
                FROM algo_trades
                WHERE status IN ('closed', 'exited')
                  AND exit_date IS NOT NULL
                  AND signal_quality_score IS NOT NULL
                  AND profit_loss_pct IS NOT NULL
            """)
            row = cur.fetchone()
            if row and row[0] is not None and row[1] >= 10:
                ic = float(row[0])
                trade_count = int(row[1])
                alert = None
                if ic < 0.1:
                    alert = "Warning: IC < 0.1 indicates weak signal quality"
                result["ic"] = {
                    "valid": True,
                    "ic": ic,
                    "trade_count": trade_count,
                    "alert": alert,
                }
        except Exception as e:
            logger.warning(f"Could not compute IC: {e}")

        # Compute expectancy and Kelly Fraction
        try:
            cur.execute("""
                SELECT
                    SUM(CASE WHEN profit_loss_dollars > 0 THEN 1 ELSE 0 END)::FLOAT / COUNT(*) as win_rate,
                    SUM(CASE WHEN profit_loss_dollars > 0 THEN profit_loss_pct ELSE 0 END) / NULLIF(SUM(CASE WHEN profit_loss_dollars > 0 THEN 1 ELSE 0 END), 0) as avg_win_pct,
                    SUM(CASE WHEN profit_loss_dollars <= 0 THEN ABS(profit_loss_pct) ELSE 0 END) / NULLIF(SUM(CASE WHEN profit_loss_dollars <= 0 THEN 1 ELSE 0 END), 0) as avg_loss_pct,
                    COUNT(*) as total_trades
                FROM algo_trades
                WHERE status IN ('closed', 'exited')
                  AND exit_date IS NOT NULL
                  AND profit_loss_dollars IS NOT NULL
                  AND profit_loss_pct IS NOT NULL
            """)
            row = cur.fetchone()
            if row and row[3] >= 5:  # Need at least 5 trades
                win_rate = float(row[0]) if row[0] else 0.0
                avg_win = float(row[1]) if row[1] else 0.0
                avg_loss = float(row[2]) if row[2] else 0.0

                if win_rate > 0 and avg_loss > 0:
                    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
                    kelly_fraction = (win_rate - ((1 - win_rate) * avg_loss / avg_win)) / 1.0 if avg_win > 0 else 0
                else:
                    expectancy = 0.0
                    kelly_fraction = 0.0

                alert = None
                if expectancy < 0:
                    alert = f"Negative expectancy: {expectancy:.4f}% - Strategy is losing"
                elif win_rate < 0.40:
                    alert = f"Win rate below 40%: {win_rate * 100:.1f}%"

                result["expectancy"] = {
                    "valid": True,
                    "expectancy": expectancy,
                    "win_rate": win_rate,
                    "kelly_fraction": max(0, kelly_fraction),
                    "alert": alert,
                }
        except Exception as e:
            logger.warning(f"Could not compute expectancy: {e}")

        return result

    def compute_closed_trade_metrics(self, cur: Any) -> dict[str, Any]:
        """Compute metrics from all closed trades: MAE/MFE, win rate, R-multiples, profit factor.

        Returns dict with:
        - win_count: int, number of winning trades
        - loss_count: int, number of losing trades
        - win_rate: float, win rate %
        - profit_factor: float, gross_profit / abs(gross_loss)
        - avg_r_multiple: float, average R-multiple of closed trades
        - best_trade_pct: float, best trade return %
        - worst_trade_pct: float, worst trade return %
        - best_mae: float, best minimum adverse excursion
        - best_mfe: float, best maximum favorable excursion
        - reason: str, summary of metrics

        These are used for dashboard E3 analytics and strategy validation.
        """
        result: dict[str, Any] = {
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_r_multiple": 0.0,
            "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
            "best_mae": 0.0,
            "best_mfe": 0.0,
            "reason": "Unable to compute closed trade metrics",
        }

        try:
            # Fetch closed trade statistics
            cur.execute("""
                SELECT
                    SUM(CASE WHEN profit_loss_dollars > 0 THEN 1 ELSE 0 END)::INTEGER as wins,
                    SUM(CASE WHEN profit_loss_dollars <= 0 THEN 1 ELSE 0 END)::INTEGER as losses,
                    SUM(CASE WHEN profit_loss_dollars > 0 THEN profit_loss_dollars ELSE 0 END) as gross_profit,
                    SUM(CASE WHEN profit_loss_dollars <= 0 THEN ABS(profit_loss_dollars) ELSE 0 END) as gross_loss,
                    AVG(CASE WHEN exit_r_multiple IS NOT NULL THEN exit_r_multiple END) as avg_r_multiple,
                    MAX(profit_loss_pct) as best_trade_pct,
                    MIN(profit_loss_pct) as worst_trade_pct,
                    AVG(mae_pct) as avg_mae,
                    AVG(mfe_pct) as avg_mfe,
                    COUNT(*) as total_closed
                FROM algo_trades
                WHERE status IN ('closed', 'exited')
                  AND exit_date IS NOT NULL
                  AND profit_loss_dollars IS NOT NULL
            """)
            row = cur.fetchone()

            if row and row[9] and row[9] > 0:  # total_closed > 0
                wins = int(row[0]) if row[0] else 0
                losses = int(row[1]) if row[1] else 0
                gross_profit = float(row[2]) if row[2] else 0.0
                gross_loss = float(row[3]) if row[3] else 0.0
                total_closed = int(row[9])

                # CRITICAL: Do NOT return 0.0 for win_rate/profit_factor as metrics
                # 0% win rate (all losers) ≠ "no trades" (data unavailable).
                # Explicitly validate data before returning metrics.
                if total_closed <= 0:
                    raise ValueError(f"Expected total_closed > 0 but got {total_closed}")
                win_rate = wins / total_closed

                if gross_loss <= 0:
                    # Profit factor undefined when gross_loss ≤ 0 (no losing trades or all breakeven)
                    # This is a data quality issue, not a metric to return as 0.0 (which means "no profit")
                    raise ValueError(
                        f"Cannot calculate profit_factor: gross_loss is {gross_loss} (expected > 0). "
                        f"Closed trades: {wins}W {losses}L. This suggests a data quality issue."
                    )
                profit_factor = gross_profit / gross_loss

                result.update(
                    {
                        "win_count": wins,
                        "loss_count": losses,
                        "win_rate": win_rate,
                        "profit_factor": profit_factor,
                        "avg_r_multiple": float(row[4]) if row[4] else 0.0,
                        "best_trade_pct": float(row[5]) if row[5] else 0.0,
                        "worst_trade_pct": float(row[6]) if row[6] else 0.0,
                        "best_mae": float(row[7]) if row[7] else 0.0,
                        "best_mfe": float(row[8]) if row[8] else 0.0,
                        "reason": f"Closed trades: {wins}W {losses}L (win rate {win_rate * 100:.1f}%), "
                        f"Profit factor {profit_factor:.2f}x, Avg R-multiple {float(row[4]) if row[4] else 0.0:.2f}",
                    }
                )
            else:
                result["reason"] = "No closed trades yet"

        except Exception as e:
            logger.warning(f"Could not compute closed trade metrics: {e}")

        return result

    def compute_trade_streak(self, cur: Any) -> int:
        """Compute current win/loss streak from recent closed trades.

        Returns positive number for win streak, negative for loss streak.
        Returns 0 if no closed trades or trades are breakeven.
        """
        try:
            cur.execute("""
                SELECT profit_loss_dollars
                FROM algo_trades
                WHERE status IN ('closed', 'exited')
                  AND exit_date IS NOT NULL
                  AND profit_loss_dollars IS NOT NULL
                ORDER BY exit_date DESC
                LIMIT 20
            """)
            rows = cur.fetchall()

            if not rows:
                return 0

            streak = 0
            current_direction = None  # 'win' or 'loss'

            for row in rows:
                pnl = float(row[0])
                if pnl > 0:
                    direction = "win"
                elif pnl < 0:
                    direction = "loss"
                else:
                    # Breakeven trade breaks the streak
                    break

                if current_direction is None:
                    current_direction = direction
                    streak = 1 if direction == "win" else -1
                elif current_direction == direction:
                    streak += 1 if direction == "win" else -1
                else:
                    # Direction changed, streak ends
                    break

            return streak
        except Exception as e:
            logger.warning(f"Could not compute trade streak: {e}")
            return 0
