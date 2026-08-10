#!/usr/bin/env python3

import logging
from datetime import date as _date
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class DailyFinanceReport:
    def __init__(self) -> None:
        from algo.orchestration import RegimeManager

        self.regime_mgr = RegimeManager()

    def generate(self, report_date: _date | None = None) -> dict[str, Any]:
        if report_date is None:
            report_date = _date.today()

        with DatabaseContext("read") as cur:
            report: dict[str, Any] = {
                "date": str(report_date),
            }

            # Fetch core sections - fail if unavailable
            try:
                report["portfolio"] = self._fetch_portfolio(cur, report_date)
            except RuntimeError as e:
                logger.error(f"Daily report generation failed: {e}")
                raise

            try:
                report["risk"] = self._fetch_risk(cur, report_date)
            except RuntimeError as e:
                logger.error(f"Daily report generation failed: {e}")
                raise

            # Fetch optional sections - return empty data if unavailable
            try:
                report["strategy"] = self._fetch_strategy(cur, report_date)
            except RuntimeError as e:
                logger.warning(f"Strategy data unavailable: {e}")
                report["strategy"] = {}

            try:
                report["components"] = self._fetch_components(cur, report_date)
            except (RuntimeError, ValueError) as e:
                logger.warning(f"Component data unavailable: {e}")
                report["components"] = {}

            try:
                report["regime"] = self._fetch_regime(report_date)
            except RuntimeError as e:
                logger.warning(f"Regime data unavailable: {e}")
                report["regime"] = {"current": "unknown"}

            try:
                report["signals"] = self._fetch_signals(cur, report_date)
            except RuntimeError as e:
                logger.warning(f"Signal data unavailable: {e}")
                report["signals"] = {}

            report["warnings"] = self._check_thresholds(report)

            logger.info(f"Daily report generated for {report_date}")
            return report

    def _fetch_portfolio(self, cur: Any, report_date: _date) -> dict[str, Any]:
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

            if rows[0][0] is None:
                raise RuntimeError(
                    f"[DAILY_REPORT] Current portfolio snapshot has NULL value for {report_date}. "
                    f"Cannot calculate daily P&L with missing current portfolio value."
                )
            current_value = float(rows[0][0])

            if len(rows) > 1:
                if rows[1][0] is None:
                    raise RuntimeError(
                        "[DAILY_REPORT] Prior portfolio snapshot has NULL value. "
                        "Cannot calculate daily P&L with missing prior portfolio value."
                    )
                prior_value = float(rows[1][0])
            else:
                raise RuntimeError(
                    f"[DAILY_REPORT] No prior portfolio snapshot available for {report_date}. "
                    f"Cannot calculate daily P&L without yesterday's portfolio value."
                )
            if prior_value <= 0:
                raise RuntimeError(
                    f"[DAILY_REPORT] Prior portfolio value is {prior_value} (invalid). "
                    f"Portfolio value must be > 0 to calculate P&L."
                )
            daily_pnl_pct = (current_value - prior_value) / prior_value * 100

            # YTD P&L (simplified)
            cur.execute(
                """SELECT total_portfolio_value FROM algo_portfolio_snapshots
                   WHERE EXTRACT(YEAR FROM snapshot_date) = EXTRACT(YEAR FROM %s)
                   ORDER BY snapshot_date ASC LIMIT 1""",
                (report_date,),
            )
            ytd_row = cur.fetchone()
            ytd_start = float(ytd_row[0]) if ytd_row is not None and ytd_row[0] is not None else None
            if ytd_start is None or ytd_start <= 0:
                raise RuntimeError(
                    f"[DAILY_REPORT] Year-to-date starting portfolio snapshot unavailable ({ytd_start}). "
                    f"Cannot calculate YTD P&L without year-start value. Check algo_portfolio_snapshots for {report_date.year} data."
                )
            ytd_pnl_pct = (current_value - ytd_start) / ytd_start * 100

            return {
                "current_value": round(current_value, 2),
                "daily_pnl_pct": round(daily_pnl_pct, 2),
                "ytd_pnl_pct": round(ytd_pnl_pct, 2),
                "open_positions": self._count_open_positions(cur, report_date),
            }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Portfolio data conversion failed for {report_date}: {e}") from e

    def _fetch_risk(self, cur: Any, report_date: _date) -> dict[str, Any]:
        """Risk metrics: Sharpe, Sortino, max drawdown, Calmar ratio, VaR, beta.

        Sharpe/Sortino/drawdown/Calmar come from algo_performance_daily (written every
        orchestrator run by Phase 9's LivePerformance.generate_daily_report), not
        algo_performance_metrics - the latter has had no writer since 2026-06-30 and was
        silently serving weeks-stale numbers here (e.g. a 2.9% max drawdown next to a real,
        circuit-breaker-confirmed 28.75% drawdown - see algo/reporting/performance.py
        LivePerformance for the live computation and lambda/api/routes/algo_handlers/metrics.py
        for the same fix applied to the dashboard API).

        VaR/beta come from algo_risk_daily, written independently by the same Phase 9 run's
        ValueAtRisk.generate_daily_risk_report() (algo/risk/var.py). This method never queried
        that table at all - var_95_pct/beta were always None here no matter how fresh the real
        data in algo_risk_daily was, so _check_thresholds() permanently logged "VaR 95% not yet
        available - check algo_performance_metrics pipeline" (a dead table with no writer since
        2026-06-30) and the VaR > 2% risk alert could never fire.

        Returns empty dict if metrics not yet available (expected during ramp-up or before
        first orchestrator run completes).
        """
        result: dict[str, Any] = {}
        db_error: Exception | None = None

        try:
            cur.execute(
                """SELECT rolling_sharpe_252d AS sharpe_ratio, rolling_sortino_252d AS sortino_ratio,
                          max_drawdown_pct, calmar_ratio
                   FROM algo_performance_daily
                   WHERE report_date <= %s
                   ORDER BY report_date DESC LIMIT 1""",
                (report_date,),
            )
            row = cur.fetchone()
            if row is None:
                logger.info(
                    f"[DAILY_REPORT] No performance metrics available for {report_date}. "
                    f"This is normal during initial ramp-up or before first orchestrator run."
                )
            else:
                result.update(
                    {
                        "sharpe_ytd": round(float(row[0]), 4) if row[0] is not None else None,
                        "sortino": round(float(row[1]), 4) if row[1] is not None else None,
                        "max_drawdown_pct": round(float(row[2]), 2) if row[2] is not None else None,
                        "calmar": round(float(row[3]), 4) if row[3] is not None else None,
                    }
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            db_error = e
            logger.warning(f"Database error fetching performance metrics for {report_date}: {type(e).__name__}")

        try:
            cur.execute(
                """SELECT var_pct_95, portfolio_beta
                   FROM algo_risk_daily
                   WHERE report_date <= %s
                   ORDER BY report_date DESC LIMIT 1""",
                (report_date,),
            )
            row = cur.fetchone()
            if row is None:
                logger.info(
                    f"[DAILY_REPORT] No VaR/beta risk data available for {report_date}. "
                    f"This is normal during initial ramp-up or before first orchestrator run."
                )
            else:
                result["var_95_pct"] = round(float(row[0]), 2) if row[0] is not None else None
                result["beta"] = round(float(row[1]), 3) if row[1] is not None else None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            db_error = e
            logger.warning(f"Database error fetching VaR/beta risk data for {report_date}: {type(e).__name__}")

        if not result:
            if db_error is not None:
                return {
                    "data_unavailable": True,
                    "reason": "database_error",
                    "details": f"{type(db_error).__name__}: {str(db_error)[:100]}",
                }
            return {
                "data_unavailable": True,
                "reason": "no_performance_metrics_available",
                "details": "Expected during ramp-up phase before algo has established P&L history",
            }
        return result

    def _fetch_strategy(self, cur: Any, report_date: _date) -> dict[str, Any]:
        """Win rate, profit factor, performance metrics from pre-computed daily metrics.

        Reads algo_performance_daily (see _fetch_risk above for why). profit_factor,
        avg_trade_pct and best_trade_pct aren't populated there (nothing in the current
        pipeline writes them) - reported as None rather than a weeks-stale number.

        Returns empty dict if metrics not yet available (expected during ramp-up or before
        first orchestrator run completes).
        """
        try:
            cur.execute(
                """SELECT win_rate_50t, profit_factor
                   FROM algo_performance_daily
                   WHERE report_date <= %s
                   ORDER BY report_date DESC LIMIT 1""",
                (report_date,),
            )
            row = cur.fetchone()

            if row is None:
                logger.info(
                    f"[DAILY_REPORT] No strategy performance data available for {report_date}. "
                    f"This is normal during ramp-up or before first trades executed."
                )
                return {
                    "data_unavailable": True,
                    "reason": "no_strategy_metrics_available",
                    "details": "Expected before first orchestrator execution or trades completed",
                }

            return {
                "win_rate_pct": round(float(row[0]), 2) if row[0] is not None else None,
                "profit_factor": round(float(row[1]), 2) if row[1] is not None else None,
                "avg_trade_pct": None,
                "best_trade_pct": None,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            msg = f"Database error fetching strategy metrics for {report_date}: {type(e).__name__}"
            logger.warning(msg)
            return {
                "data_unavailable": True,
                "reason": "database_error",
                "details": f"{type(e).__name__}: {str(e)[:100]}",
            }

    def _fetch_components(self, cur: Any, report_date: _date) -> dict[str, Any]:
        """IC and weight for each component.

        SignalAttributionEngine is deprecated (swing_scores removed), so component attribution
        data may not be available early in the day. Returns empty dict when unavailable - the report
        can still be generated without component analysis. Component attribution is populated by
        end-of-day loaders, not available during morning/afternoon orchestrator runs.
        """
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
                logger.info(
                    f"[DAILY_REPORT] No component attribution data available for {report_date}. "
                    f"Expected if running before end-of-day loaders complete."
                )
                return {
                    "data_unavailable": True,
                    "reason": "no_component_attribution_data",
                    "details": "SignalAttributionEngine is deprecated; data available only from end-of-day loaders",
                }

            components = {}
            for comp, ic, pval in rows:
                if ic is not None and pval is not None:
                    components[comp] = {
                        "ic": round(float(ic), 3),
                        "pvalue": round(float(pval), 3),
                        "status": self._ic_interpretation(float(ic)),
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
        if not history:
            raise RuntimeError(
                f"[DAILY_REPORT CRITICAL] Regime history empty for {report_date}. "
                f"Cannot generate report without regime history. Check RegimeManager.regime_history()."
            )

        regime_item = history[0]
        if "days_in_regime" not in regime_item:
            raise RuntimeError(
                f"[DAILY_REPORT CRITICAL] Regime history item missing 'days_in_regime' key. "
                f"Available keys: {list(regime_item.keys())}. Data structure error."
            )
        days_in_regime = int(regime_item["days_in_regime"])

        return {
            "current": regime,
            "days_in_regime": days_in_regime,
            "position_size_mult": params["position_size_mult"],
            "weight_update_alpha": params["weight_update_alpha"],
            "description": params["description"],
        }

    def _fetch_signals(self, cur: Any, report_date: _date) -> dict[str, Any]:
        """Signal counts for today. Validates all query results explicitly.

        FIXED: buy_sell_daily for trading day D is only published after D's EOD close
        (same lag Phase 7 accounts for via latest_buysell_date - see
        phase7_signal_generation.py). Querying WHERE date = report_date literally showed
        0 candidates for the entire trading day, every day, until that evening's loader
        run landed - even on runs where Phase 7 correctly found and qualified real
        candidates from the latest available prior date (e.g. Friday's data on a Monday
        run). That made "Today: 0 BUY signals -> N tier-passed" look like a broken
        pipeline when it wasn't. Resolve to the latest buy_sell_daily date at or before
        report_date, same as Phase 7 does, so the count reflects what Phase 7 actually saw.
        """
        try:
            cur.execute(
                "SELECT MAX(date) FROM buy_sell_daily WHERE date <= %s",
                (report_date,),
            )
            max_date_row = cur.fetchone()
            candidates_date = max_date_row[0] if max_date_row and max_date_row[0] else report_date

            cur.execute(
                """SELECT COUNT(*) FROM buy_sell_daily
                   WHERE date = %s AND signal_type = 'BUY'""",
                (candidates_date,),
            )
            result = cur.fetchone()
            if result is None or result[0] is None:
                logger.warning(f"[SIGNALS] Unexpected NULL count for buy_sell_daily on {candidates_date}")
                candidates = 0
            else:
                candidates = result[0]

            # GOVERNANCE: Read from algo_signals, the source of truth for signals that passed all filter tiers.
            # (Historical note: algo_signals_evaluated was an audit trail table for filter tier pass/fail details,
            # but its writer was accidentally deleted in commit c45211720 [2026-05-31] as a side effect of a
            # refactoring. The table has since been dropped. See Session 311+ for cleanup details.)
            cur.execute(
                """SELECT COUNT(*) FROM algo_signals
                   WHERE signal_date = %s""",
                (report_date,),
            )
            result = cur.fetchone()
            if result is None or result[0] is None:
                logger.warning(f"[SIGNALS] Unexpected NULL count for algo_signals on {report_date}")
                tier_passed = 0
            else:
                tier_passed = result[0]

            cur.execute(
                """SELECT COUNT(*) FROM algo_trades
                   WHERE trade_date = %s""",
                (report_date,),
            )
            result = cur.fetchone()
            if result is None or result[0] is None:
                logger.warning(f"[SIGNALS] Unexpected NULL count for algo_trades on {report_date}")
                entries = 0
            else:
                entries = result[0]

            return {
                "candidates_today": candidates,
                # str, not date: this dict is json.dumps()'d whole by
                # phase9_reconciliation.py's _generate_daily_report(), which requires
                # every value to be JSON-serializable (matches "date" below).
                "candidates_date": str(candidates_date),
                "passed_tiers": tier_passed,
                "entries_today": entries,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database error fetching signal counts for {report_date}: {e}") from e

    def format_text(self, report: dict[str, Any]) -> str:
        if not report:
            raise ValueError("Report cannot be None")

        regime = report["regime"]
        if not regime:
            raise ValueError("Report missing required field: regime")
        components = report.get("components", {})
        # components can be empty dict when SignalAttributionEngine is deprecated or data not yet available
        portfolio = report["portfolio"]
        if not portfolio:
            raise ValueError("Report missing required field: portfolio")
        risk = report["risk"]
        if not risk:
            raise ValueError("Report missing required field: risk")
        strategy = report["strategy"]
        # strategy can be empty dict or have data_unavailable flag when metrics unavailable
        # Both are valid - proceed with None defaults for missing fields

        pv = portfolio["current_value"]
        dpnl = portfolio["daily_pnl_pct"]
        ytd = portfolio["ytd_pnl_pct"]

        var95 = risk.get("var_95_pct")
        beta = risk.get("beta")
        sharpe = risk.get("sharpe_ytd")

        exp_r = strategy.get("expectancy_r")
        win_rate = strategy.get("win_rate_pct")
        profit_factor = strategy.get("profit_factor")

        pv_str = f"${pv:,.0f}" if pv is not None else "N/A"
        dpnl_str = f"{dpnl:+.2f}%" if dpnl is not None else "N/A"
        ytd_str = f"{ytd:+.2f}%" if ytd is not None else "N/A"
        var95_str = f"{var95:.1f}%" if var95 is not None else "N/A"
        beta_str = f"{beta:.2f}" if beta is not None else "N/A"
        sharpe_str = f"{sharpe:.1f}" if sharpe is not None else "N/A"
        exp_r_str = f"{exp_r:+.2f}R" if exp_r is not None else "N/A"
        # win_rate_pct/profit_factor are legitimately None on insufficient trade history (see
        # _fetch_strategy above) - every other optional field here already guards for None, these
        # two didn't, crashing report generation (and halting Phase 9) the instant an account has
        # too few closed trades to compute them, e.g. a fresh local paper-trading account.
        win_rate_str = f"{win_rate:.0f}%" if win_rate is not None else "N/A"
        profit_factor_str = f"{profit_factor:.1f}x" if profit_factor is not None else "N/A"

        lines = [
            f"{'=' * 70}",
            f"DAILY FINANCE REPORT - {report['date']} | Regime: {regime['current']}",
            f"{'=' * 70}",
            f"Portfolio: {pv_str} | Daily P&L: {dpnl_str} | YTD: {ytd_str}",
            f"Risk: VaR {var95_str} | Beta {beta_str} | Sharpe {sharpe_str}",
            "",
            "Strategy (last 50 trades):",
            f"  Win rate: {win_rate_str} | Profit factor: {profit_factor_str} | Expectancy: {exp_r_str}",
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
            if comp not in components:
                lines.append(f"  {comp:20s} r=N/A        MISSING")
                continue

            comp_data = components[comp]
            status = comp_data["status"]

            if status == "no_data":
                lines.append(f"  {comp:20s} r=N/A        {status.upper():10s}")
            else:
                ic = comp_data["ic"]
                status_marker = "*" if status == "strong" else "◇" if status == "moderate" else " "
                lines.append(f"  {comp:20s} r={ic:+.3f} {status_marker:2s} {status.upper():10s}")

        signals = report["signals"]
        candidates_date = signals.get("candidates_date")
        date_suffix = (
            f" (as of {candidates_date})"
            if candidates_date is not None and candidates_date != report.get("date")
            else ""
        )
        lines.extend(
            [
                "",
                f"Today: {signals['candidates_today']} BUY signals{date_suffix} -> "
                f"{signals['passed_tiers']} tier-passed -> "
                f"{signals['entries_today']} entries",
                f"{'=' * 70}",
            ]
        )

        return "\n".join(lines)

    def _check_thresholds(self, report: dict[str, Any]) -> list[str]:
        warnings = []

        risk = report.get("risk")
        if risk is None:
            logger.warning(f"[REPORT] Risk metrics missing for {report['date']} - upstream pipeline incomplete")
            var_95 = None
            sharpe_ytd = None
        else:
            var_95 = risk.get("var_95_pct")
            sharpe_ytd = risk.get("sharpe_ytd")

        if var_95 is None:
            logger.warning(f"VaR 95% unavailable for {report['date']} - not yet computed by pipeline")
            warnings.append("VaR 95% not yet available - check algo_performance_metrics pipeline")
        elif var_95 > 2.0:
            warnings.append(f"[WARN]️  VaR > 2% ({var_95:.1f}%) - High daily risk")

        if sharpe_ytd is None:
            logger.warning(f"Sharpe YTD unavailable for {report['date']} - cannot assess strategy quality")
            warnings.append("[WARN]️  Sharpe YTD missing - strategy quality unavailable")
        elif sharpe_ytd < 0.5:
            warnings.append(f"[WARN]️  Sharpe < 0.5 ({sharpe_ytd:.2f}) - Strategy struggling")

        portfolio = report.get("portfolio")
        if portfolio is None:
            logger.warning(f"[REPORT] Portfolio metrics missing for {report['date']} - upstream pipeline incomplete")
            daily_pnl = None
        else:
            daily_pnl = portfolio.get("daily_pnl_pct")
        if daily_pnl is None:
            logger.critical(f"Daily P&L unavailable for {report['date']} - cannot assess halt threshold")
            warnings.append(
                "[STOP] CRITICAL: Daily P&L missing - cannot assess halt threshold. Manually verify before trading."
            )
        elif daily_pnl < -2.0:
            warnings.append(f"[WARN]️  Daily loss > 2% ({daily_pnl:.1f}%) - Halt entries?")

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

    def _count_open_positions(self, cur: Any, report_date: _date) -> int:
        """Count open positions."""
        try:
            cur.execute(
                """SELECT COUNT(*) FROM algo_positions
                   WHERE status = 'open' AND created_at <= %s""",
                (report_date,),
            )
            result = cur.fetchone()
            if result is None:
                raise RuntimeError("CRITICAL: Portfolio snapshot count query returned None (database query failed)")
            if result[0] is None:
                raise RuntimeError("CRITICAL: Portfolio snapshot count is NULL")
            return int(result[0])
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[CRITICAL] Failed to count portfolio snapshots: {e}")
            raise RuntimeError(
                f"Portfolio snapshot count unavailable due to database error: {e}. "
                "Cannot generate financial report without portfolio data."
            ) from e


if __name__ == "__main__":
    report_gen = DailyFinanceReport()
    report = report_gen.generate(_date.today())
    logger.info(report_gen.format_text(report))
