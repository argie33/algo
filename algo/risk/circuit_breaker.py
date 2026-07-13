from __future__ import annotations

import json
import logging
import math
from datetime import date as _date
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import psycopg2

from utils.db import DatabaseContext
from utils.trading import PositionStatus, TradeStatus

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig


logger = logging.getLogger(__name__)

"""
Circuit Breakers - Kill-switch risk halts (institutional safety layer)

Halts trading when any of these fire:
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


def _float(value: Any, default: float | None = None, context: str = "") -> float:
    """Convert to float safely, rejecting NaN/Infinity.

    CRITICAL: When default is NOT provided (None), raises on missing data.
    Circuit breaker checks require exact data — missing critical values must
    cause failures, not silent defaults.

    Args:
        value: Value to convert
        default: Default value if conversion fails (None = fail-fast on missing)
        context: Description for error messages

    Raises:
        ValueError: If value is None and no default provided, or if value is NaN/Infinity

    Returns:
        Converted float value, or default if conversion fails and default provided
    """
    if value is None:
        if default is None:
            raise ValueError(f"Circuit breaker metric is missing (required, not optional) {context}")
        return default
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            if default is None:
                raise ValueError(f"Invalid float {value!r} (NaN/Inf) {context}")
            return default
        return f
    except (ValueError, TypeError) as e:
        if default is None:
            raise ValueError(f"Failed to convert {value!r} to float {context}") from e
        return default


class CircuitBreaker:
    """Pre-trade kill-switch checks."""

    _check_registry = [
        "daily_loss",
        "drawdown",
        "drawdown_re_engagement",
        "consecutive_losses",
        "total_risk",
        "vix_spike",
        "market_stage",
        "weekly_loss",
        "sector_concentration",
        "intraday_market_health",
        "win_rate_floor",
        "daily_profit_cap",
        "data_freshness",
    ]

    def __init__(self, config: AlgoConfig | dict[str, Any]) -> None:
        self.config = config

    def _get_required_config(self, key: str, context: str = "") -> Any:
        """Get a required config value. Raises ValueError if missing.

        In circuit breaker validation, missing thresholds must ALWAYS cause failure.
        There are no safe defaults for risk control parameters.
        """
        value = self.config.get(key)
        if value is None:
            raise ValueError(f"CRITICAL: Required circuit breaker config '{key}' is missing {context}")
        return value

    def check_all(self, current_date: Any = None) -> dict[str, Any]:
        """Run all circuit breakers. Returns dict with per-check status."""
        if not current_date:
            current_date = _date.today()

        with DatabaseContext("write") as cur:
            try:
                # Remove stale positions with no algo trade association before checking risk.
                # A prior sync bug inserted rows using Alpaca's asset_id as position_id,
                # giving them NULL current_stop_price and no trade_ids_arr. These orphans
                # trip the total_risk check even though they aren't real algo positions.
                cur.execute("""
                    DELETE FROM algo_positions
                    WHERE status = 'open'
                      AND current_stop_price IS NULL
                      AND (trade_ids_arr IS NULL OR array_length(trade_ids_arr, 1) IS NULL)
                """)
                orphans_removed = cur.rowcount
                if orphans_removed > 0:
                    logger.warning(
                        f"[CIRCUIT_BREAKER] Removed {orphans_removed} orphan position(s) "
                        "with no trade associations before risk checks"
                    )

                results: dict[str, Any] = {
                    "halted": False,
                    "halt_reasons": [],
                    "checks": {},
                }

                for check_name in self._check_registry:
                    try:
                        fn = getattr(self, f"_check_{check_name}")
                        state = fn(current_date, cur)
                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                        import traceback

                        tb = traceback.format_exc()
                        error_type = type(e).__name__

                        # Log full traceback for debugging
                        logger.error(f"Circuit breaker {check_name} raised {error_type}: {e}")
                        logger.error(f"Full traceback:\n{tb}")

                        # All check failures result in fail-closed halt.
                        # If a safety check cannot be verified, trading must halt.
                        # Do NOT skip checks with "transient" claims — that masks data loss.
                        logger.critical(f"Circuit breaker {check_name} FAILED - HALTING TRADING: {error_type}: {e}")
                        state = {
                            "halted": True,
                            "reason": f"check error ({error_type}: {e})",
                        }
                    state["label"] = CHECK_LABELS.get(check_name, check_name)
                    results["checks"][check_name] = state
                    if "halted" not in state:
                        raise ValueError(
                            f"Circuit breaker check '{check_name}' missing required 'halted' field in state: {state}"
                        )
                    if state["halted"]:
                        results["halted"] = True
                        results["halt_reasons"].append(f"{state['label']}: {state['reason']}")

                # Persist if halted
                if results["halted"]:
                    self._log_halt(results, cur)

                return results
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"CRITICAL ERROR in circuit breaker check: {e}", exc_info=True)
                # B12: Fail-closed — if circuit breaker logic itself fails, halt trading
                # Do NOT allow trading when we can't verify safety checks
                try:
                    from algo.reporting import notify

                    notify(
                        "critical",
                        title="CIRCUIT BREAKER CHECK FAILED",
                        message=f"Circuit breaker logic crashed: {e}. Trading halted until resolved.",
                    )
                except (ValueError, TypeError) as notify_err:
                    logger.error(f"Failed to send notification: {notify_err}")

                return {
                    "halted": True,
                    "halt_reasons": [f"Circuit breaker check failed: {e}"],
                    "checks": {},
                }

    # ---------- Individual checks ----------

    def _check_drawdown(self, current_date: Any, cur: Any) -> dict[str, Any]:
        cur.execute("""
            SELECT MAX(total_portfolio_value),
                   (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1)
            FROM algo_portfolio_snapshots
            """)
        row = cur.fetchone()
        # Bootstrap path: if table is empty (first ever run), allow through with explicit logging
        if row is None or row[0] is None or row[1] is None:
            logger.warning(
                "[CIRCUIT_BREAKER] Bootstrap path: no portfolio history available yet. "
                "Allowing initial trading while history accumulates. "
                "Subsequent runs will require valid portfolio peak/current values."
            )
            return {"halted": False, "reason": "Bootstrap: no portfolio history yet"}
        peak = _float(row[0], None, context="drawdown peak")
        cur_val = _float(row[1], None, context="drawdown current")
        if peak is None or cur_val is None or peak <= 0 or cur_val <= 0:
            return {"halted": True, "reason": "Invalid portfolio values — fail-closed"}
        dd = (peak - cur_val) / peak * 100.0
        halt_dd_val = self._get_required_config("halt_drawdown_pct", "in drawdown check")
        threshold = _float(
            halt_dd_val,
            None,
            context="halt_drawdown_pct",
        )
        if threshold is None:
            logger.error("CRITICAL: halt_drawdown_pct is invalid (NaN/Inf). Circuit breaker cannot function.")
            return {"halted": True, "reason": "CRITICAL: halt_drawdown_pct invalid"}
        # halt_drawdown_pct is stored as negative (e.g. -20.0 = halt at 20% down).
        # dd is computed as a positive percentage drop from peak.
        halt_threshold = abs(threshold)
        return {
            "halted": dd >= halt_threshold,
            "reason": (
                f"Drawdown {dd:.2f}% >= {halt_threshold:.0f}%" if dd >= halt_threshold else f"Drawdown {dd:.2f}%"
            ),
            "value": round(dd, 2),
            "threshold": threshold,
        }

    def _check_daily_loss(self, current_date: Any, cur: Any) -> dict[str, Any]:
        cur.execute(
            "SELECT daily_return_pct FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
            (current_date,),
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            return {"halted": False, "reason": "No today snapshot yet"}
        daily = _float(row[0], None, context="daily_loss")
        if daily is None:
            return {"halted": True, "reason": "Daily return data invalid — fail-closed"}
        max_daily_val = self._get_required_config("max_daily_loss_pct", "in daily loss check")
        threshold = -_float(
            max_daily_val,
            None,
            context="max_daily_loss_pct",
        )
        if threshold is None or threshold == 0.0:
            logger.error("CRITICAL: max_daily_loss_pct is invalid. Cannot enforce daily loss circuit breaker.")
            return {"halted": True, "reason": "CRITICAL: max_daily_loss_pct invalid"}
        return {
            "halted": daily <= threshold,
            "reason": (
                f"Daily loss {daily:.2f}% <= {threshold:.1f}%" if daily <= threshold else f"Daily {daily:+.2f}%"
            ),
            "value": round(daily, 2),
            "threshold": threshold,
        }

    def _check_consecutive_losses(self, current_date: Any, cur: Any) -> dict[str, Any]:
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
        # Count consecutive losses from most recent. Skip trades with NULL P&L (incomplete data).
        # Do not default NULL to 0 (would mask incomplete records), but do skip rather than fail.
        streak = 0
        for r in rows:
            if r[0] is None:
                # Skip trades with incomplete exit data; do not count as losses
                logger.debug("Skipping trade with NULL P&L in consecutive loss check")
                continue
            pnl = _float(r[0], None, context="trade_pnl")
            if pnl < 0:
                streak += 1
            else:
                break
        max_consec_val = self._get_required_config("max_consecutive_losses", "in consecutive losses check")
        threshold = int(max_consec_val)
        return {
            "halted": streak >= threshold,
            "reason": (f"{streak} consecutive losses >= {threshold}" if streak >= threshold else f"{streak} losses"),
            "value": streak,
            "threshold": threshold,
        }

    def _check_vix_spike(self, current_date: Any, cur: Any) -> dict[str, Any]:
        cur.execute(
            "SELECT vix_level FROM market_health_daily WHERE date <= %s AND vix_level IS NOT NULL ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = cur.fetchone()
        # First check if row/data exists; if not, return None for later detection
        if row is None or row[0] is None:
            vix = None
        else:
            # Row data exists — validate with _float to reject NaN/Inf
            try:
                vix = _float(row[0], context="vix_level")
            except ValueError:
                # NaN/Inf in vix_level — treat as missing data
                vix = None

        # CRITICAL: VIX data unavailable — cannot safely assess volatility risk.
        # Fail-closed: cannot use fallback estimates. Even computed estimates from SPY
        # volatility mask the real issue (missing live data) and may be inaccurate during
        # extreme market dislocations when we most need reliable circuit breaker protection.
        vix_max_val = self._get_required_config("vix_max_threshold", "in VIX circuit breaker check")

        if vix is None:
            logger.critical("VIX unavailable from live data sources — halting trading")
            return {
                "halted": True,
                "reason": "VIX data unavailable — cannot assess volatility risk. Trading halted.",
                "value": None,
                "threshold": _float(vix_max_val, None),
            }

        threshold = _float(
            vix_max_val,
            None,
            context="vix_max_threshold",
        )
        if threshold is None:
            logger.error("CRITICAL: vix_max_threshold is invalid (NaN/Inf). Cannot enforce VIX circuit breaker.")
            return {"halted": True, "reason": "CRITICAL: vix_max_threshold invalid"}
        return {
            "halted": vix > threshold,
            "reason": (f"VIX {vix:.1f} > {threshold:.0f}" if vix > threshold else f"VIX {vix:.1f}"),
            "value": vix,
            "threshold": threshold,
        }

    def _check_weekly_loss(self, current_date: Any, cur: Any) -> dict[str, Any]:
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
        if row is None or len(row) < 2 or row[0] is None or row[1] is None:
            return {"halted": False, "reason": "Insufficient history"}
        cur_val, week_ago_val = float(row[0]), float(row[1])
        if week_ago_val <= 0:
            logger.critical(
                f"CRITICAL: Week-ago portfolio value invalid ({week_ago_val}) — cannot calculate weekly return"
            )
            return {"halted": True, "reason": "CRITICAL: Portfolio history data invalid"}
        weekly = (cur_val - week_ago_val) / week_ago_val * 100.0
        max_weekly_val = self._get_required_config("max_weekly_loss_pct", "in weekly loss check")
        try:
            threshold = -float(max_weekly_val)
            if (
                threshold == 0 or (threshold != threshold) or threshold == float("inf") or threshold == float("-inf")
            ):  # NaN/Inf check
                raise ValueError(f"max_weekly_loss_pct invalid ({max_weekly_val})")
        except (ValueError, TypeError) as e:
            logger.critical(
                f"CRITICAL: max_weekly_loss_pct configuration invalid — cannot enforce weekly loss limit: {e}"
            )
            return {"halted": True, "reason": "CRITICAL: max_weekly_loss_pct configuration invalid"}
        return {
            "halted": weekly <= threshold,
            "reason": (
                f"Weekly {weekly:.2f}% <= {threshold:.1f}%" if weekly <= threshold else f"Weekly {weekly:+.2f}%"
            ),
            "value": round(weekly, 2),
            "threshold": threshold,
        }

    def _check_data_freshness(self, current_date: Any, cur: Any) -> dict[str, Any]:
        """Block if our market data is too stale.

        Compares against the previous trading day (not a fixed calendar threshold)
        so 3-day holiday weekends don't cause false halts.
        Allows up to 2 trading days of staleness to handle RDS Proxy replication lag.

        NOTE: Uses trading-day logic (more sophisticated) vs centralized config's calendar-day logic.
        Coordinated via get_freshness_rule("price_daily") for consistency with other components.
        CRITICAL: MarketCalendar must succeed; cannot fall back to weekday logic (misses holidays).
        """
        cur.execute("SELECT date FROM price_daily WHERE symbol = 'SPY' ORDER BY date DESC LIMIT 1")
        row = cur.fetchone()
        if row is None or len(row) < 1 or row[0] is None:
            return {"halted": True, "reason": "No SPY data at all"}
        latest = row[0]
        days_stale = (current_date - latest).days

        # Compute the previous trading day as the freshness reference point.
        # Using trading-day comparison prevents false halts after 3-day weekends
        # where the calendar gap (e.g. Friday -> Tuesday = 4 days) would exceed a
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
            logger.critical(
                f"MarketCalendar check failed: {cal_e}. "
                "Cannot fall back to weekday logic — holidays would be misclassified. "
                "Failing closed to prevent false staleness determination."
            )
            return {
                "halted": True,
                "reason": f"Market calendar unavailable ({type(cal_e).__name__}). Cannot determine trading days accurately. Fail-closed halt.",
                "value": days_stale,
            }
        is_stale = latest < min_acceptable

        return {
            "halted": is_stale,
            "reason": (
                f"Data {days_stale}d stale (latest {latest}, expected {expected})" if is_stale else f"{days_stale}d old"
            ),
            "value": days_stale,
        }

    def _check_sector_concentration(self, current_date: Any, cur: Any) -> dict[str, Any]:
        """Log warning if any sector exceeds max position cap — advisory only, no halt.

        Sector concentration is a soft limit; the circuit breaker warns but does not block.
        """
        try:
            max_sector_val = self._get_required_config("max_positions_per_sector", "in sector concentration check")
            max_sector_positions = int(max_sector_val)

            cur.execute("""
                -- CRITICAL FIX: Return NULL for missing sector (don't hide with 'Unknown')
                SELECT ap.symbol, cp.sector
                FROM algo_positions ap
                LEFT JOIN company_profile cp ON cp.ticker = ap.symbol
                WHERE ap.status = 'open'
                """)
            rows = cur.fetchall()
            if not rows:
                return {"halted": False, "reason": "No open positions"}

            sector_counts: dict[str, int] = {}
            for row in rows:
                if not row or len(row) < 2:
                    raise RuntimeError(f"Sector concentration check: invalid row structure {row}")
                _, sector = row[0], row[1]
                if not sector:
                    raise RuntimeError("Sector concentration check: row has None/empty sector")
                if sector not in sector_counts:
                    sector_counts[sector] = 0
                sector_counts[sector] += 1

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

    def _check_daily_profit_cap(self, current_date: Any, cur: Any) -> dict[str, Any]:
        """Warn (don't halt) if daily P&L exceeds profit target; can skip new entries."""
        cur.execute(
            "SELECT daily_return_pct FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
            (current_date,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return {"halted": False, "reason": "No today snapshot yet"}
        daily = float(row[0])
        daily_profit_val = self._get_required_config("daily_profit_cap_pct", "in daily profit cap check")
        threshold = float(daily_profit_val)
        # This check is a SOFT warning, not a halt — it's logged but doesn't block trading
        # Orchestrator uses this to skip NEW entries only, not to exit existing positions
        return {
            "halted": False,
            "reason": f"Daily profit {daily:+.2f}% vs cap {threshold:.1f}%",
            "value": round(daily, 2),
            "threshold": threshold,
            "exceed_profit_cap": daily >= threshold,
        }

    def _log_halt(self, results: dict[str, Any], cur: Any) -> None:
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

            if "halt_reasons" not in results:
                logger.error("Circuit breaker results missing 'halt_reasons' field")
                halt_msg = "Trading halted (reason unavailable)"
            else:
                halt_reasons = results["halt_reasons"]
                if not isinstance(halt_reasons, list):
                    logger.error(f"halt_reasons is not a list: {type(halt_reasons)}")
                    halt_msg = "Trading halted (reason unavailable)"
                elif not halt_reasons:
                    halt_msg = "Trading halted (no specific reason provided)"
                else:
                    halt_msg = "; ".join(halt_reasons)

            notify(
                severity="critical",
                title="Trading Halted by Circuit Breaker",
                message=halt_msg,
                details=results.get("checks"),
            )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"Warning: Could not send circuit breaker notification: {e}")
