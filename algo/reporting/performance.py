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
from typing import Any, cast

import psycopg2

from utils.db import DatabaseContext
from utils.metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)


def _dec_round(val: Any, places: int) -> float:
    """Round decimal to specified places. Fail-fast if data is missing.

    Raises:
        ValueError: If val is None (missing data) — fail-fast governance
    """
    if val is None:
        raise ValueError(
            "Cannot round None value (missing financial data). Data completeness is critical for performance metrics."
        )
    if val == 0:
        return 0.0
    d = Decimal(str(val))
    return float(d.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP))


class LivePerformance:
    """Compute live performance metrics for institutional comparison."""

    def __init__(self, config: Any) -> None:
        self.config = config

    def rolling_sharpe(self, lookback_days: int = 252) -> float | None:
        """Compute rolling Sharpe ratio from daily portfolio returns. Ramp-up tolerant.

        H17 FIX: Includes unrealized gains/losses from open trades since
        total_portfolio_value in snapshots reflects current market value of all positions.

        During initial ramp-up (< 30 snapshots): Uses available data for visibility.
        After stabilization (>= 30): Full 252-day history required.

        Args:
            lookback_days: Days to look back (default 252 = 1 year)

        Returns:
            Annualized Sharpe ratio

        Raises:
            ValueError: If insufficient data (< 5 snapshots during ramp-up).
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

            min_snapshots = 5  # Accept minimal data during ramp-up (better than None)
            if len(rows) < min_snapshots:
                raise ValueError(
                    f"Cannot calculate Sharpe ratio: insufficient portfolio snapshots ({len(rows)} found, need {min_snapshots}+). "
                    f"Portfolio history too short ({lookback_days} days). "
                    f"Sharpe is critical for risk assessment — cannot use default."
                )

            values: list[float] = []
            for i, row in enumerate(rows):
                val = float(row[1])
                if val is None:
                    raise ValueError(f"Portfolio snapshot {i} has missing/invalid value")
                values.append(val)
            daily_returns: list[float] = []
            for i in range(1, len(values)):
                if values[i - 1] > 0:
                    daily_returns.append((values[i] - values[i - 1]) / values[i - 1])

            return MetricsCalculator.calculate_sharpe_ratio(daily_returns)
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def win_rate(self, lookback_trades: int = 50) -> dict[str, float] | None:
        """Compute win rate and average R-multiple from closed trades. FAIL-FAST on no trades.

        Args:
            lookback_trades: Number of recent closed trades to analyze

        Returns:
            dict with win_rate_pct, avg_win_r, avg_loss_r, win_count, loss_count

        Raises:
            ValueError: If no closed trades found. Win rate is critical metric — cannot use default.
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

            if row is None or len(row) < 1 or row[0] == 0:
                raise ValueError(
                    "Cannot calculate win rate: no closed trades found in past 365 days. "
                    "Win rate is critical for performance evaluation — cannot use default zero."
                )

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
            avg_win_r = float(avg_win_r)
            avg_loss_r_val = float(avg_loss_r)
            avg_win_pct = float(avg_win_pct)
            avg_loss_pct = float(avg_loss_pct)

            if avg_win_r is None or avg_loss_r_val is None:
                raise ValueError(
                    f"CRITICAL: Win/loss R-multiples missing (avg_win_r={avg_win_r}, avg_loss_r={avg_loss_r_val}). "
                    f"Cannot calculate expectancy without valid R-multiple data."
                )
            avg_loss_r = abs(avg_loss_r_val)
            if avg_win_pct is None:
                avg_win_pct = 0.0
            if avg_loss_pct is None:
                avg_loss_pct = 0.0

            if total <= 0:
                raise ValueError(f"CRITICAL: No trades for expectancy calculation (total={total})")
            win_rate_pct = win_count / total * 100

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
        """Compute expectancy: E = (WR x Avg Win R) - (LR x Avg Loss R). FAIL-FAST on insufficient data.

        Args:
            lookback_trades: Number of trades for calculation

        Returns:
            Expectancy in R-multiples

        Raises:
            ValueError: If win_rate calculation fails (propagated from win_rate method)
        """
        try:
            wr = self.win_rate(lookback_trades)
            if not wr:
                raise ValueError(
                    "Expectancy calculation failed: win_rate returned empty result. "
                    "Cannot compute expectancy without valid win rate metrics."
                )

            win_rate = wr["win_rate_pct"] / 100.0
            loss_rate = 1.0 - win_rate
            avg_win_r = wr["avg_win_r"]
            avg_loss_r = wr["avg_loss_r"]

            expectancy = (win_rate * avg_win_r) - (loss_rate * avg_loss_r)
            return _dec_round(expectancy, 4)
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def max_drawdown(self) -> float | None:
        """Compute maximum drawdown from peak portfolio value. FAIL-FAST on insufficient data.

        Returns:
            Max drawdown as percentage (e.g., -15.5 = 15.5% down from peak)

        Raises:
            ValueError: If insufficient snapshots (< 2). Max drawdown is critical risk metric.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date ASC
                    """)
                rows = cur.fetchall()

            min_snapshots = 2
            if len(rows) < min_snapshots:
                raise ValueError(
                    f"Cannot calculate max drawdown: insufficient portfolio snapshots ({len(rows)} found, need {min_snapshots}+). "
                    f"Need historical portfolio values to assess peak-to-trough decline. "
                    f"Max drawdown is critical for risk assessment — cannot use default."
                )

            values = []
            for i, row in enumerate(rows):
                val = float(row[1])
                if val is None:
                    raise ValueError(f"Portfolio snapshot {i} has missing/invalid value for max_drawdown calculation")
                values.append(val)
            return cast(float, MetricsCalculator.calculate_max_drawdown(values))
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def rolling_sortino(self, lookback_days: int = 252) -> float | None:
        """Annualized Sortino ratio — penalizes only downside volatility.

        More appropriate than Sharpe for directional swing strategies where
        upside volatility is desirable.

        During initial ramp-up (< 30 snapshots): Uses available data for visibility.

        Raises:
            ValueError: If insufficient data (< 5 snapshots during ramp-up).
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

            min_snapshots = 5  # Accept minimal data during ramp-up
            if len(rows) < min_snapshots:
                raise ValueError(
                    f"Cannot calculate Sortino ratio: insufficient portfolio snapshots ({len(rows)} found, need {min_snapshots}+). "
                    f"Portfolio history too short ({lookback_days} days). "
                    f"Sortino is important for evaluating downside risk — cannot use default."
                )

            values = [float(r[0]) for i, r in enumerate(rows)]
            daily_returns: list[float] = []
            for i in range(1, len(values)):
                if values[i - 1] > 0:
                    daily_returns.append((values[i] - values[i - 1]) / values[i - 1])

            return MetricsCalculator.calculate_sortino_ratio(daily_returns)
        except ValueError:
            raise
        except (ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def calmar_ratio(self, lookback_days: int = 252) -> float | None:
        """Calmar ratio = annualized return / abs(max drawdown).

        Standard benchmark for trend-following strategies. Higher is better.

        During initial ramp-up (< 30 snapshots): Uses available data for visibility.

        Raises:
            ValueError: If insufficient data (< 5 snapshots during ramp-up).
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

            min_snapshots = 5  # Accept minimal data during ramp-up
            if len(rows) < min_snapshots:
                raise ValueError(
                    f"Cannot calculate Calmar ratio: insufficient portfolio snapshots ({len(rows)} found, need {min_snapshots}+). "
                    f"Portfolio history too short ({lookback_days} days). "
                    f"Calmar is standard benchmark for trend strategies — cannot use default."
                )

            values = [float(r[0]) for i, r in enumerate(rows)]
            return MetricsCalculator.calculate_calmar_ratio(values)
        except ValueError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def backtest_vs_live_comparison(self) -> dict[str, Any]:
        """Compare live metrics to backtest reference metrics.

        Returns:
            dict with live/backtest Sharpe, win rate, etc. and ratio,
            or data_unavailable marker if comparison cannot be computed.

        Raises:
            FileNotFoundError if reference metrics file is missing.
        """
        try:
            # Load backtest reference metrics
            ref_file = Path(__file__).parent / "tests" / "backtest" / "reference_metrics.json"
            if not ref_file.exists():
                raise FileNotFoundError(
                    f"Backtest reference metrics not found at {ref_file}. "
                    f"Cannot compute live-to-backtest comparison without reference data."
                )

            with open(ref_file) as f:
                backtest_metrics = json.load(f)

            # Compute live metrics
            live_sharpe = self.rolling_sharpe(252)
            live_wr = self.win_rate(50)
            live_expectancy = self.expectancy(50)
            live_max_dd = self.max_drawdown()

            if not all([live_sharpe, live_wr, live_max_dd]):
                return {
                    "data_unavailable": True,
                    "reason": "incomplete_live_metrics",
                    "missing": [
                        name
                        for name, val in [
                            ("sharpe", live_sharpe),
                            ("win_rate", live_wr),
                            ("max_drawdown", live_max_dd),
                        ]
                        if not val
                    ],
                }

            backtest_sharpe = backtest_metrics.get("sharpe_ratio")
            backtest_wr = backtest_metrics.get("win_rate_pct")

            live_win_rate = live_wr.get("win_rate_pct") if isinstance(live_wr, dict) else live_wr
            if backtest_sharpe is None or backtest_sharpe == 0:
                logger.warning(
                    "[PERFORMANCE_METRICS] Backtest Sharpe ratio is missing or zero. "
                    "Cannot compute live-to-backtest Sharpe comparison."
                )
                sharpe_ratio = None
            elif live_sharpe is None:
                logger.warning(
                    "[PERFORMANCE_METRICS] Live Sharpe ratio is missing. "
                    "Cannot compute live-to-backtest Sharpe comparison."
                )
                sharpe_ratio = None
            else:
                sharpe_ratio = live_sharpe / backtest_sharpe

            return {
                "live_sharpe": live_sharpe,
                "backtest_sharpe": backtest_sharpe,
                "sharpe_ratio": sharpe_ratio,
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
            try:
                sortino = self.rolling_sortino(252)
                logger.debug(f"  Sortino ratio: {sortino}")
            except ValueError as e:
                logger.warning(f"  Sortino ratio unavailable: {e}")
                sortino = None
            try:
                calmar = self.calmar_ratio(252)
                logger.debug(f"  Calmar ratio: {calmar}")
            except ValueError as e:
                logger.warning(f"  Calmar ratio unavailable: {e}")
                calmar = None
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
                sharpe_val = float(sharpe) if sharpe is not None else None
                sortino_val = float(sortino) if sortino is not None else None
                calmar_val = float(calmar) if calmar is not None else None
                win_rate_val = float(wr["win_rate_pct"]) if wr else None
                avg_win_r_val = float(wr["avg_win_r"]) if wr else None
                avg_loss_r_val = float(wr["avg_loss_r"]) if wr else None
                expectancy_val = float(expectancy) if expectancy is not None else None
                max_dd_val = float(max_dd) if max_dd is not None else None

                with DatabaseContext("write") as cur:
                    cur.execute(
                        """
                        INSERT INTO algo_performance_daily (
                            report_date, rolling_sharpe_252d, rolling_sortino_252d, calmar_ratio,
                            win_rate_50t, avg_win_r_50t, avg_loss_r_50t, expectancy,
                            max_drawdown_pct
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (report_date) DO UPDATE SET
                            rolling_sharpe_252d = EXCLUDED.rolling_sharpe_252d,
                            rolling_sortino_252d = EXCLUDED.rolling_sortino_252d,
                            calmar_ratio = EXCLUDED.calmar_ratio,
                            win_rate_50t = EXCLUDED.win_rate_50t,
                            avg_win_r_50t = EXCLUDED.avg_win_r_50t,
                            avg_loss_r_50t = EXCLUDED.avg_loss_r_50t,
                            expectancy = EXCLUDED.expectancy,
                            max_drawdown_pct = EXCLUDED.max_drawdown_pct
                        """,
                        (
                            report_date,
                            sharpe_val,
                            sortino_val,
                            calmar_val,
                            win_rate_val,
                            avg_win_r_val,
                            avg_loss_r_val,
                            expectancy_val,
                            max_dd_val,
                        ),
                    )
                    logger.info(
                        f"[OK] Performance report persisted: sharpe={sharpe_val}, sortino={sortino_val}, calmar={calmar_val}, wr={win_rate_val}%, max_dd={max_dd_val}%"
                    )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"Failed to persist performance report: {e}", exc_info=True)

            return result

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"Performance: generate_daily_report failed: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
