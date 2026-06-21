"""
Live Performance Metrics — Compute Sharpe, win rate, expectancy, max drawdown.

Institutional traders measure performance in real-time against backtested metrics.
This module validates live performance against backtest baselines and detects drift.

Metrics computed:
- Rolling Sharpe ratio (252-day annualized from portfolio snapshots, includes unrealized gains/losses)
- Win rate and average R-multiple (closed trades only for historical consistency; see load_algo_performance_daily.py for all-inclusive win rate with open trades)
- Expectancy (E = (WR x Avg Win R) - (LR x Avg Loss R))
- Maximum drawdown from peak portfolio value
- Live vs. backtest comparison
"""

import json
import logging
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import psycopg2

from utils.db import DatabaseContext
from utils.metrics_calculator import MetricsCalculator
from utils.safe_data_conversion import safe_float


logger = logging.getLogger(__name__)


def _dec_round(val, places):
    if val is None or val == 0:
        return 0.0
    d = Decimal(str(val))
    return float(d.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP))


class LivePerformance:
    """Compute live performance metrics for institutional comparison."""

    def __init__(self, config):
        self.config = config

    def rolling_sharpe(self, lookback_days: int = 252) -> float | None:
        """Compute rolling Sharpe ratio from daily portfolio returns.

        H17 FIX: Includes unrealized gains/losses from open trades since
        total_portfolio_value in snapshots reflects current market value of all positions.

        Args:
            lookback_days: Days to look back (default 252 = 1 year)

        Returns:
            Annualized Sharpe ratio or None if insufficient data
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY snapshot_date ASC
                    """,
                    (lookback_days,),
                )
                rows = cur.fetchall()

            if len(rows) < 30:
                return None

            values = [safe_float(row[1], default=0.0, context=f"portfolio_value from row {i}") for i, row in enumerate(rows)]
            daily_returns = [(values[i] - values[i - 1]) / values[i - 1] if values[i - 1] > 0 else 0.0 for i in range(1, len(values))]

            return MetricsCalculator.calculate_sharpe_ratio(daily_returns)
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def win_rate(self, lookback_trades: int = 50) -> dict[str, float] | None:
        """Compute win rate and average R-multiple from closed trades.

        Args:
            lookback_trades: Number of recent closed trades to analyze

        Returns:
            dict with win_rate_pct, avg_win_r, avg_loss_r, win_count, loss_count
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN r_multiple > 0 THEN 1 ELSE 0 END) as win_count,
                        SUM(CASE WHEN r_multiple <= 0 THEN 1 ELSE 0 END) as loss_count,
                        AVG(CASE WHEN r_multiple > 0 THEN r_multiple ELSE NULL END) as avg_win_r,
                        AVG(CASE WHEN r_multiple <= 0 THEN r_multiple ELSE NULL END) as avg_loss_r,
                        AVG(CASE WHEN profit_loss_pct > 0 THEN profit_loss_pct ELSE NULL END) as avg_win_pct,
                        AVG(CASE WHEN profit_loss_pct <= 0 THEN profit_loss_pct ELSE NULL END) as avg_loss_pct
                    FROM (
                        SELECT
                            profit_loss_pct,
                            CASE
                                WHEN exit_r_multiple IS NOT NULL THEN exit_r_multiple
                                WHEN stop_loss_price IS NOT NULL
                                     AND stop_loss_price < entry_price
                                     AND entry_quantity > 0
                                    THEN profit_loss_dollars
                                         / NULLIF((entry_price - stop_loss_price)
                                                  * entry_quantity, 0)
                                ELSE NULL
                            END AS r_multiple
                        FROM algo_trades
                        WHERE status = 'closed'
                          AND exit_date >= CURRENT_DATE - INTERVAL '365 days'
                        ORDER BY exit_date DESC NULLS LAST
                        LIMIT %s
                    ) closed_trades
                    """,
                    (lookback_trades,),
                )
                row = cur.fetchone()

            if not row or row[0] == 0:
                return None

            (
                total,
                win_count,
                loss_count,
                avg_win_r,
                avg_loss_r,
                avg_win_pct,
                avg_loss_pct,
            ) = row
            win_count = win_count
            loss_count = loss_count
            avg_win_r = safe_float(avg_win_r, default=0.0, context="avg_win_r")
            avg_loss_r = abs(safe_float(avg_loss_r, default=0.0, context="avg_loss_r"))
            avg_win_pct = safe_float(avg_win_pct, default=0.0, context="avg_win_pct")
            avg_loss_pct = safe_float(avg_loss_pct, default=0.0, context="avg_loss_pct")

            win_rate_pct = (win_count / total * 100) if total > 0 else 0

            return {
                "win_rate_pct": _dec_round(win_rate_pct, 2),
                "win_count": int(win_count),
                "loss_count": int(loss_count),
                "avg_win_pct": _dec_round(avg_win_pct, 3),
                "avg_loss_pct": _dec_round(avg_loss_pct, 3),
                "avg_win_r": _dec_round(avg_win_r, 3),
                "avg_loss_r": _dec_round(avg_loss_r, 3),
            }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def expectancy(self, lookback_trades: int = 50) -> float | None:
        """Compute expectancy: E = (WR × Avg Win R) - (LR × Avg Loss R).

        Args:
            lookback_trades: Number of trades for calculation

        Returns:
            Expectancy in R-multiples
        """
        try:
            wr = self.win_rate(lookback_trades)
            if not wr:
                return None

            win_rate = wr["win_rate_pct"] / 100.0
            loss_rate = 1.0 - win_rate
            avg_win_r = wr["avg_win_r"]
            avg_loss_r = wr["avg_loss_r"]

            expectancy = (win_rate * avg_win_r) - (loss_rate * avg_loss_r)
            return _dec_round(expectancy, 4)
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def max_drawdown(self) -> float | None:
        """Compute maximum drawdown from peak portfolio value.

        Returns:
            Max drawdown as percentage (e.g., -15.5 = 15.5% down from peak)
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - INTERVAL '365 days'
                    ORDER BY snapshot_date ASC
                    """)
                rows = cur.fetchall()

            if len(rows) < 2:
                return None

            values = [safe_float(row[1], context=f"portfolio_value from row {i}") for i, row in enumerate(rows)]
            return MetricsCalculator.calculate_max_drawdown(values)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def rolling_sortino(self, lookback_days: int = 252) -> float | None:
        """Annualized Sortino ratio — penalizes only downside volatility.

        More appropriate than Sharpe for directional swing strategies where
        upside volatility is desirable.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY snapshot_date ASC
                    """,
                    (lookback_days,),
                )
                rows = cur.fetchall()

            if len(rows) < 30:
                return None

            values = [safe_float(r[0], default=0.0, context=f"portfolio_value from row {i}") for i, r in enumerate(rows)]
            daily_returns = [(values[i] - values[i - 1]) / values[i - 1] if values[i - 1] > 0 else 0.0 for i in range(1, len(values))]

            return MetricsCalculator.calculate_sortino_ratio(daily_returns)
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def calmar_ratio(self, lookback_days: int = 252) -> float | None:
        """Calmar ratio = annualized return / abs(max drawdown).

        Standard benchmark for trend-following strategies. Higher is better.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY snapshot_date ASC
                    """,
                    (lookback_days,),
                )
                rows = cur.fetchall()

            if len(rows) < 30:
                return None

            values = [safe_float(r[0], context=f"portfolio_value from row {i}") for i, r in enumerate(rows)]
            return MetricsCalculator.calculate_calmar_ratio(values)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def backtest_vs_live_comparison(self) -> dict[str, Any] | None:
        """Compare live metrics to backtest reference metrics.

        Returns:
            dict with live/backtest Sharpe, win rate, etc. and ratio
        """
        try:
            # Load backtest reference metrics
            ref_file = Path(__file__).parent / "tests" / "backtest" / "reference_metrics.json"
            if not ref_file.exists():
                logger.info(f"Performance: Reference metrics not found at {ref_file}")
                return None

            with open(ref_file) as f:
                backtest_metrics = json.load(f)

            # Compute live metrics
            live_sharpe = self.rolling_sharpe(252)
            live_wr = self.win_rate(50)
            live_expectancy = self.expectancy(50)
            live_max_dd = self.max_drawdown()

            if not all([live_sharpe, live_wr, live_max_dd]):
                return None

            backtest_sharpe = backtest_metrics.get("sharpe_ratio")
            backtest_wr = backtest_metrics.get("win_rate_pct")

            live_win_rate = live_wr.get("win_rate_pct") if isinstance(live_wr, dict) else live_wr
            return {
                "live_sharpe": live_sharpe,
                "backtest_sharpe": backtest_sharpe,
                "sharpe_ratio": (live_sharpe / backtest_sharpe if backtest_sharpe else None),
                "live_win_rate": live_win_rate,
                "backtest_win_rate": backtest_wr,
                "win_rate_ratio": (live_win_rate / backtest_wr if (live_win_rate and backtest_wr) else None),
                "live_expectancy": live_expectancy,
                "live_max_dd": live_max_dd,
                "backtest_max_dd": backtest_metrics.get("max_drawdown_pct"),
            }
        except (FileNotFoundError, OSError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def generate_daily_report(self, report_date: date | None = None) -> dict[str, Any]:
        """Generate comprehensive daily performance report.

        Args:
            report_date: Date to report on (default today)

        Returns:
            dict with all metrics for the day
        """
        try:
            if not report_date:
                report_date = date.today()

            logger.info(f"Generating daily performance report for {report_date}")

            # Compute all metrics (each handles its own connection)
            sharpe = self.rolling_sharpe(252)
            logger.debug(f"  Sharpe ratio: {sharpe}")
            sortino = self.rolling_sortino(252)
            logger.debug(f"  Sortino ratio: {sortino}")
            calmar = self.calmar_ratio(252)
            logger.debug(f"  Calmar ratio: {calmar}")
            wr = self.win_rate(50)
            logger.debug(f"  Win rate: {wr['win_rate_pct'] if wr else None}%")
            expectancy = self.expectancy(50)
            logger.debug(f"  Expectancy: {expectancy}")
            max_dd = self.max_drawdown()
            logger.debug(f"  Max drawdown: {max_dd}%")
            comparison = self.backtest_vs_live_comparison()
            logger.debug(f"  Backtest vs live: {comparison}")

            result = {
                "report_date": report_date,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "rolling_sharpe_252d": sharpe,
                "rolling_sortino_252d": sortino,
                "calmar_ratio": calmar,
                "status": "ok",
            }

            if wr:
                result.update(
                    {
                        "win_rate_50t": wr["win_rate_pct"],
                        "avg_win_r_50t": wr["avg_win_r"],
                        "avg_loss_r_50t": wr["avg_loss_r"],
                        "expectancy": expectancy,
                    }
                )

            if max_dd is not None:
                result["max_drawdown_pct"] = max_dd

            if comparison:
                result["live_vs_backtest"] = comparison
                # Flag warning if Sharpe drops below 70% of backtest
                sharpe_ratio = comparison.get("sharpe_ratio")
                if sharpe_ratio and sharpe_ratio < 0.7:
                    result["status"] = "warning"
                    result["warning"] = (
                        f"Live Sharpe ({sharpe:.2f}) below 70% of backtest ({comparison['backtest_sharpe']:.2f})"
                    )
                    logger.warning(f"  Performance warning: {result['warning']}")

            # Upsert into database (insert or replace if already exists for this date)
            try:
                sharpe_val = safe_float(sharpe, default=None, context="sharpe_ratio") if sharpe is not None else None
                safe_float(sortino, default=None, context="sortino_ratio") if sortino is not None else None
                safe_float(calmar, default=None, context="calmar_ratio") if calmar is not None else None
                win_rate_val = safe_float(wr["win_rate_pct"], default=None, context="win_rate") if wr else None
                avg_win_r_val = safe_float(wr["avg_win_r"], default=None, context="avg_win_r") if wr else None
                avg_loss_r_val = safe_float(wr["avg_loss_r"], default=None, context="avg_loss_r") if wr else None
                expectancy_val = safe_float(expectancy, default=None, context="expectancy") if expectancy is not None else None
                max_dd_val = safe_float(max_dd, default=None, context="max_drawdown") if max_dd is not None else None

                with DatabaseContext("write") as cur:
                    cur.execute(
                        """
                        INSERT INTO algo_performance_daily (
                            report_date, rolling_sharpe_252d,
                            win_rate_50t, avg_win_r_50t, avg_loss_r_50t, expectancy,
                            max_drawdown_pct
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (report_date) DO UPDATE SET
                            rolling_sharpe_252d = EXCLUDED.rolling_sharpe_252d,
                            win_rate_50t = EXCLUDED.win_rate_50t,
                            avg_win_r_50t = EXCLUDED.avg_win_r_50t,
                            avg_loss_r_50t = EXCLUDED.avg_loss_r_50t,
                            expectancy = EXCLUDED.expectancy,
                            max_drawdown_pct = EXCLUDED.max_drawdown_pct
                        """,
                        (
                            report_date,
                            sharpe_val,
                            win_rate_val,
                            avg_win_r_val,
                            avg_loss_r_val,
                            expectancy_val,
                            max_dd_val,
                        ),
                    )
                    logger.info(
                        f"[OK] Performance report persisted: sharpe={sharpe_val}, wr={win_rate_val}%, max_dd={max_dd_val}%"
                    )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"Failed to persist performance report: {e}", exc_info=True)

            return result

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"Performance: generate_daily_report failed: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
