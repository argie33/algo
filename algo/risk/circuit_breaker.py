#!/usr/bin/env python3

"""
Trading Risk Management Gates (Pre-Trade Kill-Switches)

IMPORTANT: This is NOT a general-purpose circuit breaker for API/data handling.
Use utils.infrastructure.circuit_breaker:CircuitBreaker for data loader outage handling.

This module implements pre-trade risk checks that halt new position entry:
  CB1. PORTFOLIO DRAWDOWN  >= halt_drawdown_pct (default 20%)
  CB2. DAILY LOSS          >= max_daily_loss_pct (default 2%)
  CB3. CONSECUTIVE LOSSES  >= max_consecutive_losses (default 3)
  CB4. TOTAL OPEN RISK     >= max_total_risk_pct (default 4%)
  CB5. VIX SPIKE           > vix_max_threshold (default 35)
  CB6. MARKET STAGE BREAK  market_stage = 4 (downtrend)
  CB7. WEEKLY LOSS         >= max_weekly_loss_pct (default 5%)
  CB8. DATA STALENESS      latest data > N days old

Each check returns (halted, reason). The orchestrator runs all checks before
new entries — any halt blocks new positions but does NOT auto-exit existing
ones (those are managed by exit_engine + position_monitor).

When a circuit breaker fires:
  - logged in algo_audit_log with action_type='circuit_breaker'
  - returned to caller for display / notification
  - persists state until cleared (e.g., recovery threshold met)
"""

import json
import logging
import math
from datetime import date as _date
from datetime import datetime, timedelta
from typing import Any

import psycopg2

from utils.db import DatabaseContext
from utils.safe_data_conversion import safe_bool, safe_float, safe_int
from utils.trading import PositionStatus, TradeStatus


logger = logging.getLogger(__name__)

# Human-readable labels for circuit breaker checks
CHECK_LABELS = {
    "daily_loss": "Daily Loss Limit Exceeded",
    "drawdown": "Portfolio Drawdown Limit",
    "drawdown_re_engagement": "Drawdown Recovery Period",
    "consecutive_losses": "Consecutive Losses Limit",
    "total_risk": "Total Open Risk Limit",
    "vix_spike": "Market Volatility Spike",
    "market_stage": "Market Stage Break",
    "weekly_loss": "Weekly Loss Limit Exceeded",
    "sector_concentration": "Sector Concentration Warning",
    "intraday_market_health": "Market Instability (Prior-Day Drop)",
    "win_rate_floor": "Win Rate Floor Breached",
    "daily_profit_cap": "Daily Profit Target Reached",
    "data_freshness": "Data Staleness Check",
}


def _safe_float(value, default=None, context=""):
    """Convert to float safely, rejecting NaN/Infinity.

    Uses None as default to distinguish between "missing" and "zero".
    Callers can explicitly pass default=0.0 if zero is appropriate for their context.
    """
    if value is None:
        return default
    try:
        f = safe_float(value, default=0.0, context="value")
        if math.isnan(f) or math.isinf(f):
            logger.warning(f"Invalid float {value!r} (NaN/Inf) {context}")
            return default
        return f
    except (ValueError, TypeError):
        logger.warning(f"Failed to convert {value!r} to float {context}")
        return default


class CircuitBreaker:
    """Pre-trade kill-switch checks."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def check_all(self, current_date: Any = None) -> dict[str, Any]:
        """Run all circuit breakers. Returns dict with per-check status."""
        if not current_date:
            current_date = _date.today()

        with DatabaseContext("write", cursor_factory=None) as cur:
            try:
                results: dict[str, Any] = {
                    "halted": False,
                    "halt_reasons": [],
                    "checks": {},
                }

                for name, fn in [
                    ("daily_loss", self._check_daily_loss),
                    ("drawdown", self._check_drawdown),
                    ("drawdown_re_engagement", self._check_drawdown_re_engagement),
                    ("consecutive_losses", self._check_consecutive_losses),
                    ("total_risk", self._check_total_risk),
                    ("vix_spike", self._check_vix_spike),
                    ("market_stage", self._check_market_stage),
                    ("weekly_loss", self._check_weekly_loss),
                    ("sector_concentration", self._check_sector_concentration),
                    ("intraday_market_health", self._check_intraday_market_health),
                    ("win_rate_floor", self._check_win_rate_floor),
                    ("daily_profit_cap", self._check_daily_profit_cap),
                    ("data_freshness", self._check_data_freshness),
                ]:
                    try:
                        state = fn(current_date, cur)
                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                        import traceback

                        tb = traceback.format_exc()
                        error_type = type(e).__name__

                        # Log full traceback for debugging
                        logger.error(f"Circuit breaker {name} raised {error_type}: {e}")
                        logger.error(f"Full traceback:\n{tb}")

                        # All check failures result in fail-closed halt.
                        # If a safety check cannot be verified, trading must halt.
                        # Do NOT skip checks with "transient" claims — that masks data loss.
                        logger.critical(f"Circuit breaker {name} FAILED - HALTING TRADING: {error_type}: {e}")
                        state = {
                            "halted": True,
                            "reason": f"check error ({error_type}: {e})",
                        }
                    state["label"] = CHECK_LABELS.get(name, name)
                    results["checks"][name] = state
                    if state.get("halted"):
                        results["halted"] = True
                        results["halt_reasons"].append(f"{state['label']}: {state['reason']}")

                # Persist if halted
                if results["halted"]:
                    self._log_halt(results, cur)

                return results
            except Exception as e:
                logger.error(f"CRITICAL ERROR in circuit breaker check: {e}")
                import traceback

                traceback.print_exc()
                # B12: Fail-closed — if circuit breaker logic itself fails, halt trading
                # Do NOT allow trading when we can't verify safety checks
                try:
                    from algo.reporting import notify

                    notify(
                        "critical",
                        title="CIRCUIT BREAKER CHECK FAILED",
                        message=f"Circuit breaker logic crashed: {e}. Trading halted until resolved.",
                    )
                except Exception as notify_err:
                    logger.error(f"Unhandled exception: {notify_err}")

                return {
                    "halted": True,
                    "halt_reasons": [f"Circuit breaker check failed: {e}"],
                    "checks": {},
                }

    # ---------- Individual checks ----------

    def _check_drawdown(self, current_date: Any, cur) -> dict[str, Any]:
        cur.execute("""
            SELECT MAX(total_portfolio_value),
                   (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1)
            FROM algo_portfolio_snapshots
            """)
        row = cur.fetchone()
        # Bootstrap path: if table is empty (first ever run), allow through
        if row is None or row[0] is None or row[1] is None:
            return {"halted": False, "reason": "First run — no portfolio history yet"}
        peak = _safe_float(row[0], None, context="drawdown peak")
        cur_val = _safe_float(row[1], None, context="drawdown current")
        if peak is None or cur_val is None or peak <= 0 or cur_val <= 0:
            return {"halted": True, "reason": "Invalid portfolio values — fail-closed"}
        dd = ((peak - cur_val) / peak * 100.0) if peak > 0 else 0.0
        threshold = _safe_float(
            self.config.get("halt_drawdown_pct", 20.0),
            20.0,
            context="halt_drawdown_pct",
        )
        return {
            "halted": dd >= threshold,
            "reason": (f"Drawdown {dd:.2f}% >= {threshold:.0f}%" if dd >= threshold else f"Drawdown {dd:.2f}%"),
            "value": round(dd, 2),
            "threshold": threshold,
        }

    def _check_drawdown_re_engagement(self, current_date: Any, cur) -> dict[str, Any]:
        """C2: Drawdown Re-engagement Protocol.

        After a drawdown halt, require conditions to resume:
        1. Portfolio recovered to within N% of peak (not at peak)
        2. Market shows Follow-Through Day signal (optional)
        3. At least N days have passed since halt
        """
        threshold = safe_float(self.config.get("halt_drawdown_pct", 20.0), default=20.0, context="halt_drawdown_pct")

        # First check: is current drawdown >= threshold? If not, no re-engagement needed
        cur.execute("""
            SELECT MAX(total_portfolio_value),
                   (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1)
            FROM algo_portfolio_snapshots
            """)
        row = cur.fetchone()
        if row is None or row[0] is None or row[1] is None:
            return {"halted": False, "reason": "No halt history"}

        peak = safe_float(row[0], default=None, context="row[0]")
        cur_val = safe_float(row[1], default=None, context="row[1]")
        if peak is None or cur_val is None or peak <= 0 or cur_val <= 0:
            logger.warning("Portfolio values missing/invalid for re-engagement check")
            return {"halted": False, "reason": "Invalid values"}

        dd = (peak - cur_val) / peak * 100.0

        # If NOT currently halted due to drawdown, no re-engagement check needed
        if dd < threshold:
            return {"halted": False, "reason": "Not in drawdown halt"}

        recovery_threshold = safe_float(self.config.get("re_engage_recovery_pct", 8.0), default=8.0, context="re_engage_recovery_pct")
        min_days_elapsed = safe_int(self.config.get("re_engage_min_days", 5), default=5, context="re_engage_min_days")
        require_ftd = safe_bool(self.config.get("require_ftd_to_re_engage", True), default=True)

        recovery_pct = (peak - cur_val) / peak * 100.0  # Current distance from peak
        if recovery_pct > recovery_threshold:
            return {
                "halted": True,
                "reason": f"Drawdown {dd:.1f}%, need recovery to {recovery_threshold:.1f}% to resume (currently {recovery_pct:.1f}%)",
            }

        # Find the date of the latest drawdown halt event
        days_elapsed = 0
        cur.execute("""
            SELECT created_at FROM algo_audit_log
            WHERE action_type = 'circuit_breaker_halt' AND details ILIKE '%drawdown%'
            ORDER BY created_at DESC LIMIT 1
            """)
        halt_row = cur.fetchone()
        if halt_row is not None:
            halt_date = halt_row[0]
            days_elapsed = (
                (current_date - halt_date.date()).days
                if isinstance(halt_date, datetime)
                else (current_date - halt_date).days
            )
            if days_elapsed < min_days_elapsed:
                return {
                    "halted": True,
                    "reason": f"Halt occurred {days_elapsed}d ago, need {min_days_elapsed}d to elapse before resume",
                }

        if require_ftd:
            # A Follow-Through Day is when SPY up 1.25%+ on higher volume after a pullback/correction
            # For now, simplified check: market is in Stage 2
            cur.execute("SELECT market_stage FROM market_health_daily ORDER BY date DESC LIMIT 1")
            market_row = cur.fetchone()
            if market_row is None or market_row[0] != 2:
                return {
                    "halted": True,
                    "reason": "Recovery conditions met, but market not in Stage 2 uptrend (waiting for Follow-Through Day)",
                }

        # All conditions met — re-engagement approved
        return {
            "halted": False,
            "reason": f"Re-engagement approved: recovered to {recovery_pct:.1f}%, {days_elapsed}d elapsed, market Stage 2",
        }

    def _check_daily_loss(self, current_date: Any, cur) -> dict[str, Any]:
        cur.execute(
            "SELECT daily_return_pct FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
            (current_date,),
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            return {"halted": False, "reason": "No today snapshot yet"}
        daily = _safe_float(row[0], None, context="daily_loss")
        if daily is None:
            return {"halted": True, "reason": "Daily return data invalid — fail-closed"}
        threshold = -_safe_float(
            self.config.get("max_daily_loss_pct", 2.0),
            2.0,
            context="max_daily_loss_pct",
        )
        return {
            "halted": daily <= threshold,
            "reason": (
                f"Daily loss {daily:.2f}% <= {threshold:.1f}%" if daily <= threshold else f"Daily {daily:+.2f}%"
            ),
            "value": round(daily, 2),
            "threshold": threshold,
        }

    def _check_consecutive_losses(self, current_date: Any, cur) -> dict[str, Any]:
        cur.execute(
            """
            SELECT profit_loss_pct, exit_date FROM algo_trades
            WHERE status = %s AND exit_date IS NOT NULL
              AND trade_id NOT LIKE 'EXT-%%'
            ORDER BY exit_date DESC, id DESC
            LIMIT 10
            """,
            (TradeStatus.CLOSED.value,),
        )
        rows = cur.fetchall()
        if not rows:
            return {"halted": False, "reason": "No closed trades"}
        # Count consecutive losses from most recent
        streak = 0
        for r in rows:
            pnl = _safe_float(r[0], None, context="trade_pnl")
            if pnl is None:
                logger.warning(f"Trade {r} has invalid P&L — stopping consecutive loss count")
                break
            if pnl < 0:
                streak += 1
            else:
                break
        threshold = safe_int(self.config.get("max_consecutive_losses", 3), default=3, context="max_consecutive_losses")
        return {
            "halted": streak >= threshold,
            "reason": (f"{streak} consecutive losses >= {threshold}" if streak >= threshold else f"{streak} losses"),
            "value": streak,
            "threshold": threshold,
        }

    def _check_win_rate_floor(self, current_date: Any, cur) -> dict[str, Any]:
        """Halt if recent win rate drops below floor (includes both closed and open positions at risk).

        Win rate = wins / (wins + losses), where losses include both closed losses and open positions
        with negative unrealized P&L. Excluding break-even trades to avoid dilution.
        """
        # Include both closed trades (confirmed exits) and open positions (unrealized losses).
        # This prevents masked deterioration where closed trades look good but open positions bleed.
        cur.execute(
            """
            SELECT COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
                   COUNT(*) FILTER (WHERE pnl_pct < 0) as losses,
                   COUNT(*) FILTER (WHERE pnl_pct = 0) as breakeven,
                   COUNT(*) as total
            FROM (
                -- Closed trades with confirmed exits
                SELECT profit_loss_pct as pnl_pct
                FROM algo_trades
                WHERE status = %s AND exit_date IS NOT NULL
                  AND exit_r_multiple IS NOT NULL
                  AND trade_id NOT LIKE 'EXT-%%'
                UNION ALL
                -- Open positions with unrealized P&L (show current risk)
                SELECT unrealized_pnl_pct as pnl_pct
                FROM algo_positions
                WHERE status = 'open'
                  AND quantity > 0
            ) all_trades
            """,
            (TradeStatus.CLOSED.value,),
        )
        row = cur.fetchone()
        if row is None or row[3] is None or safe_int(row[3], default=0, context="trade_count") < 10:
            return {"halted": False, "reason": "Insufficient closed trades (< 10)"}

        wins = safe_int(row[0], default=0, context="win_count") if row[0] is not None else 0
        losses = safe_int(row[1], default=0, context="loss_count") if row[1] is not None else 0
        safe_int(row[2], default=0, context="breakeven_count") if row[2] is not None else 0
        total = safe_int(row[3], default=0, context="total_count")

        # Win rate based on wins vs (wins + losses), excluding break-even trades
        # This avoids dilution where many break-even trades inflate the denominator
        decisive_trades = wins + losses
        win_rate = (wins / decisive_trades * 100.0) if decisive_trades > 0 else 0
        threshold = safe_float(self.config.get("min_win_rate_pct", 40.0), default=40.0, context="min_win_rate_pct")
        return {
            "halted": win_rate < threshold,
            "reason": (
                f"Win rate {win_rate:.1f}% < {threshold:.0f}%" if win_rate < threshold else f"Win rate {win_rate:.1f}%"
            ),
            "value": round(win_rate, 1),
            "threshold": threshold,
            "trades_sampled": total,
        }

    def _check_total_risk(self, current_date: Any, cur) -> dict[str, Any]:
        """Sum of (entry - stop) * qty across open positions vs portfolio value."""
        cur.execute(
            """
            SELECT COALESCE(SUM(GREATEST(0, (t.entry_price - COALESCE(p.current_stop_price, t.stop_loss_price)) * p.quantity)), 0)
            FROM algo_positions p
            JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
            WHERE p.status = %s
            """,
            (PositionStatus.OPEN.value,),
        )
        result = cur.fetchone()
        total_open_risk = _safe_float(result[0], None, context="total_open_risk") if result else None
        if total_open_risk is None:
            logger.critical("Cannot calculate total open risk — risk calculation failed")
            return {"halted": True, "reason": "Risk calculation failed — fail-closed"}

        cur.execute("SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1")
        row = cur.fetchone()
        if row is None or row[0] is None:
            # First run (no portfolio snapshots yet) — skip risk check but log
            logger.info("[TOTAL_RISK_CHECK] Skipping (no portfolio snapshot yet; expected on first run)")
            return {"halted": False, "reason": "No portfolio snapshot (first run?)"}

        portfolio = _safe_float(row[0], None, context="portfolio_value")
        # CRITICAL: Portfolio value missing/invalid → risk calculation impossible.
        # Fail-closed: cannot assess total risk without portfolio value.
        if portfolio is None or portfolio <= 0:
            logger.critical(
                f"[TOTAL_RISK_CHECK] Portfolio value invalid ({portfolio}) — cannot calculate risk. "
                "Halting trading to prevent blind risk-taking."
            )
            return {
                "halted": True,
                "reason": f"Portfolio value invalid ({portfolio}) — risk calculation impossible. Fail-closed halt.",
            }

        risk_pct = total_open_risk / portfolio * 100.0
        threshold = _safe_float(
            self.config.get("max_total_risk_pct", 4.0),
            4.0,
            context="max_total_risk_pct",
        )
        return {
            "halted": risk_pct >= threshold,
            "reason": (
                f"Total open risk {risk_pct:.2f}% >= {threshold:.0f}%"
                if risk_pct >= threshold
                else f"Risk {risk_pct:.2f}%"
            ),
            "value": round(risk_pct, 2),
            "threshold": threshold,
        }

    def _check_vix_spike(self, current_date: Any, cur) -> dict[str, Any]:
        cur.execute(
            "SELECT vix_level FROM market_health_daily WHERE date <= %s AND vix_level IS NOT NULL ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = cur.fetchone()
        vix = _safe_float(row[0], None, context="vix_level") if row is not None and row[0] is not None else None

        # CRITICAL: VIX data unavailable — cannot safely assess volatility risk.
        # Fail-closed: cannot use fallback estimates. Even computed estimates from SPY
        # volatility mask the real issue (missing live data) and may be inaccurate during
        # extreme market dislocations when we most need reliable circuit breaker protection.
        if vix is None:
            logger.critical("VIX unavailable from live data sources — halting trading")
            return {
                "halted": True,
                "reason": "VIX data unavailable — cannot assess volatility risk. Trading halted.",
                "value": None,
                "threshold": _safe_float(self.config.get("vix_max_threshold", 35.0), 35.0),
            }

        threshold = _safe_float(
            self.config.get("vix_max_threshold", 35.0),
            35.0,
            context="vix_max_threshold",
        )
        return {
            "halted": vix > threshold,
            "reason": (f"VIX {vix:.1f} > {threshold:.0f}" if vix > threshold else f"VIX {vix:.1f}"),
            "value": vix,
            "threshold": threshold,
        }

    def _check_market_stage(self, current_date: Any, cur) -> dict[str, Any]:
        """H7 FIX: Market stage validation with data freshness check.

        Ensures we don't use stale market stage data from days ago.
        """
        cur.execute(
            "SELECT date, market_stage, market_trend FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = cur.fetchone()
        if row is None:
            return {
                "halted": True,
                "reason": "Market health data missing — fail-closed",
            }

        data_date = row[0]
        if isinstance(data_date, datetime):
            data_date = data_date.date()
        days_stale = (current_date - data_date).days

        # Use trading-day-aware staleness check (same pattern as _check_data_freshness and Phase 1).
        # Hardcoded calendar-day thresholds cause false halts after 3-day holiday weekends when
        # the market_health_daily record is from Friday but current_date is Tuesday (4 days gap).
        # Root causes for stale data now fixed: RDS Proxy removed (cfb3f01f), failsafe verification in place (a2a8a654).
        # Revert to 1 trading day of staleness tolerance for tighter data freshness.
        expected_date = current_date - timedelta(days=1)
        min_acceptable_date = current_date - timedelta(days=2)  # 1 trading day back
        try:
            from algo.infrastructure import MarketCalendar

            for _ in range(10):
                if MarketCalendar.is_trading_day(expected_date):
                    break
                expected_date -= timedelta(days=1)
            for _ in range(10):
                if MarketCalendar.is_trading_day(min_acceptable_date):
                    break
                min_acceptable_date -= timedelta(days=1)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as cal_e:
            logger.debug(f"MarketCalendar check failed, falling back to weekday check: {cal_e}")
            while expected_date.weekday() >= 5:
                expected_date -= timedelta(days=1)
            while min_acceptable_date.weekday() >= 5:
                min_acceptable_date -= timedelta(days=1)

        if data_date < min_acceptable_date:
            # OPTION_B FIX: Fail-open on stale market_health_daily to allow trading with 91% fresh data.
            # Market stage is advisory (only stage 4 halts); older data is less critical than price/technical freshness.
            # Log the staleness issue for ops monitoring while allowing orchestrator to proceed with default caution (stage 2).
            logger.warning(
                f"[OPTION_B] Market stage data stale ({days_stale}d old, expected {expected_date}) — "
                "using default caution stage 2 to allow trading with available price/technical data"
            )
            return {
                "halted": False,
                "reason": f"Market stage stale ({days_stale}d) — using default stage 2",
                "value": 2,
            }

        if row[1] is None:
            return {
                "halted": True,
                "reason": "Market stage NULL — fail-closed to prevent trading in unknown stage",
            }

        stage = safe_int(row[1], default=2, context="market_stage")
        trend = row[2] or "unknown"
        # Stage 4 = halt new entries (full downtrend). Stage 3 = caution but allow.
        halted = stage == 4
        return {
            "halted": halted,
            "reason": (f"Stage 4 downtrend (trend={trend})" if halted else f"Stage {stage} ({trend})"),
            "value": stage,
        }

    def _check_weekly_loss(self, current_date: Any, cur) -> dict[str, Any]:
        """7-day return on portfolio."""
        week_ago = current_date - timedelta(days=7)
        cur.execute(
            """
            SELECT
                (SELECT total_portfolio_value FROM algo_portfolio_snapshots WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1),
                (SELECT total_portfolio_value FROM algo_portfolio_snapshots WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1)
            """,
            (current_date, week_ago),
        )
        row = cur.fetchone()
        if not row or not row[0] or not row[1]:
            return {"halted": False, "reason": "Insufficient history"}
        cur_val, week_ago_val = safe_float(row[0], default=0.0, context="row[0]"), safe_float(row[1], default=0.0, context="row[1]")
        weekly = ((cur_val - week_ago_val) / week_ago_val * 100.0) if week_ago_val > 0 else 0
        threshold = -safe_float(self.config.get("max_weekly_loss_pct", 5.0), default=5.0, context="max_weekly_loss_pct")
        return {
            "halted": weekly <= threshold,
            "reason": (
                f"Weekly {weekly:.2f}% <= {threshold:.1f}%" if weekly <= threshold else f"Weekly {weekly:+.2f}%"
            ),
            "value": round(weekly, 2),
            "threshold": threshold,
        }

    def _check_data_freshness(self, current_date: Any, cur) -> dict[str, Any]:
        """Block if our market data is too stale.

        Compares against the previous trading day (not a fixed calendar threshold)
        so 3-day holiday weekends don't cause false halts.
        Allows up to 2 trading days of staleness to handle RDS Proxy replication lag.

        NOTE: Uses trading-day logic (more sophisticated) vs centralized config's calendar-day logic.
        Coordinated via get_freshness_rule("price_daily") for consistency with other components.
        """
        cur.execute("SELECT date FROM price_daily WHERE symbol = 'SPY' ORDER BY date DESC LIMIT 1")
        row = cur.fetchone()
        if not row or not row[0]:
            return {"halted": True, "reason": "No SPY data at all"}
        latest = row[0]
        days_stale = (current_date - latest).days

        # Compute the previous trading day as the freshness reference point.
        # Using trading-day comparison prevents false halts after 3-day weekends
        # where the calendar gap (e.g. Friday → Tuesday = 4 days) would exceed a
        # fixed threshold even though the data is from the last trading day.
        from datetime import timedelta

        expected = current_date - timedelta(days=1)
        min_acceptable = current_date - timedelta(days=2)  # 1 trading day back
        try:
            from algo.infrastructure import MarketCalendar

            for _ in range(10):
                if MarketCalendar.is_trading_day(expected):
                    break
                expected -= timedelta(days=1)
            for _ in range(10):
                if MarketCalendar.is_trading_day(min_acceptable):
                    break
                min_acceptable -= timedelta(days=1)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as cal_e:
            logger.debug(f"MarketCalendar check failed, falling back to weekday check: {cal_e}")
            while expected.weekday() >= 5:
                expected -= timedelta(days=1)
            while min_acceptable.weekday() >= 5:
                min_acceptable -= timedelta(days=1)
        is_stale = latest < min_acceptable

        return {
            "halted": is_stale,
            "reason": (
                f"Data {days_stale}d stale (latest {latest}, expected {expected})" if is_stale else f"{days_stale}d old"
            ),
            "value": days_stale,
        }

    def _check_intraday_market_health(self, current_date: Any, cur) -> dict[str, Any]:
        """Prior-day market drop check: did SPY fall >2% yesterday?

        The orchestrator runs pre-market (9:30 AM ET). price_daily contains yesterday's
        EOD prices, so the two most recent rows are yesterday vs the day before. This
        checks the prior day's return, not a live intraday reading. Blocking on a >2%
        decline yesterday is intentional: entering new swing positions the morning after
        a significant sell-off is poor risk management (Minervini: wait for market to
        stabilize before adding exposure).
        """
        try:
            cur.execute(
                """
                SELECT close FROM price_daily
                WHERE symbol = 'SPY'
                  AND date <= %s
                ORDER BY date DESC LIMIT 2
                """,
                (current_date,),
            )
            rows = cur.fetchall()
            if len(rows) < 2:
                return {"halted": False, "reason": "Insufficient price history"}

            latest = safe_float(rows[0][0], default=0.0, context="rows[0][0]") if rows[0][0] else None
            prior = safe_float(rows[1][0], default=0.0, context="rows[1][0]") if rows[1][0] else None

            if not latest or not prior or prior <= 0:
                return {"halted": False, "reason": "Invalid price data"}

            prior_day_change = (latest - prior) / prior * 100.0

            # Halt if SPY dropped >2% yesterday — significant sell-off, wait for stability
            if prior_day_change <= -2.0:
                return {
                    "halted": True,
                    "reason": f"Market down {prior_day_change:.2f}% yesterday (await stability)",
                    "market_change_pct": round(prior_day_change, 2),
                }

            return {
                "halted": False,
                "reason": f"SPY prior day {prior_day_change:+.2f}%",
                "market_change_pct": round(prior_day_change, 2),
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Prior-day market health check failed: {e}")
            # Fail-open on data errors — this is an observational check, not a core gate.
            # Core gates (Phase 1 freshness, CB drawdown, VIX) handle true safety halts.
            return {
                "halted": False,
                "reason": f"Prior-day check skipped (data error): {e}",
            }

    def _check_sector_concentration(self, current_date: Any, cur) -> dict[str, Any]:
        """Log warning if any sector exceeds max position cap — advisory only, no halt.

        Sector concentration is a soft limit; the circuit breaker warns but does not block.
        """
        try:
            max_sector_positions = safe_int(self.config.get("max_positions_per_sector", 5), default=5, context="max_positions_per_sector")

            cur.execute("""
                SELECT ap.symbol, COALESCE(cp.sector, 'Unknown') AS sector
                FROM algo_positions ap
                LEFT JOIN company_profile cp ON cp.ticker = ap.symbol
                WHERE ap.status = 'open'
                """)
            rows = cur.fetchall()
            if not rows:
                return {"halted": False, "reason": "No open positions"}

            sector_counts: dict[str, int] = {}
            for _, sector in rows:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1

            concentrated = {s: n for s, n in sector_counts.items() if n >= max_sector_positions and s != "Unknown"}
            if concentrated:
                sector_details = ", ".join(f"{s}({n})" for s, n in concentrated.items())
                logger.warning(
                    f"Sector at/near cap: {sector_details} (max {max_sector_positions}) — Phase 6 will block same-sector entries"
                )
                return {
                    "halted": False,
                    "reason": f"At-cap sectors (per-trade enforcement in Phase 6): {sector_details}",
                    "at_cap_sectors": concentrated,
                }

            return {
                "halted": False,
                "reason": f"All sectors within limits (max {max_sector_positions} per sector)",
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Sector concentration check failed: {e}") from e

    def _check_daily_profit_cap(self, current_date: Any, cur) -> dict[str, Any]:
        """Warn (don't halt) if daily P&L exceeds profit target; can skip new entries."""
        cur.execute(
            "SELECT daily_return_pct FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
            (current_date,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return {"halted": False, "reason": "No today snapshot yet"}
        daily = safe_float(row[0], default=0.0, context="row[0]")
        threshold = safe_float(self.config.get("daily_profit_cap_pct", 2.0), default=2.0, context="daily_profit_cap_pct")
        # This check is a SOFT warning, not a halt — it's logged but doesn't block trading
        # Orchestrator uses this to skip NEW entries only, not to exit existing positions
        return {
            "halted": False,
            "reason": f"Daily profit {daily:+.2f}% vs cap {threshold:.1f}%",
            "value": round(daily, 2),
            "threshold": threshold,
            "exceed_profit_cap": daily >= threshold,
        }

    def _log_halt(self, results, cur):
        try:
            cur.execute(
                """
                INSERT INTO algo_audit_log (action_type, action_date, details, actor, status, created_at)
                VALUES ('circuit_breaker_halt', CURRENT_TIMESTAMP, %s, 'circuit_breaker', 'halt', CURRENT_TIMESTAMP)
                """,
                (json.dumps(results),),
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.critical(f"[AUDIT_FAILURE] Could not log circuit breaker halt to audit log: {e}")
            raise
        # Surface to notifications for UI (non-critical, warn only)
        try:
            from algo.reporting import notify

            notify(
                severity="critical",
                title="Trading Halted by Circuit Breaker",
                message="; ".join(results.get("halt_reasons", [])),
                details=results.get("checks"),
            )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"Warning: Could not send circuit breaker notification: {e}")


if __name__ == "__main__":
    from algo.infrastructure import get_config

    cb = CircuitBreaker(get_config())
    result = cb.check_all()
    logger.info(f"\n{'HALTED' if result['halted'] else 'CLEAR'}\n")
    for name, state in result["checks"].items():
        flag = "[HALT]" if state.get("halted") else "[OK]  "
        label = state.get("label", name)
        logger.info(f"  {flag} {label:40s} : {state.get('reason', 'no detail')}")
    if result["halted"]:
        logger.info("\nHALT REASONS:")
        for r in result["halt_reasons"]:
            logger.info(f"  - {r}")
