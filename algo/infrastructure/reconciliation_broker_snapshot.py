#!/usr/bin/env python3
"""BROKER-CONNECTED RECONCILIATION: concentration/drawdown/return metrics + snapshot write

Pure extract-method split of `DailyReconciliation.run_daily_reconciliation()` (see that
module's class docstring for the overall contract). This file covers the metrics and
persistence tail of the execution_mode=="auto" (self.broker is not None) branch, run after
`_fetch_and_analyze_open_positions` (reconciliation_broker_positions.py) and the cash/equity
computation that stays inline in run_daily_reconciliation() (it contains the
`if execution_mode in ("paper", "dry"):` line a regression test scans for by source text):

1. `_log_analytics_metrics` - step 1d's IC/expectancy log lines.
2. `_compute_broker_snapshot_metrics` - concentration (largest/average/Herfindahl), prior
   snapshot / daily return, market trend, today's win/loss counts, initial capital, max
   drawdown / running peak / cash-flow-adjusted drawdown, cumulative return, and Sharpe
   ratio.
3. `_write_broker_snapshot` - the advisory-lock-guarded INSERT ... ON CONFLICT into
   algo_portfolio_snapshots.
4. `_audit_and_log_broker_snapshot` - the audit-log call plus the "3. Portfolio Summary"
   log block.

NO BEHAVIOR CHANGE: every method here is a verbatim relocation of code that used to live
inline in run_daily_reconciliation() - control flow, thresholds, SQL, and log messages are
unchanged. Comments documenting non-obvious business logic (fix-history notes, migration
references, bug-found dates) moved verbatim with the code they describe.

Mixed into DailyReconciliation via multiple inheritance - `self.audit_logger` (set in
DailyReconciliation.__init__ whenever self.broker is not None, which is the only case this
mixin's methods are ever reached from) resolves normally through the instance.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import date as _date_type
from decimal import Decimal
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

from algo.config.credential_manager import get_algo_owner_cognito_sub
from algo.infrastructure.reconciliation_broker_positions import BrokerPositionState
from algo.infrastructure.reconciliation_shared import PORTFOLIO_SNAPSHOT_LOCK_ID, compute_adjusted_drawdown

logger = logging.getLogger(__name__)


@dataclass
class BrokerSnapshotMetrics:
    """Everything computed by `_compute_broker_snapshot_metrics`, threaded into
    `_write_broker_snapshot` and `_audit_and_log_broker_snapshot`. One field per named
    local variable the original inline code carried across this same span.
    """

    largest_position_dec: Decimal
    max_concentration_dec: Decimal
    avg_position_size_dec: Decimal
    herfindahl_index_dec: Decimal
    daily_return_pct_dec: Decimal
    market_trend: str
    win_count: int
    loss_count: int
    realized_pnl_today: float
    initial_capital: float
    max_drawdown_pct_dec: Decimal
    running_peak_dec: Decimal
    drawdown_pct_dec: Decimal
    net_capital_flow_cum: float
    adjusted_equity: float
    adjusted_running_peak: float
    adjusted_drawdown_pct: float
    cumulative_return_pct: float
    sharpe_ratio: float | None


class BrokerSnapshotMixin:
    """Mixin providing the metrics-computation and snapshot-persistence steps of the
    broker-connected (execution_mode=="auto") branch of run_daily_reconciliation()."""

    def _log_analytics_metrics(self, analytics: dict[str, Any]) -> None:
        # 1d. Compute analytics metrics: IC and expectancy (E4-E5)
        logger.info("\n1d. Analytics Metrics:")
        if analytics["ic"].get("valid"):
            logger.info(
                f"   IC (Information Coefficient): {analytics['ic']['ic']:.4f} ({analytics['ic']['trade_count']} trades)"
            )
            if analytics["ic"]["alert"]:
                logger.info(f"   [WARN] {analytics['ic']['alert']}")
        if analytics["expectancy"].get("valid"):
            logger.info(
                f"   Expectancy: {analytics['expectancy']['expectancy']:+.4f}% (win rate {analytics['expectancy']['win_rate']:.1f}%)"
            )
            logger.info(f"   Kelly Fraction (25% conservative): {analytics['expectancy']['kelly_fraction']:.4f}")
            if analytics["expectancy"]["alert"]:
                logger.info(f"   [FAIL] {analytics['expectancy']['alert']}")

    def _compute_broker_snapshot_metrics(
        self,
        cur: PsycopgCursor[Any],
        reconcile_date: _date_type,
        total_equity_dec: Decimal,
        position_state: BrokerPositionState,
    ) -> BrokerSnapshotMetrics:
        positions = position_state.positions
        total_position_value = position_state.total_position_value

        position_values = [p[5] for p in positions if p[5] is not None]  # position_value is now at index 5 (was 4)
        if len(position_values) < len(positions):
            excluded_count = len(positions) - len(position_values)
            logger.critical(
                f"CRITICAL: {excluded_count}/{len(positions)} positions have NULL position_value in reconciliation"
            )
            raise ValueError(
                f"CRITICAL: {excluded_count}/{len(positions)} positions have NULL position_value in reconciliation. "
                f"Cannot calculate concentration risk without complete position data."
            )

        # FIXED: Allow zero positions (fresh account) as valid state
        # Fresh accounts have no positions - this is expected, not an error
        if not position_values:
            logger.info("[RECONCILIATION] Portfolio has no open positions (fresh account or all exited)")
            largest_position_dec = Decimal(0)
            max_concentration_dec = Decimal(0)
            avg_position_size_dec = Decimal(0)
            herfindahl_index_dec = Decimal(0)
        else:
            largest_position_dec = Decimal(str(max(position_values)))
            if total_equity_dec <= 0:
                logger.critical(f"CRITICAL: Total equity invalid ({total_equity_dec}) for concentration calculation")
                raise ValueError(
                    f"CRITICAL: Total equity invalid ({total_equity_dec}) - cannot calculate concentration"
                )
            max_concentration_dec = largest_position_dec / total_equity_dec * Decimal(100)
            # avg_position_size_dec stores the average position VALUE in dollars (NOT a percentage)
            # It will be converted to percentage on line 1385-1388
            avg_position_size_dec = total_position_value / len(positions) if len(positions) > 0 else Decimal(0)

            # Calculate Herfindahl index for concentration_risk_pct (sum of squared position percentages)
            # This measures portfolio concentration: 1/n for equal-weight = low concentration, 100 for single position = high
            herfindahl_index_dec = Decimal(0)
            for pos_val in position_values:
                pos_pct = Decimal(str(pos_val)) / total_equity_dec * Decimal(100)
                herfindahl_index_dec += pos_pct * pos_pct

            logger.debug(
                f"[RECONCILIATION] Concentration metrics: "
                f"total_position_value={float(total_position_value):.2f}, "
                f"total_equity_dec={float(total_equity_dec):.2f}, "
                f"largest_pos={float(largest_position_dec):.2f} ({float(max_concentration_dec):.2f}%), "
                f"avg_pos_dollars={float(avg_position_size_dec):.2f}, "
                f"herfindahl_index={float(herfindahl_index_dec):.2f}"
            )

        # CRITICAL FIX 2026-08-09: bound by reconcile_date - an unbounded "latest
        # snapshot" query picks up any stray future-dated row (e.g. a leftover
        # local --date simulation snapshot in the shared dev DB) ahead of the real
        # current one. See algo/risk/circuit_breaker.py for the same bug class.
        cur.execute(
            """
            SELECT total_portfolio_value FROM algo_portfolio_snapshots
            WHERE snapshot_date <= %s
            ORDER BY snapshot_date DESC LIMIT 1
        """,
            (reconcile_date,),
        )

        prev_snapshot = cur.fetchone()
        prev_value_dec = Decimal(str(prev_snapshot[0])) if prev_snapshot else total_equity_dec
        daily_return_dec = total_equity_dec - prev_value_dec
        if prev_value_dec <= 0:
            logger.critical(
                f"CRITICAL: Prior portfolio snapshot value invalid ({prev_value_dec}) - cannot calculate daily return. "
                f"Check portfolio snapshot data continuity."
            )
            raise ValueError(
                f"Prior portfolio value invalid ({prev_value_dec}) - daily return calculation requires valid historical snapshot"
            )
        daily_return_pct_dec = daily_return_dec / prev_value_dec * Decimal(100)

        cur.execute(
            """
            SELECT market_trend, distribution_days_4w
            FROM market_health_daily
            WHERE date <= %s
            ORDER BY date DESC LIMIT 1
        """,
            (reconcile_date,),
        )

        market = cur.fetchone()
        if market is None:
            logger.warning(
                f"[RECONCILIATION] Market trend data missing for {reconcile_date} (no row in market_health_daily)"
            )
            market_trend = "data_unavailable"
        else:
            market_trend = market[0]

        # Calculate additional metrics (no COALESCE - catch missing data explicitly)
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE profit_loss_dollars > 0) as wins,
                COUNT(*) FILTER (WHERE profit_loss_dollars < 0) as losses,
                SUM(profit_loss_dollars) FILTER (WHERE DATE(exit_date) = %s::date) as realized_pnl_today,
                COUNT(*) FILTER (WHERE profit_loss_dollars IS NULL) as null_pnl_count
            FROM algo_trades
            WHERE status = %s
        """,
            (str(reconcile_date), "closed"),
        )
        result = cur.fetchone()
        if result is None:
            raise ValueError("No trades data returned from database")
        win_count = result[0]
        loss_count = result[1]
        realized_pnl_today = result[2]
        null_pnl_count = result[3]

        # Log but don't fail if some trades have missing PnL
        # (incomplete test trades or partial exits can have missing P&L calculations)
        if null_pnl_count and null_pnl_count > 0:
            logger.warning(
                f"WARN: {null_pnl_count} closed trades have NULL profit_loss_dollars. "
                "Using P&L from trades with complete exit data. Check trade execution audit log for details."
            )

        # Validate counts (null if no matching rows)
        if win_count is None or loss_count is None:
            raise ValueError(f"Trade counts missing from database: wins={win_count}, losses={loss_count}")

        # realized_pnl_today can legitimately be None when no trades closed today.
        if realized_pnl_today is None:
            realized_pnl_today = 0.0
            logger.info("No trades closed today - daily realized PnL is 0")
        win_count = int(win_count)
        loss_count = int(loss_count)
        realized_pnl_today = float(realized_pnl_today)

        # initial_capital is fetched here (normalize to actual initial capital from Alpaca
        # account history) but cumulative_return_pct itself is computed further below,
        # once adjusted_equity is available - see that comment for why.
        try:
            initial_capital = self._fetch_initial_capital(cur)  # type: ignore[attr-defined]
            if initial_capital <= 0:
                raise ValueError(
                    f"CRITICAL: Invalid initial_capital={initial_capital} - cannot calculate cumulative return. "
                    "Check Alpaca account initialization and capital history."
                )
        except ValueError as e:
            logger.error(f"CRITICAL: {e} - cannot calculate cumulative return")
            raise

        # Calculate max drawdown from historical snapshots
        max_drawdown_pct_dec = Decimal(0)
        cur.execute("""
            SELECT
                MAX(total_portfolio_value) as peak,
                MIN(total_portfolio_value) as trough
            FROM algo_portfolio_snapshots
        """)
        peak_row = cur.fetchone()
        if peak_row is not None and peak_row[0] is not None and peak_row[1] is not None:
            peak_val_dec = Decimal(str(peak_row[0]))
            trough_val_dec = Decimal(str(peak_row[1]))
            if peak_val_dec > 0:
                max_drawdown_pct_dec = ((peak_val_dec - trough_val_dec) / peak_val_dec) * Decimal(100)

        # Calculate running peak for current snapshot (for use by circuit breaker)
        # running_peak = maximum portfolio value seen up to and including today
        running_peak_dec = max(peak_val_dec, total_equity_dec) if peak_row and peak_row[0] else total_equity_dec

        # Calculate drawdown percentage from running peak (used by circuit breaker)
        # drawdown_pct = how far below the all-time peak the current portfolio is
        drawdown_pct_dec = Decimal(0)
        if running_peak_dec > 0:
            drawdown_pct_dec = ((running_peak_dec - total_equity_dec) / running_peak_dec) * Decimal(100)

        # Cash-flow-adjusted equity/peak/drawdown (migration 1134): raw total_equity moves
        # for both trading performance AND external capital flows (deposits/withdrawals),
        # which the circuit breaker must not conflate. See algo_capital_flows and
        # algo/risk/circuit_breaker.py::_check_drawdown for the full rationale.
        net_capital_flow_cum, adjusted_running_peak, adjusted_drawdown_pct = compute_adjusted_drawdown(
            cur, reconcile_date, float(total_equity_dec)
        )
        adjusted_equity = float(total_equity_dec) - net_capital_flow_cum

        # Cumulative return against adjusted_equity (cash-flow-adjusted), NOT the
        # realized-trades-only cumulative_pnl this used previously: "total return since
        # inception" should reflect trading performance (realized + unrealized) relative
        # to starting capital, not be inflated/deflated by deposits and withdrawals, and
        # should include unrealized gains on open positions rather than excluding them
        # entirely. Mirrors the LOCAL_MODE/paper path above and the migration 1134
        # rationale already applied to drawdown/daily-loss elsewhere in this codebase.
        cumulative_return_pct = (adjusted_equity - initial_capital) / initial_capital * 100
        logger.info(f"   Cumulative Return: {cumulative_return_pct:+.2f}% (on initial capital ${initial_capital:,.2f})")

        # Calculate Sharpe ratio: mean_return / std_dev * sqrt(252)
        # CRITICAL FIX 2026-08-09: bound by reconcile_date - an unbounded trailing
        # window can pull in a stray future-dated row (e.g. a leftover local
        # --date simulation snapshot), corrupting the return series.
        sharpe_ratio = None
        try:
            cur.execute(
                """
                SELECT daily_return_pct FROM algo_portfolio_snapshots
                WHERE daily_return_pct IS NOT NULL AND snapshot_date <= %s
                ORDER BY snapshot_date DESC LIMIT 252
            """,
                (reconcile_date,),
            )
            returns = [float(r[0]) / 100.0 for r in cur.fetchall() if r[0] is not None]
            if len(returns) > 1:
                std_dev = statistics.stdev(returns)
                mean_return = statistics.mean(returns)
                if std_dev > 0:
                    sharpe_ratio = mean_return / std_dev * (252**0.5)
            elif len(returns) <= 1:
                logger.warning(
                    f"[RECONCILIATION] Sharpe calculation skipped: insufficient return history ({len(returns)} values). "
                    "Need at least 2 return points to calculate standard deviation."
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(
                f"[RECONCILIATION CRITICAL] Sharpe ratio calculation failed: {e}. "
                "Cannot compute risk-adjusted return metric. This is critical for portfolio risk assessment. "
                "Check database connection and portfolio snapshot data consistency."
            )
            raise ValueError(
                f"CRITICAL: Sharpe ratio calculation failed: {e}. "
                "Reconciliation requires valid return history for risk metrics. "
                "Cannot proceed without Sharpe calculation capability."
            ) from e

        return BrokerSnapshotMetrics(
            largest_position_dec=largest_position_dec,
            max_concentration_dec=max_concentration_dec,
            avg_position_size_dec=avg_position_size_dec,
            herfindahl_index_dec=herfindahl_index_dec,
            daily_return_pct_dec=daily_return_pct_dec,
            market_trend=market_trend,
            win_count=win_count,
            loss_count=loss_count,
            realized_pnl_today=realized_pnl_today,
            initial_capital=initial_capital,
            max_drawdown_pct_dec=max_drawdown_pct_dec,
            running_peak_dec=running_peak_dec,
            drawdown_pct_dec=drawdown_pct_dec,
            net_capital_flow_cum=net_capital_flow_cum,
            adjusted_equity=adjusted_equity,
            adjusted_running_peak=adjusted_running_peak,
            adjusted_drawdown_pct=adjusted_drawdown_pct,
            cumulative_return_pct=cumulative_return_pct,
            sharpe_ratio=sharpe_ratio,
        )

    def _write_broker_snapshot(
        self,
        cur: PsycopgCursor[Any],
        reconcile_date: _date_type,
        cash_dec: Decimal,
        total_equity_dec: Decimal,
        position_state: BrokerPositionState,
        metrics: BrokerSnapshotMetrics,
    ) -> None:
        positions = position_state.positions

        cur.execute("SELECT pg_advisory_lock(%s)", (PORTFOLIO_SNAPSHOT_LOCK_ID,))
        cur.fetchone()
        try:
            # CRITICAL: Verify that metrics are being calculated correctly
            # The snapshot should show realistic concentration percentages
            avg_pct_calc = (
                (metrics.avg_position_size_dec / total_equity_dec * Decimal(100))
                if total_equity_dec > 0
                else Decimal(0)
            )

            # Sanity check: largest_position_pct should be >= avg_position_size_pct (largest >= average)
            if metrics.max_concentration_dec < avg_pct_calc:
                logger.warning(
                    f"[RECONCILIATION SANITY CHECK] Largest position % ({float(metrics.max_concentration_dec):.2f}%) "
                    f"< average % ({float(avg_pct_calc):.2f}%) - this is mathematically impossible. "
                    f"Check calculation logic in reconciliation.py"
                )

            logger.info(
                f"[RECONCILIATION INSERT] Snapshot metrics for {reconcile_date}:\n"
                f"  Total Positions: {len(positions)}\n"
                f"  Total Position Value: ${float(position_state.total_position_value):,.2f}\n"
                f"  Total Equity: ${float(total_equity_dec):,.2f}\n"
                f"  Largest Position: ${float(metrics.largest_position_dec):,.2f} = {float(metrics.max_concentration_dec):.2f}%\n"
                f"  Average Position: ${float(metrics.avg_position_size_dec):,.2f} = {float(avg_pct_calc):.2f}%\n"
                f"  Concentration Risk (Herfindahl): {float(metrics.herfindahl_index_dec):.2f}"
            )

            cur.execute(
                """
                INSERT INTO algo_portfolio_snapshots (
                    snapshot_date, total_portfolio_value, total_cash, total_equity,
                    position_count, largest_position_pct, average_position_size_pct,
                    concentration_risk_pct,
                    realized_pnl_today, unrealized_pnl_total, unrealized_pnl_pct,
                    unrealized_pnl_winning_count, unrealized_pnl_losing_count, unrealized_pnl_breakeven_count,
                    unrealized_pnl_source,
                    win_count_today, loss_count_today,
                    daily_return_pct, cumulative_return_pct, max_drawdown_pct,
                    sharpe_ratio, market_health_status, drawdown_pct, running_peak,
                    net_capital_flow_cum, adjusted_equity, adjusted_running_peak, adjusted_drawdown_pct,
                    cognito_sub, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                )
                ON CONFLICT (snapshot_date) DO UPDATE SET
                total_portfolio_value = EXCLUDED.total_portfolio_value,
                total_cash = EXCLUDED.total_cash,
                total_equity = EXCLUDED.total_equity,
                position_count = EXCLUDED.position_count,
                largest_position_pct = EXCLUDED.largest_position_pct,
                average_position_size_pct = EXCLUDED.average_position_size_pct,
                concentration_risk_pct = EXCLUDED.concentration_risk_pct,
                realized_pnl_today = EXCLUDED.realized_pnl_today,
                unrealized_pnl_total = EXCLUDED.unrealized_pnl_total,
                unrealized_pnl_pct = EXCLUDED.unrealized_pnl_pct,
                unrealized_pnl_winning_count = EXCLUDED.unrealized_pnl_winning_count,
                unrealized_pnl_losing_count = EXCLUDED.unrealized_pnl_losing_count,
                unrealized_pnl_breakeven_count = EXCLUDED.unrealized_pnl_breakeven_count,
                unrealized_pnl_source = EXCLUDED.unrealized_pnl_source,
                win_count_today = EXCLUDED.win_count_today,
                loss_count_today = EXCLUDED.loss_count_today,
                daily_return_pct = EXCLUDED.daily_return_pct,
                cumulative_return_pct = EXCLUDED.cumulative_return_pct,
                max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                sharpe_ratio = EXCLUDED.sharpe_ratio,
                market_health_status = EXCLUDED.market_health_status,
                drawdown_pct = EXCLUDED.drawdown_pct,
                running_peak = EXCLUDED.running_peak,
                net_capital_flow_cum = EXCLUDED.net_capital_flow_cum,
                adjusted_equity = EXCLUDED.adjusted_equity,
                adjusted_running_peak = EXCLUDED.adjusted_running_peak,
                adjusted_drawdown_pct = EXCLUDED.adjusted_drawdown_pct,
                updated_at = NOW()
        """,
                (
                    reconcile_date,
                    float(total_equity_dec),  # total_portfolio_value
                    float(cash_dec),  # total_cash
                    float(total_equity_dec),  # total_equity
                    len(positions) if positions else 0,  # position_count
                    float(metrics.max_concentration_dec),  # largest_position_pct
                    float(avg_pct_calc),  # average_position_size_pct - should be avg position size as % of portfolio
                    float(metrics.herfindahl_index_dec),  # concentration_risk_pct (Herfindahl index)
                    metrics.realized_pnl_today,
                    float(position_state.unrealized_pnl),
                    float(
                        Decimal(str(position_state.unrealized_pnl_pct))
                        if position_state.unrealized_pnl_pct is not None
                        else Decimal(0)
                    ),
                    position_state.winning_count,
                    position_state.losing_count,
                    position_state.breakeven_count,
                    "open_positions_only",
                    metrics.win_count,
                    metrics.loss_count,
                    float(metrics.daily_return_pct_dec),
                    metrics.cumulative_return_pct,
                    float(metrics.max_drawdown_pct_dec),
                    metrics.sharpe_ratio,
                    metrics.market_trend,
                    float(metrics.drawdown_pct_dec),
                    float(metrics.running_peak_dec),
                    metrics.net_capital_flow_cum,
                    metrics.adjusted_equity,
                    metrics.adjusted_running_peak,
                    metrics.adjusted_drawdown_pct,
                    get_algo_owner_cognito_sub(),
                ),
            )
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", (PORTFOLIO_SNAPSHOT_LOCK_ID,))

    def _audit_and_log_broker_snapshot(
        self,
        reconcile_date: _date_type,
        cash_dec: Decimal,
        total_equity_dec: Decimal,
        position_state: BrokerPositionState,
        metrics: BrokerSnapshotMetrics,
    ) -> None:
        unrealized_pnl_pct_dec = (
            Decimal(str(position_state.unrealized_pnl_pct))
            if position_state.unrealized_pnl_pct is not None
            else Decimal(0)
        )

        # Audit log portfolio snapshot for traceability
        self.audit_logger.log_portfolio_snapshot_audit(  # type: ignore[attr-defined]
            snapshot_date=reconcile_date,
            total_portfolio_value=float(total_equity_dec),
            total_cash=float(cash_dec),
            position_count=len(position_state.positions) if position_state.positions else 0,
            unrealized_pnl_total=float(position_state.unrealized_pnl),
            unrealized_pnl_pct=float(unrealized_pnl_pct_dec),
        )

        logger.info("\n3. Portfolio Summary:")
        logger.info(f"   Total Value: ${float(total_equity_dec):,.2f}")
        logger.info(f"   Position Value: ${float(position_state.total_position_value):,.2f}")
        logger.info(f"   Cash: ${float(cash_dec):,.2f}")
        logger.info(
            f"   Unrealized P&L (OPEN POSITIONS ONLY): {float(position_state.unrealized_pnl):+,.2f} ({float(unrealized_pnl_pct_dec):+.2f}%)"
        )
        logger.info(f"     - Winning positions: {position_state.winning_count}")
        logger.info(f"     - Losing positions: {position_state.losing_count}")
        logger.info(f"     - Breakeven positions: {position_state.breakeven_count}")
        logger.info(f"   Daily Return: {float(metrics.daily_return_pct_dec):+.2f}%")
        logger.info(f"   Concentration: {float(metrics.max_concentration_dec):.1f}%")

        logger.info(f"\n{'=' * 70}")
        logger.info("Reconciliation complete - snapshot created")
        logger.info(f"{'=' * 70}\n")
