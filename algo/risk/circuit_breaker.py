from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from datetime import date, datetime, timedelta
from datetime import date as _date
from typing import TYPE_CHECKING, Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

from utils.db import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.trading import PositionStatus, TradeStatus

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig


logger = logging.getLogger(__name__)

"""
Circuit Breakers - Kill-switch risk halts (institutional safety layer)

NOTE: this is the live pretrade halt gate. loaders/compute_circuit_breakers.py
computes a SEPARATE dashboard/reporting table (circuit_breaker_status) with its
own, differently-numbered CB1-CB9 scheme - they only agree on CB1/CB2/CB3/CB6.
Do not assume a "CBn" reference from one file means the same check in the other.

Halts trading when any of these fire:
  CB1. PORTFOLIO DRAWDOWN  >= halt_drawdown_pct (default 20%)
  CB2. DAILY LOSS          >= max_daily_loss_pct (default 2%)
  CB3. CONSECUTIVE LOSSES  >= max_consecutive_losses (default 3)
  CB4. TOTAL OPEN RISK     >= max_total_risk_pct (default 4%)
  CB5. VIX SPIKE           > vix_max_threshold (default 35)
  CB6. MARKET STAGE BREAK  market_stage = 4 (downtrend)
  CB7. WEEKLY LOSS         >= max_weekly_loss_pct (default 5%)
  CB8. DATA STALENESS      latest data > N days old
  CB9. SECTOR DRAWDOWN     <= sector_drawdown_halt_pct (default -12%, cost-basis weighted)

Each check returns (halted, reason). The orchestrator runs all checks before
new entries - any halt blocks new positions but does NOT auto-exit existing
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
    "sector_drawdown": "Sector Drawdown Halt",
    "intraday_market_health": "Market Instability (Prior-Day Drop)",
    "win_rate_floor": "Win Rate Floor Breached",
    "daily_profit_cap": "Daily Profit Target Reached",
    "data_freshness": "Data Staleness Check",
}


def _float(value: Any, default: float | None = None, context: str = "") -> float:
    """Convert to float safely, rejecting NaN/Infinity.

    CRITICAL: When default is NOT provided (None), raises on missing data.
    Circuit breaker checks require exact data - missing critical values must
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
        "sector_drawdown",
        "intraday_market_health",
        "win_rate_floor",
        "daily_profit_cap",
        "data_freshness",
    ]

    def __init__(self, config: AlgoConfig | dict[str, Any]) -> None:
        self.config = config
        # Explicit name -> bound-method map (NOT getattr(self, f"_check_{name}")).
        # check_all() previously resolved these dynamically by string, which made every
        # _check_* method look unused to static "dead code" analysis and get deleted by
        # automated cleanup passes multiple times. Referencing each method directly here
        # is a real, greppable usage that keeps them from being flagged as dead code.
        self._checks: dict[str, Callable[[Any, Any], dict[str, Any]]] = {
            "daily_loss": self._check_daily_loss,
            "drawdown": self._check_drawdown,
            "drawdown_re_engagement": self._check_drawdown_re_engagement,
            "consecutive_losses": self._check_consecutive_losses,
            "total_risk": self._check_total_risk,
            "vix_spike": self._check_vix_spike,
            "market_stage": self._check_market_stage,
            "weekly_loss": self._check_weekly_loss,
            "sector_concentration": self._check_sector_concentration,
            "sector_drawdown": self._check_sector_drawdown,
            "intraday_market_health": self._check_intraday_market_health,
            "win_rate_floor": self._check_win_rate_floor,
            "daily_profit_cap": self._check_daily_profit_cap,
            "data_freshness": self._check_data_freshness,
        }

    def _get_required_config(self, key: str, context: str = "") -> Any:
        """Get a required config value. Raises ValueError if missing.

        In circuit breaker validation, missing thresholds must ALWAYS cause failure.
        There are no safe defaults for risk control parameters.
        """
        value = self.config.get(key)
        if value is None:
            raise ValueError(f"CRITICAL: Required circuit breaker config '{key}' is missing {context}")
        return value

    def check_all(self, current_date: date | datetime | None = None) -> dict[str, Any]:
        """Run all circuit breakers. Returns dict with per-check status."""
        if current_date is None:
            # Eastern Time, not system-local date.today() - current_date feeds every
            # date-filtered check below (daily_loss, weekly_loss, etc.). The only
            # production caller (phase2_circuit_breakers.py) always passes run_date
            # explicitly, so this default isn't live-reachable today, but fixed defensively
            # to the same Eastern-Time convention as every other eval_date default in this
            # codebase (2026-07-21 audit) rather than leave a known-bad pattern for a future
            # caller (script, test, direct invocation) to inherit.
            current_date = datetime.now(EASTERN_TZ).date()
        elif isinstance(current_date, datetime):
            current_date = current_date.date()

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
                        fn = self._checks[check_name]
                        state = fn(current_date, cur)
                    except Exception as e:
                        # CRITICAL FIX: previously only caught (psycopg2.DatabaseError,
                        # psycopg2.OperationalError) - stress-tested live and confirmed a plain
                        # ValueError (e.g. a malformed algo_config value) from any individual
                        # _check_* method propagated straight out of check_all() uncaught,
                        # contradicting this exact comment block's own stated contract ("All
                        # check failures result in fail-closed halt"). check_all() only stayed
                        # safe in practice because both of its current callers
                        # (phase2_circuit_breakers.py, utils/orchestrator_diagnostics.py)
                        # happen to also wrap it in a broad except Exception - a landmine for
                        # any future caller that reasonably trusts this function's own
                        # docstring ("Returns dict with per-check status") instead of
                        # independently re-adding that same broad catch. Widened to catch
                        # every exception type, not just DB errors, so check_all() is
                        # genuinely self-contained and fail-closed regardless of caller.
                        import traceback

                        tb = traceback.format_exc()
                        error_type = type(e).__name__
                        safe_tb = tb.replace("{", "{{").replace("}", "}}")

                        # Log full traceback for debugging
                        logger.error(f"Circuit breaker {check_name} raised {error_type}: {e}")
                        logger.error(f"Full traceback:\n{safe_tb}")

                        # All check failures result in fail-closed halt.
                        # If a safety check cannot be verified, trading must halt.
                        # Do NOT skip checks with "transient" claims - that masks data loss.
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
            except Exception as e:
                # CRITICAL FIX: previously only caught (psycopg2.DatabaseError,
                # psycopg2.OperationalError) - widened for the same reason as the per-check
                # handler above (see its comment): a non-DB exception anywhere in this method
                # (e.g. the "missing 'halted' field" ValueError a few lines up, or a bug in
                # _log_halt) must fail closed here directly, not rely on every caller
                # independently re-adding a broad except Exception around check_all().
                logger.error(f"CRITICAL ERROR in circuit breaker check: {e}", exc_info=True)
                # B12: Fail-closed - if circuit breaker logic itself fails, halt trading
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

    def _check_drawdown(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        # Uses adjusted_equity/adjusted_running_peak (cash-flow-adjusted), NOT raw
        # total_portfolio_value/running_peak. Raw equity moves for two different reasons:
        # trading performance AND external capital flows (deposits/withdrawals). A withdrawal
        # looks identical to a trading loss in the raw series, which is exactly the bug fixed
        # by migration 1134 (see algo_capital_flows) - this circuit breaker must measure
        # trading performance, not account size. Every capital flow must be recorded in
        # algo_capital_flows (see scripts/record_capital_flow.py) or it will misreport here.
        # CRITICAL FIX: bound the "current" subquery by current_date - an unbounded
        # "ORDER BY snapshot_date DESC LIMIT 1" picks up any stray future-dated row (e.g. a
        # leftover local --date simulation snapshot in the shared dev DB) ahead of the real
        # current one, corrupting the drawdown halt check with the wrong equity value.
        # Live-reproduced 2026-08-09: a leftover 2026-08-11 test snapshot outranked the real
        # current run's own snapshot. _check_daily_loss below already bounds by current_date
        # correctly - this sibling check (and _check_drawdown_re_engagement) had been missed.
        # MAX(adjusted_equity) for the peak is intentionally unbounded (all-time high).
        cur.execute(
            """
            SELECT MAX(adjusted_equity),
                   (SELECT adjusted_equity FROM algo_portfolio_snapshots
                    WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1)
            FROM algo_portfolio_snapshots
            """,
            (current_date,),
        )
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
            return {"halted": True, "reason": "Invalid portfolio values - fail-closed"}
        dd = (peak - cur_val) / peak * 100.0
        halt_dd_val = self._get_required_config("halt_drawdown_pct", "in drawdown check")
        # _float(val, default=None, ...) raises ValueError on invalid/NaN/Inf input rather than
        # returning None (see its docstring/impl) - an `if threshold is None` guard here would be
        # dead code. An invalid config value propagates as an exception instead, caught by
        # phase2_circuit_breakers.py's outer handler, which still halts (fail-closed either way).
        threshold = _float(
            halt_dd_val,
            None,
            context="halt_drawdown_pct",
        )
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

    def _check_drawdown_re_engagement(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """C2: Drawdown Re-engagement Protocol.

        After a drawdown halt, require conditions to resume:
        1. Portfolio recovered to within N% of peak (not at peak)
        2. Market shows Follow-Through Day signal (optional)
        3. At least N days have passed since halt
        """
        # Cash-flow-adjusted, same reasoning as _check_drawdown above. Also bound by
        # current_date for the same reason (see CRITICAL FIX comment in _check_drawdown).
        cur.execute(
            """
            SELECT MAX(adjusted_equity),
                   (SELECT adjusted_equity FROM algo_portfolio_snapshots
                    WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1)
            FROM algo_portfolio_snapshots
            """,
            (current_date,),
        )
        row = cur.fetchone()
        if row is None or row[0] is None or row[1] is None:
            return {"halted": False, "reason": "No halt history"}

        peak = float(row[0])
        cur_val = float(row[1])
        if peak <= 0 or cur_val <= 0:
            return {"halted": False, "reason": "Invalid values"}

        dd = (peak - cur_val) / peak * 100.0

        # Gate on whether a drawdown halt has ever actually fired, not on whether the
        # CURRENT drawdown is still above halt_threshold_abs. The old gate made this
        # check redundant with _check_drawdown: the instant dd ticked back under the
        # halt line (e.g. 20.1% -> 19.9%), this returned "not halted" before ever
        # evaluating the tighter recovery/day/FTD protocol below - defeating the point
        # of a separate re-engagement guard.
        # Match on the actual drawdown check's own halted flag, not a substring search over
        # the whole details blob - every halt log's JSON always contains the literal key
        # "drawdown" (and "drawdown_re_engagement") in its `checks` dict regardless of which
        # check actually fired, so `details::text ILIKE '%drawdown%'` matched EVERY halt log
        # entry ever written, not just genuine drawdown-triggered ones. That meant an
        # unrelated halt (e.g. a VIX spike) reset "halt occurred Nd ago" back to 0 on every
        # occurrence, capable of extending this 5-day recovery lockout indefinitely as long
        # as anything else kept halting periodically - confirmed live 2026-07-20 (a real
        # drawdown halt fired at 11:59, recovered by 13:54, but 3 subsequent VIX-only halts
        # with drawdown.halted=false each re-matched the old query and kept resetting the
        # clock to "0d ago").
        # Excludes entries explicitly marked details->>'corrected'=true: a documented,
        # auditable correction (see algo_audit_log action_type
        # 'circuit_breaker_halt_correction' for the reasoning/evidence/commit reference)
        # applied when a halt's own recorded value is later proven to not reflect real
        # trading risk - e.g. computed by a since-fixed bug. The correction never rewrites
        # the original checks/value/reason fields, only adds a 'corrected' annotation, so
        # the halt remains fully visible in history; it's just excluded from gating
        # re-engagement, since that cooldown exists to protect against a genuine drawdown
        # recurring, not to penalize a measurement bug that has already been fixed.
        cur.execute("""
            SELECT created_at FROM algo_audit_log
            WHERE action_type = 'circuit_breaker_halt'
              AND (details->'checks'->'drawdown'->>'halted')::boolean IS TRUE
              AND NOT COALESCE((details->>'corrected')::boolean, false)
            ORDER BY created_at DESC LIMIT 1
            """)
        halt_row = cur.fetchone()
        if halt_row is None:
            return {"halted": False, "reason": "Not in drawdown halt"}

        halt_date = halt_row[0]
        days_elapsed = (
            (current_date - halt_date.date()).days
            if isinstance(halt_date, datetime)
            else (current_date - halt_date).days
        )

        recovery_val = self._get_required_config("re_engage_recovery_pct", "in re-engagement recovery check")
        min_days_val = self._get_required_config("re_engage_min_days", "in re-engagement timing check")
        require_ftd_val = self._get_required_config("require_ftd_to_re_engage", "in re-engagement FTD check")
        recovery_threshold = float(recovery_val)
        min_days_elapsed = int(min_days_val)
        require_ftd = bool(require_ftd_val)

        recovery_pct = (peak - cur_val) / peak * 100.0  # Current distance from peak
        if recovery_pct > recovery_threshold:
            return {
                "halted": True,
                "reason": f"Drawdown {dd:.1f}%, need recovery to {recovery_threshold:.1f}% to resume (currently {recovery_pct:.1f}%)",
            }

        if days_elapsed < min_days_elapsed:
            return {
                "halted": True,
                "reason": f"Halt occurred {days_elapsed}d ago, need {min_days_elapsed}d to elapse before resume",
            }

        if require_ftd:
            # A Follow-Through Day is when SPY up 1.25%+ on higher volume after a pullback/correction;
            # simplified here to "market is in Stage 2". Uses the same NULL-skipping +
            # staleness-bounded lookup as CB6 (_resolve_current_market_stage) instead of a bare
            # "latest row" query - a bare query here previously misread a not-yet-computed
            # same-day NULL placeholder (e.g. before the day's market-exposure loader ran) as a
            # confirmed "market not in Stage 2", permanently blocking re-engagement that day even
            # though yesterday's stage (still valid) may have qualified.
            stage, _trend, halt_reason = self._resolve_current_market_stage(current_date, cur)
            if halt_reason is not None:
                return {"halted": True, "reason": halt_reason}
            if stage != 2:
                return {
                    "halted": True,
                    "reason": "Recovery conditions met, but market not in Stage 2 uptrend (waiting for Follow-Through Day)",
                }

        # All conditions met - re-engagement approved
        return {
            "halted": False,
            "reason": f"Re-engagement approved: recovered to {recovery_pct:.1f}%, {days_elapsed}d elapsed, market Stage 2",
        }

    def _check_daily_loss(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        # Cash-flow-adjusted, same reasoning as _check_drawdown above (migration 1134):
        # the precomputed daily_return_pct column is derived from raw total_portfolio_value
        # deltas, so a same-day capital withdrawal reads as an equivalent trading loss and
        # can false-trip this breaker exactly like the pre-1134 drawdown bug. Compute the
        # daily return from adjusted_equity deltas instead, mirroring _check_drawdown.
        cur.execute(
            "SELECT adjusted_equity FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
            (current_date,),
        )
        today_row = cur.fetchone()
        if today_row is None or today_row[0] is None:
            return {"halted": False, "reason": "No today snapshot yet"}
        cur.execute(
            """
            SELECT adjusted_equity FROM algo_portfolio_snapshots
            WHERE snapshot_date < %s AND adjusted_equity IS NOT NULL
            ORDER BY snapshot_date DESC LIMIT 1
            """,
            (current_date,),
        )
        prev_row = cur.fetchone()
        if prev_row is None or prev_row[0] is None:
            return {"halted": False, "reason": "Insufficient history"}
        cur_val = _float(today_row[0], None, context="daily_loss current")
        prev_val = _float(prev_row[0], None, context="daily_loss previous")
        if cur_val is None or prev_val is None or prev_val <= 0:
            return {"halted": True, "reason": "Adjusted equity data invalid - fail-closed"}
        daily = (cur_val - prev_val) / prev_val * 100.0
        max_daily_val = self._get_required_config("max_daily_loss_pct", "in daily loss check")
        # _float(val, default=None, ...) raises rather than returning None on invalid/NaN/Inf
        # input, so `threshold is None` below is unreachable (see matching note in
        # _check_drawdown above) - kept only because `threshold == 0.0` is a real, reachable
        # guard against a misconfigured zero threshold (max_daily_loss_pct=0 is a valid float
        # that would otherwise halt on any loss, however small).
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

    def _check_consecutive_losses(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        # CRITICAL FIX: tiebreak was `id DESC` - id is the row's insertion order, which tracks
        # when the trade was ENTERED, not when it EXITED. Confirmed live against this DB that
        # this genuinely reorders same-exit_date trades differently from an exit_time-based
        # ordering (the convention _check_win_rate_floor already uses below for the identical
        # "most recent N closed trades" query). A day with 2+ exits could evaluate the
        # consecutive-loss streak against the wrong subset/order of trades. `id DESC` kept as a
        # final tiebreak (not the primary one) since exit_time is frequently NULL on this table
        # (several close paths didn't set it until this same fix round) and ORDER BY must stay
        # fully deterministic even when it is.
        # CRITICAL FIX: this query had no exclusion for non-representative closes, unlike
        # _check_win_rate_floor's identical "most recent N closed trades" query just below
        # (which already excludes reconciliation/force-close/delisted exit reasons as not
        # reflecting real strategy performance). Confirmed live 2026-07-27: a since-fixed
        # exit_engine bug (check_distribution() raising the stop to breakeven even when
        # price hadn't reached breakeven yet, then immediately reading the same price as
        # "below the new stop") force-closed 9 positions in one pass at prices nowhere near
        # their real, much-wider stop_loss_price - a code-bug artifact, not a real losing
        # streak - yet this check counted all 9 toward the halt with no way to exclude them.
        # DATA-QC is the short marker this session appended to those 9 trades'
        # exit_reason after verifying the root-cause fix (commits c6d399ba4, 5f1e8f8e1).
        # CRITICAL FIX: same gap for POSITION_SIZE_CONCENTRATION/SECTOR_CONCENTRATION
        # force-exits (phase6_exit_execution.py) - these are portfolio-construction/
        # risk-limit rebalancing, not a strategy call gone wrong, exactly like the
        # force-close/reconciliation/delisted exits already excluded above. Confirmed
        # live 2026-08-03: the position-size-concentration denominator bug (fixed in
        # b22e66d3b) force-exited 6 real positions within 7 minutes citing 17-42%
        # concentration (impossible for a diversified portfolio), 3 of them losses,
        # which this check counted as 3 real consecutive losses and halted trading via
        # circuit_breaker_halt at 09:20:30 - a structural/denominator bug pretending to
        # be a losing streak. Even with that bug now fixed, concentration force-exits
        # remain structurally not a strategy decision and should never count here.
        # FIX (2026-08-05): Also check algo_positions for recent closes (last 90s).
        # Phase 2 runs before Phase 9 (exit recording), so exits that closed on broker
        # but haven't been recorded in algo_trades yet don't affect the streak check.
        # If most recent position close was a win in the last 90s, it breaks the streak.
        cur.execute(
            """
            SELECT unrealized_pnl_pct as profit_loss_pct, closed_at as exit_date
            FROM algo_positions
            WHERE status = 'closed' AND closed_at > NOW() - INTERVAL '90 seconds'
            ORDER BY closed_at DESC
            LIMIT 1
            """
        )
        recent_close = cur.fetchone()
        if recent_close and recent_close[0] is not None:
            recent_pnl = _float(recent_close[0], None, context="recent_position_pnl")
            if recent_pnl >= 0:
                logger.debug(
                    f"[CIRCUIT BREAKER] Recent position close ({recent_pnl:+.2f}%) "
                    f"in last 90s breaks loss streak - skipping algo_trades check"
                )
                return {"halted": False, "reason": "0 losses (recent win resets streak)"}

        cur.execute(
            """
            SELECT profit_loss_pct, exit_date FROM algo_trades
            WHERE status = %s AND exit_date IS NOT NULL
              AND trade_id NOT ILIKE 'EXT-%%'
              AND exit_reason NOT ILIKE %s
              AND exit_reason NOT ILIKE %s
              AND exit_reason NOT ILIKE %s
              AND exit_reason NOT ILIKE %s
              AND exit_reason NOT ILIKE %s
            ORDER BY exit_date DESC, exit_time DESC NULLS LAST, id DESC
            LIMIT 10
            """,
            (TradeStatus.CLOSED.value, "%reconciliation%", "%force%close%", "%delisted%", "%DATA-QC%", "%CONCENTRATION%"),
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
        # CRITICAL FIX: Use paper_mode_max_consecutive_losses when in paper trading mode
        # Paper mode allows higher threshold (5 vs 3) for thorough testing without interruption.
        # This prevents false halts during normal market volatility testing.
        #
        # BUG FOUND 2026-08-10: this used to silently default missing config to True (paper
        # mode), which is backwards for a capital-protection check - if alpaca_paper_trading
        # were ever missing while actually live, it would silently apply the LENIENT
        # threshold (5) instead of the strict live threshold (3), under-protecting real
        # capital. Every other consumer of this same config key in the codebase (phase6/8,
        # alpaca_broker_adapter.py, execution_config.py, alpaca_sync_manager.py,
        # infrastructure/reconciliation.py) already fails fast with "NO FALLBACK TO LIVE
        # TRADING" - and this file's own _get_required_config() docstring says the same
        # thing: "missing thresholds must ALWAYS cause failure. There are no safe defaults
        # for risk control parameters." This call site was the one place that didn't follow
        # its own file's rule.
        is_paper_trading = self._get_required_config("alpaca_paper_trading", "in consecutive losses check")
        if is_paper_trading:
            config_key = "paper_mode_max_consecutive_losses"
            # Fallback to regular threshold if paper mode not configured yet
            max_consec_val = self.config.get(config_key)
            if max_consec_val is None:
                max_consec_val = self._get_required_config("max_consecutive_losses", "in consecutive losses check")
        else:
            max_consec_val = self._get_required_config("max_consecutive_losses", "in consecutive losses check")

        threshold = int(max_consec_val)
        return {
            "halted": streak >= threshold,
            "reason": (f"{streak} consecutive losses >= {threshold}" if streak >= threshold else f"{streak} losses"),
            "value": streak,
            "threshold": threshold,
        }

    def _check_win_rate_floor(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Halt if recent win rate drops below floor on closed trades only.

        CRITICAL FIX 2026-08-06: Only count CLOSED trades with confirmed exits, not open positions.
        Including open positions caused false halts when positions had small unrealized losses
        that would recover. Win rate floor should measure proven performance on closed trades,
        not in-flight unrealized P&L which is transient and misleading.

        Example: 11 closed wins, 18 closed losses = 37.9% → halt
        But 4 open positions with negative P&L were artificially counted as losses in the old
        calculation, making the sample look worse than it was. This fix uses only closed trades
        (the decided outcome) for circuit breaker gating, while exit_engine monitors open positions
        separately via stop-loss/exit conditions.

        Rolling 30-trade window (per solution-blueprint.html's CB11 spec and the same convention
        _check_consecutive_losses uses via its own LIMIT 10) - NOT all-time history. An earlier
        version of this query aggregated every closed trade ever with no ORDER BY/LIMIT, so a
        cluster of old losses could permanently anchor the win rate below floor and halt trading
        forever regardless of how well it was performing recently; loaders/compute_circuit_breakers.py's
        _compute_win_rate already implemented the correct rolling-30 window (for a metrics/display
        table only, never wired into this actual gating check) - mirrored here.
        """
        # CRITICAL FIX: Use only closed trades for win rate. Open positions are managed separately
        # by exit_engine's stop-loss/target checks. Including unrealized P&L here caused false
        # halts due to temporary unrealized losses that would recover or be managed by exit logic.
        cur.execute(
            """
            SELECT COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
                   COUNT(*) FILTER (WHERE pnl_pct < 0) as losses,
                   COUNT(*) FILTER (WHERE pnl_pct = 0) as breakeven,
                   COUNT(*) as total
            FROM (
                -- Most recent 30 closed trades with confirmed exits (rolling window, not all-time)
                -- Do NOT include open positions - they're transient and managed separately by exit_engine
                SELECT profit_loss_pct as pnl_pct
                FROM (
                    SELECT profit_loss_pct, id
                    FROM algo_trades
                    WHERE status = %s AND exit_date IS NOT NULL
                      AND exit_r_multiple IS NOT NULL
                      AND trade_id NOT ILIKE 'EXT-%%'
                      AND exit_reason NOT ILIKE %s
                      AND exit_reason NOT ILIKE %s
                      AND exit_reason NOT ILIKE %s
                      AND exit_reason NOT ILIKE %s
                      AND exit_reason NOT ILIKE %s
                    -- CRITICAL FIX: exit_time is frequently NULL on this table (several close
                    -- paths didn't set it until this same fix round - see
                    -- _check_consecutive_losses's comment above), so NULLS LAST alone left ties
                    -- among NULL-exit_time rows in a non-deterministic order (no further ORDER BY
                    -- key) - this "most recent 30" window could silently vary between runs on the
                    -- same underlying data. id DESC is a final deterministic tiebreak.
                    ORDER BY exit_date DESC, exit_time DESC NULLS LAST, id DESC
                    LIMIT 30
                ) recent_closed
            ) all_trades
            """,
            (TradeStatus.CLOSED.value, "%reconciliation%", "%force%close%", "%delisted%", "%DATA-QC%", "%CONCENTRATION%"),
        )
        row = cur.fetchone()
        if row is None:
            return {"halted": False, "reason": "No trade data available - insufficient trades (< 10)"}

        total = row[3]
        if total is None:
            return {"halted": False, "reason": "Insufficient closed trades (< 10)"}
        total = int(total)

        # CRITICAL FIX: Do NOT default wins/losses to 0 if missing.
        # Missing data indicates query failure or data integrity issue.
        # Fail-fast to prevent incorrect win rate calculations.
        if row[0] is None or row[1] is None:
            raise RuntimeError(
                f"[CIRCUIT_BREAKER CRITICAL] Win/loss counts missing from query result. "
                f"Cannot calculate win rate without actual trade outcomes. "
                f"Row[0]={row[0]}, Row[1]={row[1]}. "
                f"Data integrity issue or insufficient closed trades. Check database state."
            )
        wins = int(row[0])
        losses = int(row[1])

        # Win rate based on wins vs (wins + losses), excluding break-even trades
        # This avoids dilution where many break-even trades inflate the denominator
        decisive_trades = wins + losses

        # CRITICAL FIX: Check if this is a NEW account (no closed trades yet).
        # Applying win_rate_floor to open positions before ANY closed trades were
        # executed halts trading indefinitely if those positions are underwater.
        # Grace period: don't apply win_rate_floor until at least 10 STRATEGIC CLOSED trades exist.
        # Exclude reconciliation and force-close exits as these are not strategic outcomes.
        cur.execute(
            """
            SELECT COUNT(*) FROM algo_trades
            WHERE status = %s AND exit_date IS NOT NULL
              AND exit_r_multiple IS NOT NULL
              AND exit_reason NOT LIKE %s
              AND exit_reason NOT LIKE %s
              AND exit_reason NOT LIKE %s
              AND exit_reason NOT LIKE %s
        """,
            (TradeStatus.CLOSED.value, "%reconciliation%", "%force%close%", "%delisted%", "%CONCENTRATION%"),
        )
        closed_row = cur.fetchone()
        # CRITICAL FIX: Do NOT default closed_count to 0 if query fails.
        # Missing count indicates data integrity issue or failed query.
        if closed_row is None or closed_row[0] is None:
            raise RuntimeError(
                "[CIRCUIT_BREAKER CRITICAL] Could not fetch closed trade count. "
                "Cannot determine if account is in bootstrap period. "
                "Database query failed or no trades found. Check database state."
            )
        closed_count = int(closed_row[0])

        if closed_count < 10:
            return {
                "halted": False,
                "reason": f"New account bootstrap period - insufficient closed trades ({closed_count} < 10 required)",
                "trades_sampled": total,
            }

        # The sample-size guard must gate on decisive_trades (the actual win_rate
        # denominator below), not on total (which also counts breakeven placeholder
        # rows - e.g. Phase 9 "pending fill price confirmation" reconciliation exits
        # recorded at exactly 0.00% before their real fill price is known). Gating on
        # total let it through with total=26 but decisive_trades=8 in a live run -
        # a below-threshold sample size computing a real halt off effectively 8 trades.
        if decisive_trades < 10:
            return {
                "halted": False,
                "reason": f"Insufficient decisive trades in window ({decisive_trades} < 10)",
                "trades_sampled": total,
            }
        win_rate = wins / decisive_trades * 100.0
        win_rate_val = self._get_required_config("min_win_rate_pct", "in win rate check")
        threshold = float(win_rate_val)
        if (
            not isinstance(threshold, float)
            or (threshold != threshold)
            or threshold == float("inf")
            or threshold == float("-inf")
        ):  # NaN/Inf check
            logger.critical("CRITICAL: min_win_rate_pct is invalid (NaN/Inf) - circuit breaker cannot function")
            return {"halted": True, "reason": "CRITICAL: min_win_rate_pct invalid (NaN/Inf)"}
        return {
            "halted": win_rate < threshold,
            "reason": (
                f"Win rate {win_rate:.1f}% < {threshold:.0f}%" if win_rate < threshold else f"Win rate {win_rate:.1f}%"
            ),
            "value": round(win_rate, 1),
            "threshold": threshold,
            "trades_sampled": total,
        }

    def _check_total_risk(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Sum of (entry - stop) * qty across open positions vs portfolio value."""
        cur.execute(
            "SELECT COUNT(*) FROM algo_positions WHERE status = %s AND current_stop_price IS NULL",
            (PositionStatus.OPEN.value,),
        )
        result = cur.fetchone()
        if not result:
            raise RuntimeError("Circuit breaker total_risk check: algo_positions query returned no rows")
        missing_stops_count = result[0]
        if missing_stops_count > 0:
            logger.critical(
                f"[TOTAL_RISK_CHECK] {missing_stops_count} open positions have NULL current_stop_price. "
                "Cannot calculate risk with missing current stops. Halting to prevent blind risk-taking."
            )
            return {
                "halted": True,
                "reason": f"{missing_stops_count} positions missing current stops - fail-closed halt",
            }

        cur.execute(
            """
            SELECT SUM(GREATEST(0, (t.entry_price - p.current_stop_price) * p.quantity)),
                   COUNT(*) as position_count
            FROM algo_positions p
            JOIN algo_trades t ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
            WHERE p.status = %s
            """,
            (PositionStatus.OPEN.value,),
        )
        result = cur.fetchone()
        if result is None:
            logger.error(
                "Position count query failed (no result). Cannot determine position count. "
                "Position monitoring unsafe - halting to prevent blind trading."
            )
            raise RuntimeError(
                "Cannot determine position count: query failed. Position monitoring unsafe. "
                "Zero positions must be explicitly confirmed, not defaulted."
            )
        total_open_risk_raw = result[0]
        position_count = result[1]

        # CRITICAL: the SUM/COUNT above is an INNER JOIN against algo_trades via
        # trade_ids_arr - any open position whose trade_ids_arr doesn't resolve to a real
        # algo_trades row (empty array, stale/orphaned ids) silently drops out of BOTH the
        # SUM and this COUNT, understating total open risk with no error raised. Verify
        # against a direct count of open positions and fail-closed on any mismatch, since a
        # position risk calculation silently ignores is exactly the "blind risk-taking" this
        # check exists to prevent.
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = %s", (PositionStatus.OPEN.value,))
        actual_open_row = cur.fetchone()
        actual_open_count = actual_open_row[0] if actual_open_row else None
        if actual_open_count is None:
            raise RuntimeError("Cannot verify open position count - query failed. Position monitoring unsafe.")
        if actual_open_count != position_count:
            logger.critical(
                f"[TOTAL_RISK_CHECK] {actual_open_count} open positions exist but risk calculation only "
                f"matched {position_count} via trade_ids_arr join - {actual_open_count - position_count} "
                "position(s) have no resolvable algo_trades row and were silently excluded from total risk. "
                "Halting to prevent blind risk-taking."
            )
            return {
                "halted": True,
                "reason": (
                    f"{actual_open_count - position_count} open position(s) missing from risk calculation "
                    "(orphaned trade_ids_arr) - fail-closed halt"
                ),
            }

        # If there are open positions but SUM returns NULL, that's data corruption
        if position_count > 0 and total_open_risk_raw is None:
            logger.critical(
                f"[TOTAL_RISK_CHECK] {position_count} open positions exist but risk calculation returned NULL. "
                "Missing or corrupted entry_price or stop_price data detected. Halting to prevent blind trading."
            )
            return {
                "halted": True,
                "reason": f"Risk calculation failed on {position_count} positions - data corruption",
            }

        # If no positions, risk is legitimately 0; if positions exist and calculation succeeded, use result
        total_open_risk = _float(total_open_risk_raw, 0.0, context="total_open_risk")
        if total_open_risk is None:
            logger.critical("Cannot calculate total open risk - risk calculation failed")
            return {"halted": True, "reason": "Risk calculation failed - fail-closed"}

        # CRITICAL FIX: bound by current_date - see _check_drawdown for why an unbounded
        # "latest snapshot" query is unsafe (stray future-dated rows outrank the real one).
        cur.execute(
            "SELECT total_portfolio_value FROM algo_portfolio_snapshots "
            "WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1",
            (current_date,),
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            # First run (no portfolio snapshots yet) - skip risk check but log
            logger.info("[TOTAL_RISK_CHECK] Skipping (no portfolio snapshot yet; expected on first run)")
            return {"halted": False, "reason": "No portfolio snapshot (first run?)"}

        portfolio = _float(row[0], None, context="portfolio_value")
        # CRITICAL: Portfolio value missing/invalid -> risk calculation impossible.
        # Fail-closed: cannot assess total risk without portfolio value.
        if portfolio is None or portfolio <= 0:
            logger.critical(
                f"[TOTAL_RISK_CHECK] Portfolio value invalid ({portfolio}) - cannot calculate risk. "
                "Halting trading to prevent blind risk-taking."
            )
            return {
                "halted": True,
                "reason": f"Portfolio value invalid ({portfolio}) - risk calculation impossible. Fail-closed halt.",
            }

        # CRITICAL FIX: Ensure both operands are float before arithmetic. Database SUM may return
        # psycopg2 Decimal type; explicitly convert to avoid "Decimal * float" TypeError.
        # NOTE: total_open_risk and portfolio are guaranteed non-None at this point:
        # - total_open_risk: checked at line 700, returns if None
        # - portfolio: checked at line 714, returns if None or <= 0
        # No fallback defaults allowed (fail-fast accuracy principle)
        if total_open_risk is None:
            raise RuntimeError(
                "[CIRCUIT_BREAKER CRITICAL] total_open_risk is None after earlier validation check. "
                "This indicates a logic error in _check_total_risk. Cannot proceed with risk calculation."
            )
        if portfolio is None:
            raise RuntimeError(
                "[CIRCUIT_BREAKER CRITICAL] portfolio is None after earlier validation check. "
                "This indicates a logic error in _check_total_risk. Cannot proceed with risk calculation."
            )
        total_open_risk_f = float(total_open_risk)
        portfolio_f = float(portfolio)
        risk_pct = total_open_risk_f / portfolio_f * 100.0
        max_risk_val = self._get_required_config("max_total_risk_pct", "in total risk check")
        threshold = _float(
            max_risk_val,
            None,
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

    def _check_vix_spike(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        from algo.infrastructure import MarketCalendar

        # On non-trading days (weekends/holidays), VIX data from last trading day is valid
        # (market regime unchanged while market is closed)
        is_trading_day = MarketCalendar.is_trading_day(current_date)

        cur.execute(
            "SELECT vix_level, date, data_unavailable, reason FROM market_health_daily WHERE date <= %s AND vix_level IS NOT NULL ORDER BY date DESC LIMIT 1",
            (current_date,),
        )
        row = cur.fetchone()
        # First check if row/data exists; if not, return None for later detection
        if row is None or row[0] is None:
            vix = None
            data_date = None
        else:
            vix = row[0]
            data_date = row[1]
            data_unavailable_flag = row[2]
            reason_msg = row[3]

            # CRITICAL FIX: market_health_daily.date can come back as datetime (not date) -
            # _resolve_current_market_stage needed the identical normalization for the same
            # column/table. Without it, data_date >= min_acceptable_date below (both `date`
            # objects) raises TypeError comparing datetime to date - caught by check_all's
            # generic exception handler and fails closed (halts), but as a confusing crash
            # rather than a clean stale-data message, and only when the driver happens to
            # return datetime for this particular row.
            if isinstance(data_date, datetime):
                data_date = data_date.date()

            # GOVERNANCE COMPLIANCE: Check data_unavailable flag before using VIX data
            if data_unavailable_flag:
                return {
                    "halted": True,
                    "reason": f"VIX data marked unavailable: {reason_msg or 'no reason provided'}. Cannot assess market volatility without valid VIX data. Fail-closed halt.",
                }

            vix = _float(vix, None, context="vix_level check")
            # CRITICAL: VIX is a volatility index and is physically never <= 0 (historical
            # floor is ~9, set by index construction itself) - a non-positive value can only
            # come from upstream data corruption (bad parse, sign error, wrong field mapped).
            # Silently treating it as "not halted" (it easily clears the >threshold check)
            # would be a fail-open on data corruption, the exact failure mode this circuit
            # breaker exists to prevent. Stress-tested 2026-07-28: confirmed real historical
            # data has never had vix_level <= 0 (min ever recorded: 15.03), so this only fires
            # on genuine corruption, never a real market condition.
            if vix <= 0:
                logger.critical(f"VIX data corrupted: {vix} is not a physically possible VIX value - halting trading")
                corrupted_vix_max_val = self._get_required_config("vix_max_threshold", "in VIX circuit breaker check")
                return {
                    "halted": True,
                    "reason": f"VIX data corrupted: value {vix} is not physically possible (VIX must be positive). Fail-closed halt.",
                    "value": vix,
                    "threshold": _float(corrupted_vix_max_val, None),
                }
            # CRITICAL FIX: Use trading-day logic, not calendar days
            # On trading days: accept data from today OR the most recent trading day (pre-market runs get yesterday's EOD)
            # On non-trading days: data from most recent trading day is valid (market regime unchanged while closed)
            # DO NOT compare calendar days (Friday vs Monday = 3-5 days apart)

            is_acceptable_age = False
            min_acceptable_date = None

            if is_trading_day:
                # Today is a trading day (Mon-Fri)
                # Find the most recent trading day (to handle cases where today is trading day)
                most_recent_trading_day = current_date
                for _ in range(10):
                    if MarketCalendar.is_trading_day(most_recent_trading_day):
                        break
                    most_recent_trading_day -= timedelta(days=1)

                # Also find the previous trading day (pre-market runs use yesterday's EOD)
                prev_trading_day = current_date - timedelta(days=1)
                for _ in range(10):
                    if MarketCalendar.is_trading_day(prev_trading_day):
                        break
                    prev_trading_day -= timedelta(days=1)

                # Accept data from current trading day OR previous trading day
                min_acceptable_date = prev_trading_day
                is_acceptable_age = data_date >= min_acceptable_date
            else:
                # Today is weekend/holiday: find most recent trading day and require that date
                most_recent_trading_day = current_date - timedelta(days=1)
                for _ in range(10):
                    if MarketCalendar.is_trading_day(most_recent_trading_day):
                        break
                    most_recent_trading_day -= timedelta(days=1)

                min_acceptable_date = most_recent_trading_day
                is_acceptable_age = data_date >= min_acceptable_date

            if not is_acceptable_age:
                calendar_age = (current_date - data_date).days
                logger.critical(
                    f"VIX data stale: latest from {data_date}, expected from {min_acceptable_date} or later. "
                    f"Calendar age: {calendar_age} days. Trading halted."
                )
                vix_max_val = self._get_required_config("vix_max_threshold", "in VIX circuit breaker check")
                return {
                    "halted": True,
                    "reason": f"VIX data stale ({data_date}): expected {min_acceptable_date} or later. Trading halted.",
                    "value": None,
                    "threshold": _float(vix_max_val, None),
                }

        # CRITICAL: VIX data unavailable - cannot safely assess volatility risk.
        # Fail-closed: cannot use fallback estimates. Even computed estimates from SPY
        # volatility mask the real issue (missing live data) and may be inaccurate during
        # extreme market dislocations when we most need reliable circuit breaker protection.
        vix_max_val = self._get_required_config("vix_max_threshold", "in VIX circuit breaker check")

        if vix is None:
            logger.critical("VIX unavailable from live data sources - halting trading")
            return {
                "halted": True,
                "reason": "VIX data unavailable - cannot assess volatility risk. Trading halted.",
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

    def _resolve_current_market_stage(
        self, current_date: _date, cur: PsycopgCursor[Any]
    ) -> tuple[int | None, str, str | None]:
        """Shared market_stage lookup with data-freshness handling, used by both the
        Stage-4 circuit breaker (CB6, _check_market_stage) and the drawdown re-engagement
        Follow-Through-Day check (_check_drawdown_re_engagement) - both need "what is the
        market stage right now", and duplicating this logic let the FTD check drift out of
        sync with CB6's NULL/staleness handling (see history for the bug that caused).

        On trading days: prefer today's market_stage once computed; the morning loader inserts
        a same-day row before market_stage is available, so we fall back to the most recent
        NON-NULL stage (bounded to 10 days) rather than fail-closed halting on that placeholder.
        On non-trading days (weekends/holidays): use most recent trading day's market_stage
        (market regime doesn't change when market is closed).
        CRITICAL: MarketCalendar must succeed to ensure holiday accuracy.

        Returns (stage, trend, halt_reason). halt_reason is None on success; when set, the
        caller must fail-closed halt with it instead of trusting stage/trend (both None/"unknown").
        """
        from algo.infrastructure import MarketCalendar

        # Determine expected data date based on trading days
        is_trading_day = MarketCalendar.is_trading_day(current_date)
        if is_trading_day:
            # Trading day: require today's market_stage (market closed at 4 PM today)
            expected_data_date = current_date
        else:
            # Weekend/holiday: use most recent trading day's market_stage
            # (market regime valid from most recent close, unchanged until next open)
            expected_data_date = current_date - timedelta(days=1)
            for _ in range(10):
                if MarketCalendar.is_trading_day(expected_data_date):
                    break
                expected_data_date -= timedelta(days=1)

        # market_health_daily gets a same-day row from the morning loader (VIX, breadth) before
        # market_stage is computed later in the day - a bare "latest row <= expected_data_date"
        # picks up that not-yet-computed NULL and fail-closed halts even though yesterday's stage
        # is still valid. compute_circuit_breakers.py's own _compute_market_stage() already skips
        # NULL rows for this exact reason (WHERE market_stage IS NOT NULL); mirror that here so a
        # same-day placeholder row doesn't halt trading before the day's stage is even available.
        cur.execute(
            """SELECT date, market_stage, market_trend, data_unavailable, reason FROM market_health_daily
               WHERE date <= %s AND market_stage IS NOT NULL ORDER BY date DESC LIMIT 1""",
            (expected_data_date,),
        )
        row = cur.fetchone()
        if row is None:
            return None, "unknown", "Market health data missing - fail-closed"

        data_date, market_stage_val, market_trend_val, data_unavailable_flag, reason_msg = (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
        )

        # GOVERNANCE COMPLIANCE: Check data_unavailable flag before using any data from this row
        if data_unavailable_flag:
            return (
                None,
                "unknown",
                f"Market health data marked unavailable: {reason_msg or 'no reason provided'}. Cannot determine market stage without valid data. Fail-closed halt.",
            )

        if isinstance(data_date, datetime):
            data_date = data_date.date()

        # Bound how far back the NULL-skipping fallback above may reach: a legitimately
        # not-yet-computed same-day value is expected (small gap), but if the most recent
        # non-NULL stage is more than 10 calendar days old, market_stage computation itself
        # is broken and trusting it further would be exactly the silent stale-data bypass
        # this check exists to prevent - fail closed instead.
        staleness_days = (expected_data_date - data_date).days
        if staleness_days > 10:
            return (
                None,
                "unknown",
                (
                    f"Market stage last computed {data_date} ({staleness_days}d before expected "
                    f"{expected_data_date}) - too stale to trust. Fail-closed halt."
                ),
            )

        stage = int(market_stage_val)
        trend = market_trend_val if market_trend_val is not None else "unknown"
        return stage, trend, None

    def _check_market_stage(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """H7 FIX: Market stage validation with data freshness check (CB6)."""
        stage, trend, halt_reason = self._resolve_current_market_stage(current_date, cur)
        if halt_reason is not None:
            return {"halted": True, "reason": halt_reason}
        # Stage 4 = halt new entries (full downtrend). Stage 3 = caution but allow.
        halted = stage == 4
        return {
            "halted": halted,
            "reason": (f"Stage 4 downtrend (trend={trend})" if halted else f"Stage {stage} ({trend})"),
            "value": stage,
        }

    def _check_weekly_loss(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """7-day return on portfolio (cash-flow-adjusted, see _check_daily_loss/_check_drawdown - migration 1134)."""
        week_ago = current_date - timedelta(days=7)
        cur.execute(
            """
            SELECT
                (SELECT adjusted_equity FROM algo_portfolio_snapshots WHERE snapshot_date <= %s AND adjusted_equity IS NOT NULL ORDER BY snapshot_date DESC LIMIT 1),
                (SELECT adjusted_equity FROM algo_portfolio_snapshots WHERE snapshot_date <= %s AND adjusted_equity IS NOT NULL ORDER BY snapshot_date DESC LIMIT 1)
            """,
            (current_date, week_ago),
        )
        row = cur.fetchone()
        if row is None or len(row) < 2 or row[0] is None or row[1] is None:
            return {"halted": False, "reason": "Insufficient history"}
        cur_val, week_ago_val = float(row[0]), float(row[1])
        if week_ago_val <= 0:
            logger.critical(
                f"CRITICAL: Week-ago portfolio value invalid ({week_ago_val}) - cannot calculate weekly return"
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
                f"CRITICAL: max_weekly_loss_pct configuration invalid - cannot enforce weekly loss limit: {e}"
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

    def _check_data_freshness(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Block if our market data is too stale.

        Compares against the previous trading day (not a fixed calendar threshold)
        so 3-day holiday weekends don't cause false halts.
        Allows up to 2 trading days of staleness to handle RDS Proxy replication lag.

        NOTE: Uses trading-day logic (more sophisticated) vs centralized config's calendar-day logic.
        Coordinated via get_freshness_rule("price_daily") for consistency with other components.
        CRITICAL: MarketCalendar must succeed; cannot fall back to weekday logic (misses holidays).
        """
        cur.execute(
            "SELECT date, data_unavailable, data_unavailable_reason FROM price_daily WHERE symbol = 'SPY' ORDER BY date DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None or len(row) != 3 or row[0] is None:
            return {
                "halted": True,
                "reason": f"SPY data query malformed (expected 3 columns, got {len(row) if row else 0})",
            }

        latest = row[0]
        data_unavailable_flag_raw = row[1]
        if data_unavailable_flag_raw is None:
            logger.critical(
                "[CIRCUIT_BREAKER] SPY data_unavailable flag missing from database query. "
                "Fail-closed: cannot determine if SPY data is safe for trading."
            )
            return {
                "halted": True,
                "reason": "SPY data_unavailable flag is NULL - cannot determine data integrity. Fail-closed halt.",
            }
        data_unavailable_flag = bool(data_unavailable_flag_raw)
        reason_msg = row[2] if row[2] is not None else None

        # GOVERNANCE COMPLIANCE: Check data_unavailable flag before using price data
        if data_unavailable_flag:
            return {
                "halted": True,
                "reason": f"SPY price data marked unavailable: {reason_msg or 'no reason provided'}. Cannot assess data freshness without valid prices. Fail-closed halt.",
            }
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
                "Cannot fall back to weekday logic - holidays would be misclassified. "
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

    def _check_intraday_market_health(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Prior-day market drop check: did SPY fall >2% yesterday?

        The orchestrator runs pre-market (9:30 AM ET). price_daily contains yesterday's
        EOD prices, so the two most recent rows are yesterday vs the day before. This
        checks the prior day's return, not a live intraday reading. Blocking on a >2%
        decline yesterday is intentional: entering new swing positions the morning after
        a significant sell-off is poor risk management (Minervini: wait for market to
        stabilize before adding exposure).
        CRITICAL: Missing or invalid SPY prices must halt trading (fail-closed).
        """
        try:
            cur.execute(
                """
                SELECT close, data_unavailable, data_unavailable_reason FROM price_daily
                WHERE symbol = 'SPY'
                  AND date <= %s
                ORDER BY date DESC LIMIT 2
                """,
                (current_date,),
            )
            rows = cur.fetchall()
            if len(rows) < 2:
                logger.critical(
                    f"CIRCUIT BREAKER: Insufficient SPY price history (got {len(rows)}, need 2). "
                    "Cannot determine prior-day market movement. Halting to prevent trading in unknown market conditions."
                )
                return {"halted": True, "reason": "Insufficient SPY price history - cannot assess market stability"}

            # GOVERNANCE COMPLIANCE: Check data_unavailable flags before using prices
            for idx, row in enumerate(rows):
                data_unavailable_flag = row[1] if len(row) > 1 else False
                reason_msg = row[2] if len(row) > 2 else None
                if data_unavailable_flag:
                    return {
                        "halted": True,
                        "reason": f"SPY price data marked unavailable (row {idx}): {reason_msg or 'no reason provided'}. Cannot assess market movement with invalid prices. Fail-closed halt.",
                    }

            latest = float(rows[0][0]) if rows[0][0] is not None else None
            prior = float(rows[1][0]) if rows[1][0] is not None else None

            if latest is None or prior is None or prior <= 0:
                logger.critical(
                    f"CIRCUIT BREAKER: Invalid SPY price data (latest={latest}, prior={prior}). "
                    "Cannot calculate prior-day market change. Halting to prevent trading with missing market data."
                )
                return {
                    "halted": True,
                    "reason": "Invalid SPY price data - cannot assess market stability. Fail-closed halt.",
                }

            prior_day_change = (latest - prior) / prior * 100.0

            # Halt if SPY dropped >2% yesterday - significant sell-off, wait for stability
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
            logger.critical(f"CIRCUIT BREAKER: Prior-day market health check failed: {e}")
            return {
                "halted": True,
                "reason": f"Market health check unavailable (data error): {type(e).__name__}. Cannot proceed without market data.",
            }

    def _check_sector_concentration(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Log warning if any sector exceeds max position cap - advisory only, no halt.

        Sector concentration is a soft limit; the circuit breaker warns but does not block.
        """
        try:
            max_sector_val = self._get_required_config("max_positions_per_sector", "in sector concentration check")
            max_sector_positions = int(max_sector_val)

            cur.execute("""
                -- CRITICAL FIX: Return NULL for missing sector (don't hide with 'Unknown')
                SELECT ap.symbol, cp.sector
                FROM algo_positions ap
                LEFT JOIN company_profile cp ON cp.symbol = ap.symbol
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
                    f"Sector at/near cap: {sector_details} (max {max_sector_positions}) - Phase 6 will block same-sector entries"
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

    def _check_sector_drawdown(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Halt if any sector's cost-basis-weighted unrealized P&L drops to/below
        sector_drawdown_halt_pct.

        CRITICAL: sector_drawdown_halt_pct has been a seeded, validated, admin-editable
        config value since migration 005 - documented in
        algo/infrastructure/config/circuit_breaker_config.py's own module docstring as one
        of this codebase's 8 core circuit-breaker categories, alongside daily_loss,
        weekly_loss, consecutive_losses, win_rate, total_risk, profit_cap, and
        data_staleness (all of which DO have real _check_* methods here) - but unlike
        those 7 siblings, nothing ever read this value to actually halt trading. It looked
        like active protection and wasn't. This check closes that gap.

        Distinct from _check_sector_concentration (position-COUNT cap, advisory only,
        enforced per-trade in Phase 6): this is a P&L-based portfolio-wide halt, same
        severity tier as _check_drawdown/_check_daily_loss/_check_weekly_loss.

        Weighted by cost basis (SUM(unrealized_pnl) / SUM(entry_price * quantity) per
        sector), not a simple average of each position's unrealized_pnl_pct - an
        unweighted average would let a $500 position and a $50,000 position in the same
        sector count equally, masking the actual dollar-weighted sector exposure.

        sector_drawdown_halt_pct is stored negative (e.g. -12.0 = halt at 12% down),
        same convention as halt_drawdown_pct/max_daily_loss_pct/max_weekly_loss_pct -
        compared directly with <=, no abs() needed (see _check_daily_loss for the same
        pattern).
        """
        cur.execute("""
            -- Same NULL-sector fail-closed handling as _check_sector_concentration.
            SELECT cp.sector, ap.unrealized_pnl, ap.entry_price, ap.quantity
            FROM algo_positions ap
            LEFT JOIN company_profile cp ON cp.symbol = ap.symbol
            WHERE ap.status = 'open'
            """)
        rows = cur.fetchall()
        if not rows:
            return {"halted": False, "reason": "No open positions"}

        sector_pnl: dict[str, float] = {}
        sector_basis: dict[str, float] = {}
        skipped_positions = 0
        for row in rows:
            if not row or len(row) < 4:
                logger.warning(f"Sector drawdown check: skipping malformed row {row}")
                skipped_positions += 1
                continue
            sector, unrealized_pnl, entry_price, quantity = row[0], row[1], row[2], row[3]
            # Skip positions with missing sector (from LEFT JOIN) - they'll be synced in next run
            if not sector:
                skipped_positions += 1
                continue
            # Skip positions with missing P&L data - they'll be resync'd in Phase 3
            # Don't halt orchestrator for incomplete position data
            if unrealized_pnl is None or entry_price is None or quantity is None:
                logger.warning(
                    f"Sector drawdown check: skipping position with missing P&L/cost-basis data (sector={sector}, "
                    f"pnl={unrealized_pnl}, price={entry_price}, qty={quantity})"
                )
                skipped_positions += 1
                continue
            try:
                cost_basis = float(entry_price) * float(quantity)
                if cost_basis <= 0:
                    logger.warning(f"Sector drawdown check: skipping position with invalid cost basis (sector={sector}, basis={cost_basis})")
                    skipped_positions += 1
                    continue
            except (ValueError, TypeError) as e:
                logger.warning(f"Sector drawdown check: skipping position - cost basis conversion error: {e}")
                skipped_positions += 1
                continue
            sector_pnl[sector] = sector_pnl.get(sector, 0.0) + float(unrealized_pnl)
            sector_basis[sector] = sector_basis.get(sector, 0.0) + cost_basis

        # If we skipped all positions, insufficient data to calculate sector drawdown
        if not sector_pnl:
            logger.info(f"Sector drawdown check: all {skipped_positions} positions skipped due to missing data - insufficient data for sector drawdown calculation")
            return {"halted": False, "reason": "Insufficient data for sector drawdown check (positions missing P&L data)"}

        sector_returns = {s: sector_pnl[s] / sector_basis[s] * 100 for s in sector_pnl}
        worst_sector = min(sector_returns, key=lambda s: sector_returns[s])
        worst_pct = sector_returns[worst_sector]

        halt_val = self._get_required_config("sector_drawdown_halt_pct", "in sector drawdown check")
        threshold = _float(halt_val, None, context="sector_drawdown_halt_pct")
        if threshold >= 0:
            logger.critical(f"CRITICAL: sector_drawdown_halt_pct must be negative, got {threshold}")
            return {
                "halted": True,
                "reason": f"CRITICAL: sector_drawdown_halt_pct misconfigured (must be negative, got {threshold})",
            }

        halted = worst_pct <= threshold
        return {
            "halted": halted,
            "reason": (
                f"{worst_sector} sector at {worst_pct:.2f}% <= {threshold:.1f}%"
                if halted
                else f"Worst sector ({worst_sector}) at {worst_pct:.2f}%"
            ),
            "value": round(worst_pct, 2),
            "threshold": threshold,
            "sector": worst_sector,
        }

    def _check_daily_profit_cap(self, current_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Warn (don't halt) if daily P&L exceeds profit target; can skip new entries.

        Cash-flow-adjusted (migration 1134): raw daily_return_pct would read a same-day
        deposit as a false "profit cap exceeded" (spuriously skipping new entries) or a
        withdrawal as masking a real profit cap breach.
        """
        cur.execute(
            "SELECT adjusted_equity FROM algo_portfolio_snapshots WHERE snapshot_date = %s",
            (current_date,),
        )
        today_row = cur.fetchone()
        if not today_row or today_row[0] is None:
            return {"halted": False, "reason": "No today snapshot yet"}
        cur.execute(
            """
            SELECT adjusted_equity FROM algo_portfolio_snapshots
            WHERE snapshot_date < %s AND adjusted_equity IS NOT NULL
            ORDER BY snapshot_date DESC LIMIT 1
            """,
            (current_date,),
        )
        prev_row = cur.fetchone()
        if not prev_row or prev_row[0] is None:
            return {"halted": False, "reason": "Insufficient history"}
        prev_val = float(prev_row[0])
        if prev_val <= 0:
            return {"halted": False, "reason": "Insufficient history"}
        daily = (float(today_row[0]) - prev_val) / prev_val * 100.0
        daily_profit_val = self._get_required_config("daily_profit_cap_pct", "in daily profit cap check")
        threshold = float(daily_profit_val)
        # This check is a SOFT warning, not a halt - it's logged but doesn't block trading
        # Orchestrator uses this to skip NEW entries only, not to exit existing positions
        return {
            "halted": False,
            "reason": f"Daily profit {daily:+.2f}% vs cap {threshold:.1f}%",
            "value": round(daily, 2),
            "threshold": threshold,
            "exceed_profit_cap": daily >= threshold,
        }

    def _log_halt(self, results: dict[str, Any], cur: PsycopgCursor[Any]) -> None:
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
