#!/usr/bin/env python3

import logging
from datetime import date as _date
from typing import Any

import psycopg2

from utils.db import DatabaseContext
from utils.safe_data_conversion import safe_float


logger = logging.getLogger(__name__)


class DailyFinanceReport:
    """Generate institutional daily finance report."""

    def __init__(self):
        from algo.orchestration import RegimeManager

        self.regime_mgr = RegimeManager()

    def generate(self, report_date: _date | None = None) -> dict[str, Any]:
        """
        Generate comprehensive daily report.

        Returns:
            {
                'date': str,
                'portfolio': {...},
                'risk': {...},
                'strategy': {...},
                'components': {...},
                'regime': {...},
                'signals': {...},
                'warnings': [...],
            }
        """
        if report_date is None:
            report_date = _date.today()

        with DatabaseContext("read") as cur:
            report = {
                "date": str(report_date),
                "portfolio": self._fetch_portfolio(cur, report_date),
                "risk": self._fetch_risk(cur, report_date),
                "strategy": self._fetch_strategy(cur, report_date),
                "components": self._fetch_components(cur, report_date),
                "regime": self._fetch_regime(report_date),
                "signals": self._fetch_signals(cur, report_date),
                "warnings": [],
            }

            # Check thresholds
            report["warnings"] = self._check_thresholds(report)

            logger.info(f"Daily report generated for {report_date}")
            return report

    def _fetch_portfolio(self, cur, report_date: _date) -> dict[str, Any]:
        """Portfolio value, P&L, drawdown."""
        try:
            cur.execute(
                """
                SELECT total_portfolio_value, snapshot_date FROM algo_portfolio_snapshots
                WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 2
                """,
                (report_date,),
            )
            rows = cur.fetchall()

            if not rows:
                raise RuntimeError(f"No portfolio snapshots available for {report_date}")

            current_value = float(rows[0][0]) if rows[0][0] is not None else 0
            prior_value = float(rows[1][0]) if len(rows) > 1 and rows[1][0] is not None else current_value

            daily_pnl_pct = ((current_value - prior_value) / prior_value * 100) if prior_value > 0 else 0

            # YTD P&L (simplified)
            cur.execute(
                """SELECT total_portfolio_value FROM algo_portfolio_snapshots
                   WHERE EXTRACT(YEAR FROM snapshot_date) = EXTRACT(YEAR FROM %s)
                   ORDER BY snapshot_date ASC LIMIT 1""",
                (report_date,),
            )
            ytd_row = cur.fetchone()
            ytd_start = safe_float(ytd_row[0], default=0.0) if ytd_row is not None and ytd_row[0] is not None else current_value
            ytd_pnl_pct = ((current_value - ytd_start) / ytd_start * 100) if ytd_start > 0 else 0

            return {
                "current_value": round(current_value, 2),
                "daily_pnl_pct": round(daily_pnl_pct, 2),
                "ytd_pnl_pct": round(ytd_pnl_pct, 2),
                "open_positions": self._count_open_positions(cur, report_date),
            }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Portfolio data conversion failed for {report_date}: {e}") from e

    def _fetch_risk(self, cur, report_date: _date) -> dict[str, Any]:
        """Risk metrics: Sharpe, Sortino, max drawdown, Calmar ratio from pre-computed metrics."""
        try:
            cur.execute(
                """SELECT sharpe_ratio, sortino_ratio, max_drawdown_pct, calmar_ratio
                   FROM algo_performance_metrics
                   WHERE metric_date <= %s
                   ORDER BY metric_date DESC LIMIT 1""",
                (report_date,),
            )
            row = cur.fetchone()

            if row is None:
                raise RuntimeError(f"No performance metrics available for {report_date}")

            return {
                "sharpe_ytd": round(safe_float(row[0], default=0.0), 4) if row[0] else None,
                "sortino": round(safe_float(row[1], default=0.0), 4) if row[1] else None,
                "max_drawdown_pct": round(safe_float(row[2], default=0.0), 2) if row[2] else None,
                "calmar": round(safe_float(row[3], default=0.0), 4) if row[3] else None,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database error fetching risk metrics for {report_date}: {e}") from e

    def _fetch_strategy(self, cur, report_date: _date) -> dict[str, Any]:
        """Win rate, profit factor, performance metrics from pre-computed daily metrics."""
        try:
            cur.execute(
                """SELECT win_rate_pct, profit_factor, avg_trade_pct, best_trade_pct
                   FROM algo_performance_metrics
                   WHERE metric_date <= %s
                   ORDER BY metric_date DESC LIMIT 1""",
                (report_date,),
            )
            row = cur.fetchone()

            if row is None:
                raise RuntimeError(f"No strategy performance data available for {report_date}")

            return {
                "win_rate_pct": round(safe_float(row[0], default=0.0), 2) if row[0] else None,
                "profit_factor": round(safe_float(row[1], default=0.0), 2) if row[1] else None,
                "avg_trade_pct": round(safe_float(row[2], default=0.0), 2) if row[2] else None,
                "best_trade_pct": round(safe_float(row[3], default=0.0), 2) if row[3] else None,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database error fetching strategy metrics for {report_date}: {e}") from e

    def _fetch_components(self, cur, report_date: _date) -> dict[str, Any]:
        """IC and weight for each component."""
        try:
            cur.execute(
                """
                SELECT component, ic_value, ic_pvalue FROM algo_component_attribution
                WHERE report_date = %s
                ORDER BY component
                """,
                (report_date,),
            )
            rows = cur.fetchall()

            if not rows:
                raise RuntimeError(f"No component attribution data available for {report_date}")

            components = {}
            for comp, ic, pval in rows:
                if ic is not None and pval is not None:
                    components[comp] = {
                        "ic": round(safe_float(ic, default=0.0), 3),
                        "pvalue": round(safe_float(pval, default=0.0), 3),
                        "status": self._ic_interpretation(safe_float(ic, default=0.0)),
                    }
                else:
                    components[comp] = {"status": "no_data"}

            return components
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Component data conversion failed for {report_date}: {e}") from e

    def _fetch_regime(self, report_date: _date) -> dict[str, Any]:
        """Current regime and parameter multipliers."""
        regime = self.regime_mgr.get_current_regime(report_date)
        if regime is None:
            raise RuntimeError(f"Regime manager returned None for {report_date}")

        params = self.regime_mgr.get_regime_params(report_date)
        if not params or "position_size_mult" not in params:
            raise RuntimeError(f"Regime params incomplete for {report_date}: {params}")

        history = self.regime_mgr.regime_history(days=30)
        days_in_regime = history[0]["days_in_regime"] if history else 0

        return {
            "current": regime,
            "days_in_regime": days_in_regime,
            "position_size_mult": params["position_size_mult"],
            "weight_update_alpha": params["weight_update_alpha"],
            "description": params["description"],
        }

    def _fetch_signals(self, cur, report_date: _date) -> dict[str, Any]:
        """Signal counts for today."""
        try:
            cur.execute(
                """SELECT COUNT(*) FROM buy_sell_daily
                   WHERE date = %s AND signal_type = 'BUY'""",
                (report_date,),
            )
            result = cur.fetchone()
            candidates = result[0] if result else 0

            cur.execute(
                """SELECT COUNT(*) FROM algo_signals_evaluated
                   WHERE signal_date = %s AND filter_tier_5_pass = TRUE""",
                (report_date,),
            )
            result = cur.fetchone()
            tier_passed = result[0] if result else 0

            cur.execute(
                """SELECT COUNT(*) FROM algo_trades
                   WHERE trade_date = %s""",
                (report_date,),
            )
            result = cur.fetchone()
            entries = result[0] if result else 0

            return {
                "candidates_today": candidates,
                "passed_tiers": tier_passed,
                "entries_today": entries,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database error fetching signal counts for {report_date}: {e}") from e

    def format_text(self, report: dict[str, Any]) -> str:
        """Format report as text for logs."""
        regime = report.get("regime", {})
        components = report.get("components", {})
        portfolio = report.get("portfolio", {})
        risk = report.get("risk", {})
        strategy = report.get("strategy", {})

        pv = portfolio.get("current_value")
        if pv is None:
            pv = 0
        dpnl = portfolio.get("daily_pnl_pct")
        if dpnl is None:
            logger.warning(f"Daily P&L missing for {report['date']} - using N/A instead of fake 0")
            dpnl_str = "N/A"
        else:
            dpnl_str = f"{dpnl:+.2f}%"

        ytd = portfolio.get("ytd_pnl_pct")
        if ytd is None:
            logger.warning(f"YTD P&L missing for {report['date']} - using N/A instead of fake 0")
            ytd_str = "N/A"
        else:
            ytd_str = f"{ytd:+.2f}%"

        var95 = risk.get("var_95_pct")
        if var95 is None:
            logger.warning(f"VaR 95% missing for {report['date']} - using N/A instead of fake 0")
            var95_str = "N/A"
        else:
            var95_str = f"{var95:.1f}%"

        beta = risk.get("beta")
        if beta is None:
            logger.warning(f"Beta missing for {report['date']} - using N/A instead of fake 0")
            beta_str = "N/A"
        else:
            beta_str = f"{beta:.2f}"

        sharpe = risk.get("sharpe_ytd")
        if sharpe is None:
            logger.warning(f"Sharpe YTD missing for {report['date']} - using N/A instead of fake 0")
            sharpe_str = "N/A"
        else:
            sharpe_str = f"{sharpe:.1f}"

        exp_r = strategy.get("expectancy_r")
        if exp_r is None:
            logger.warning(f"Expectancy missing for {report['date']} - using N/A instead of fake 0")
            exp_r_str = "N/A"
        else:
            exp_r_str = f"{exp_r:+.2f}R"

        lines = [
            f"{'=' * 70}",
            f"DAILY FINANCE REPORT - {report['date']} | Regime: {regime.get('current', 'unknown')}",
            f"{'=' * 70}",
            f"Portfolio: ${pv:,.0f} | Daily P&L: {dpnl_str} | YTD: {ytd_str}",
            f"Risk: VaR {var95_str} | Beta {beta_str} | Sharpe {sharpe_str}",
            "",
            "Strategy (last 50 trades):",
            f"  Win rate: {strategy.get('win_rate_pct', 0):.0f}% | "
            f"Profit factor: {strategy.get('profit_factor', 0):.1f}x | "
            f"Expectancy: {exp_r_str}",
            "",
            "Component IC (alpha contribution):",
        ]

        for comp in [
            "setup_quality",
            "trend_quality",
            "momentum_rs",
            "volume",
            "fundamentals",
            "sector_industry",
            "multi_timeframe",
        ]:
            comp_data = components.get(comp, {})
            status = comp_data.get("status", "?")

            if status == "no_data":
                lines.append(f"  {comp:20s} r=N/A        {status.upper():10s}")
            else:
                ic = comp_data.get("ic", 0)
                status_marker = "★" if status == "strong" else "◇" if status == "moderate" else " "
                lines.append(f"  {comp:20s} r={ic:+.3f} {status_marker:2s} {status.upper():10s}")

        signals = report.get("signals", {})
        lines.extend(
            [
                "",
                f"Today: {signals.get('candidates_today', 0)} BUY signals → "
                f"{signals.get('passed_tiers', 0)} tier-passed → "
                f"{signals.get('entries_today', 0)} entries",
                f"{'=' * 70}",
            ]
        )

        return "\n".join(lines)

    def _check_thresholds(self, report: dict[str, Any]) -> list[str]:
        """Check metric thresholds and return warnings."""
        warnings = []

        risk = report.get("risk", {})
        var_95 = risk.get("var_95_pct")
        if var_95 is None:
            logger.warning(f"VaR 95% unavailable for {report['date']} - not yet computed by pipeline")
            warnings.append("VaR 95% not yet available - check algo_performance_metrics pipeline")
        elif var_95 > 2.0:
            warnings.append(f"⚠️  VaR > 2% ({var_95:.1f}%) - High daily risk")

        sharpe_ytd = risk.get("sharpe_ytd")
        if sharpe_ytd is None:
            logger.warning(f"Sharpe YTD unavailable for {report['date']} - cannot assess strategy quality")
            warnings.append("⚠️  Sharpe YTD missing - strategy quality unavailable")
        elif sharpe_ytd < 0.5:
            warnings.append(f"⚠️  Sharpe < 0.5 ({sharpe_ytd:.2f}) - Strategy struggling")

        portfolio = report.get("portfolio", {})
        daily_pnl = portfolio.get("daily_pnl_pct")
        if daily_pnl is None:
            logger.critical(f"Daily P&L unavailable for {report['date']} - cannot assess halt threshold")
            warnings.append(
                "🔴 CRITICAL: Daily P&L missing - cannot assess halt threshold. Manually verify before trading."
            )
        elif daily_pnl < -2.0:
            warnings.append(f"⚠️  Daily loss > 2% ({daily_pnl:.1f}%) - Halt entries?")

        return warnings

    def _ic_interpretation(self, ic_value: float) -> str:
        """Interpret IC value."""
        if ic_value >= 0.40:
            return "strong"
        elif ic_value >= 0.25:
            return "moderate"
        elif ic_value >= 0.10:
            return "weak"
        elif ic_value >= 0:
            return "noise"
        else:
            return "negative"  # anti-predictive - signal has inverted

    def _count_open_positions(self, cur, report_date: _date) -> int:
        """Count open positions."""
        try:
            cur.execute(
                """SELECT COUNT(*) FROM algo_positions
                   WHERE status = 'open' AND created_at <= %s""",
                (report_date,),
            )
            result = cur.fetchone()
            return result[0] if result else 0
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Exception: {e}")
            return 0


if __name__ == "__main__":
    report_gen = DailyFinanceReport()
    report = report_gen.generate(_date.today())
    logger.info(report_gen.format_text(report))
