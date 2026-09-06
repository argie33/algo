#!/usr/bin/env python3
"""Consolidated intraday risk monitor - one 5-minute check that replaces 4 previously
uncoordinated mechanisms (real-money-readiness architecture rebuild, 2026-09-06, see
memory/intraday_monitoring_architecture_gap_20260906.md for the audit that found this):

  1. `lambda/circuit-breaker/index.py` - separately packaged Lambda, own IAM role/zip,
     3 fixed daily schedules (10am/12pm/3pm), portfolio P&L variance only.
  2. `lambda/execution-monitor/index.py` - separately packaged Lambda, every 2h,
     read-only reporting, no action.
  3. `algo/risk/intraday_risk_monitor.py::check_intraday_risk` - live beta/top-5
     concentration re-check, deliberately ALERT-ONLY by its own prior docstring
     (auto-halt was an explicitly deferred decision).
  4. `stop_loss_guardian` mode (phase9_reconciliation.py's stop-loss verify/repair step,
     re-invoked on its own tighter schedule).

This module is the single entry point (`check_unified_risk`) all 4 collapse into, run on
one 5-minute schedule during market hours via `lambda_function.py`'s
`mode: "unified_risk_monitor"` dispatch (see that file).

USER-DIRECTED DESIGN (2026-09-06): the user explicitly wants automated remediation over
relying on a human being available to act - but "best and right," not reckless, given
every automated exit is a real, irreversible trade with real slippage. The safety is
engineered into WHEN action fires, not into a human checkpoint:
  - A breach must be independently re-confirmed against FRESH live data on
    CONSECUTIVE_BREACH_RUNS_TO_HALT consecutive runs before it counts as real (a single
    bad tick, stale beta row, or transient API hiccup must never trigger a real trade).
    State persists in `algo_risk_monitor_state` (migration 1260) since each Lambda
    invocation is a fresh process.
  - Confirmed breach -> automatic HALT (HaltFlagManager.set_halt_flag, the same
    reversible, well-tested, origin-aware primitive circuit-breaker already used
    correctly). This alone protects against new entries.
  - Breach still confirmed on the runs AFTER halting (halting alone didn't fix it,
    because it's a concentration/beta problem from EXISTING positions, not new entries)
    -> automatic reduce/flatten through the exact same exit path
    scripts/flatten_all_positions.py uses (TradeExecutor.exit_trade -> ExitHandler -> the
    real order path, never the Alpaca API directly - preserves the fill-vs-cancel race
    fix, commits bc9b68268/b9c350ee2). CORRECTED 2026-09-06 (adversarial review flagged
    this claim as broader than the code): today `_resolve_offending_symbols` can only
    pinpoint one narrow case - a beta breach where a position is missing a beta value
    entirely (check_intraday_risk returns no other per-symbol beta/concentration
    contribution data at all). Every other breach shape (variance, market-health, a
    correctly-scored high-beta position simply dominating exposure, any concentration
    breach) has no per-symbol data to target and always falls back to a FULL flatten -
    which is safe, just not "targeted." Building real per-symbol attribution for those
    cases is a separate follow-up, not yet done.
  - Every automated action still sends an alert (AlertManager) describing exactly what
    was detected and done - this is an audit trail, not a checkpoint. Nothing waits for
    acknowledgment.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any

import psycopg2

from algo.orchestration.halt_flag_manager import HaltFlagManager
from algo.reporting import AlertManager
from algo.risk.intraday_risk_monitor import check_intraday_risk
from algo.trading.quote_fetcher import fetch_live_quote
from utils.data_queries import get_open_portfolio_totals
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)

# How many consecutive 5-minute runs must independently re-confirm a breach (against
# fresh live data each time) before it counts as real and triggers the halt. Chosen to
# require a genuinely sustained condition (>=5 real minutes) while still reacting fast -
# this is not a config knob because relaxing it is a real risk-tolerance decision, not an
# operational tuning parameter; changing it needs the same deliberateness as changing
# max_position_size_pct (see position_sizer.py's own resolved-decision comment).
CONSECUTIVE_BREACH_RUNS_TO_HALT = 2

# How many additional consecutive confirmed-breach runs AFTER the halt has already fired
# before escalating to an automated reduce/flatten. The halt already stops new entries -
# this gives one more full confirmation cycle (>=5 more real minutes) that the breach is
# from the EXISTING book (not something the halt itself would resolve) before touching
# live positions.
CONSECUTIVE_BREACH_RUNS_TO_ACT = CONSECUTIVE_BREACH_RUNS_TO_HALT + 1


def _load_state(cur: Any, check_key: str) -> dict[str, Any]:
    cur.execute(
        """SELECT consecutive_breach_count, last_breached, last_action
           FROM algo_risk_monitor_state WHERE check_key = %s""",
        (check_key,),
    )
    row = cur.fetchone()
    if row is None:
        return {"consecutive_breach_count": 0, "last_breached": False, "last_action": None}
    return {"consecutive_breach_count": row[0], "last_breached": row[1], "last_action": row[2]}


def _save_state(
    cur: Any, check_key: str, breached: bool, consecutive_count: int, action: str, result: dict[str, Any]
) -> None:
    cur.execute(
        """
        INSERT INTO algo_risk_monitor_state (
            check_key, consecutive_breach_count, last_breached, last_action, last_result_json,
            last_checked_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (check_key) DO UPDATE SET
            consecutive_breach_count = EXCLUDED.consecutive_breach_count,
            last_breached = EXCLUDED.last_breached,
            last_action = EXCLUDED.last_action,
            last_result_json = EXCLUDED.last_result_json,
            last_checked_at = NOW(),
            updated_at = NOW()
        """,
        (check_key, consecutive_count, breached, action, json.dumps(result, default=str)),
    )


def _update_breach_streak(cur: Any, check_key: str, breached: bool, result: dict[str, Any]) -> int:
    """Advance (or reset) this check's consecutive-breach streak and persist it.

    Returns the streak count AFTER this run - the value callers act on. A non-breach
    resets to 0 immediately (no partial credit - the breach must be sustained on truly
    consecutive runs, not merely "frequent").
    """
    state = _load_state(cur, check_key)
    new_count = (state["consecutive_breach_count"] + 1) if breached else 0
    _save_state(cur, check_key, breached, new_count, action="", result=result)
    return new_count


def _check_portfolio_variance(config: Any, max_attempts: int = 3) -> dict[str, Any]:
    """Portfolio P&L variance vs. session-open snapshot. Ported from
    lambda/circuit-breaker/index.py::get_portfolio_pnl - same fail-closed retry
    semantics (never treat "unknown" as "safe": raises after max_attempts rather than
    returning a variance that would read as within-threshold).
    """
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with DatabaseContext("read") as cur:
                portfolio_data = get_open_portfolio_totals(cur)
                total_equity = portfolio_data.get("total_equity")
                current_pnl = portfolio_data.get("current_pnl")
                if total_equity is None or current_pnl is None:
                    raise RuntimeError(
                        f"Portfolio data unavailable: total_equity={total_equity}, "
                        f"current_pnl={current_pnl} (no open positions or data missing)"
                    )
                total_equity = float(total_equity)
                current_pnl = float(current_pnl)

                cur.execute(
                    """SELECT unrealized_pnl_total FROM algo_portfolio_snapshots
                       WHERE snapshot_date = CURRENT_DATE LIMIT 1"""
                )
                session_row = cur.fetchone()
                if session_row is None:
                    raise RuntimeError("Session opening P&L snapshot not found (market may not have opened yet)")
                if session_row[0] is None:
                    raise RuntimeError("Session opening P&L value is NULL (data quality issue)")
                open_pnl = float(session_row[0])

            if total_equity <= 0:
                raise RuntimeError(f"Cannot calculate portfolio variance: total_equity invalid ({total_equity})")

            variance = (current_pnl - open_pnl) / total_equity
            return {
                "variance": variance,
                "current_pnl": current_pnl,
                "open_pnl": open_pnl,
                "total_equity": total_equity,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError, RuntimeError, ValueError, TypeError) as e:
            last_err = e
            logger.warning(f"[UNIFIED_RISK_MONITOR] variance check attempt {attempt}/{max_attempts} failed: {e}")

    raise RuntimeError(
        f"[UNIFIED_RISK_MONITOR] Unable to calculate portfolio variance after {max_attempts} retries: {last_err}. "
        "Failing fast to prevent trading on stale/unknown variance data."
    ) from last_err


def _check_live_intraday_spy_move(config: Any) -> dict[str, Any]:
    """True live intraday check: live SPY quote vs. today's prior-close baseline.

    Distinct from (and does NOT touch) circuit_breaker_market_conditions.py's
    _check_intraday_market_health, which compares yesterday's close to the day before -
    that check is correct for its own purpose (a pre-market "don't add exposure the
    morning after a selloff" gate). This is a new, separate check for movement DURING
    the current session, using a live quote rather than the EOD price_daily table.
    """
    with DatabaseContext("read") as cur:
        cur.execute(
            """SELECT close, data_unavailable, data_unavailable_reason FROM price_daily
               WHERE symbol = 'SPY' AND date < %s ORDER BY date DESC LIMIT 1""",
            (_date.today(),),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("[UNIFIED_RISK_MONITOR] No prior-day SPY close on file - cannot assess live intraday move.")
    if row[1]:
        raise RuntimeError(f"[UNIFIED_RISK_MONITOR] Prior-day SPY close marked unavailable: {row[2]}")
    prior_close = float(row[0]) if row[0] is not None else None
    if prior_close is None or math.isnan(prior_close) or math.isinf(prior_close) or prior_close <= 0:
        raise RuntimeError(f"[UNIFIED_RISK_MONITOR] Invalid prior-day SPY close: {prior_close}")

    execution_mode = str(config["execution_mode"]).lower()
    quote = fetch_live_quote("SPY", execution_mode, log_prefix="UNIFIED_RISK_MONITOR")
    if isinstance(quote, dict):
        raise RuntimeError(f"[UNIFIED_RISK_MONITOR] Live SPY quote unavailable: {quote.get('reason', quote)}")
    if math.isnan(quote) or math.isinf(quote) or quote <= 0:
        raise RuntimeError(f"[UNIFIED_RISK_MONITOR] Non-finite/invalid live SPY quote: {quote}")

    intraday_change_pct = (quote - prior_close) / prior_close * 100.0
    return {"live_price": quote, "prior_close": prior_close, "intraday_change_pct": intraday_change_pct}


def _get_halt_manager(alerts: AlertManager) -> HaltFlagManager:
    return HaltFlagManager(alerts=alerts, log_phase_result=lambda *a, **k: None)


def _resolve_offending_symbols(risk_result: dict[str, Any]) -> list[str] | None:
    """For a beta/concentration breach, identify the specific position(s) driving it, so
    an escalated action can reduce just those rather than flattening the whole book.
    Returns None when no single position can be pinpointed (variance/market-health
    breaches - the whole book moved together, not one name)."""
    symbols_missing_beta = risk_result.get("symbols_missing_beta") or []
    if risk_result.get("beta_breach") and symbols_missing_beta:
        # A position with no beta on file contributed zero to the (already-breaching)
        # weighted sum yet is real dollar exposure - treat it as a prime reduction
        # candidate rather than implicitly assuming it's fine.
        return list(symbols_missing_beta)
    return None


def _apply_risk_verdict(
    config: Any,
    alerts: AlertManager,
    check_key: str,
    breached: bool,
    reason: str,
    result: dict[str, Any],
    offending_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Advance this check's breach streak, and escalate through HALT -> reduce/flatten
    if the streak crosses the confirmation thresholds. Every transition is alerted -
    the alert is the audit trail, not a gate that blocks the action.
    """
    with DatabaseContext("write") as cur:
        # RACE CONDITION FIX (found in adversarial review, 2026-09-06): mode="unified_risk_
        # monitor" is dispatched directly in lambda_handler, bypassing orchestrator.py's own
        # run()/DB advisory lock entirely - nothing else serializes overlapping invocations
        # of this check. A slow run (this module's own retry loops on transient API/DB
        # errors can genuinely exceed the 5-minute schedule interval) can overlap a fresh
        # invocation. Without locking, _load_state's plain SELECT then _save_state's
        # INSERT...ON CONFLICT is a classic lost-update: two overlapping runs can both read
        # the same prior streak count and each independently increment from it, silently
        # under-counting a real sustained breach - delaying the automatic halt/reduce
        # exactly when API distress (the same condition causing the overlap) makes
        # protection matter most. A transaction-scoped advisory lock keyed by check_key
        # forces a second concurrent run for the SAME check to block until the first
        # commits (released automatically at transaction end), so it always sees the
        # already-updated streak rather than a stale one - independent checks (variance vs
        # beta vs concentration vs market_health) never block each other.
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (check_key,))
        streak = _update_breach_streak(cur, check_key, breached, result)

    if not breached:
        if streak == 0:
            _maybe_clear_halt(alerts, check_key, reason)
        return {"check": check_key, "breached": False, "streak": streak, "action": "none"}

    logger.info(f"[UNIFIED_RISK_MONITOR] {check_key} breach observed (streak={streak}): {reason}")

    if streak < CONSECUTIVE_BREACH_RUNS_TO_HALT:
        alerts.send_position_alert(
            "PORTFOLIO",
            "RISK_BREACH_OBSERVED",
            f"{check_key} breach observed (run {streak}/{CONSECUTIVE_BREACH_RUNS_TO_HALT} - "
            f"not yet acted on, must be re-confirmed against fresh live data first): {reason}",
            result,
        )
        return {"check": check_key, "breached": True, "streak": streak, "action": "warn"}

    manager = _get_halt_manager(alerts)
    manager.set_halt_flag(reason=f"[UNIFIED_RISK_MONITOR:{check_key}] {reason}", triggered_by="unified_risk_monitor")
    alerts.send_position_alert(
        "PORTFOLIO",
        "RISK_BREACH_HALTED",
        f"{check_key} breach CONFIRMED across {streak} consecutive live-reconfirmed runs - "
        f"new entries halted automatically: {reason}",
        result,
    )

    if streak < CONSECUTIVE_BREACH_RUNS_TO_ACT:
        return {"check": check_key, "breached": True, "streak": streak, "action": "halt"}

    action_detail = _act_reduce_or_flatten(config, alerts, check_key, reason, offending_symbols)
    if action_detail.get("failed"):
        # ESCALATION FIX (adversarial review, 2026-09-06): a position that genuinely can't
        # be closed (delisted, halted, Alpaca rejects the exit) previously retried
        # identically every run with only the same routine RISK_BREACH_AUTO_REDUCED alert
        # repeating indefinitely - no distinct signal that this specific run's automated
        # action did NOT succeed and needs a human now, as opposed to a routine confirmed
        # breach. This is a separate, more urgent alert on top of that one (not instead of
        # it) so an operator can filter/page on this specific type.
        alerts.send_position_alert(
            "PORTFOLIO",
            "RISK_BREACH_ACTION_FAILED_MANUAL_INTERVENTION_REQUIRED",
            f"{check_key}: automated reduce/flatten could NOT close {len(action_detail['failed'])} "
            f"position(s) - this will keep retrying every run but requires manual intervention "
            f"now: {action_detail['failed']}",
            action_detail,
        )
    return {
        "check": check_key,
        "breached": True,
        "streak": streak,
        "action": "reduce_or_flatten",
        "detail": action_detail,
    }


def _maybe_clear_halt(alerts: AlertManager, check_key: str, reason: str) -> None:
    manager = _get_halt_manager(alerts)
    current_trigger = manager.get_halt_triggered_by()
    cleared = manager.clear_halt_flag(
        reason=f"[UNIFIED_RISK_MONITOR:{check_key}] recovered: {reason}",
        allowed_triggers=frozenset({"unified_risk_monitor", None}),
    )
    if cleared:
        alerts.send_position_alert(
            "PORTFOLIO", "RISK_BREACH_RESOLVED", f"{check_key} back within limits - halt cleared: {reason}", {}
        )
    elif current_trigger not in (None, "unified_risk_monitor"):
        logger.info(
            f"[UNIFIED_RISK_MONITOR] {check_key} recovered, but active halt belongs to "
            f"'{current_trigger}', not this monitor - not auto-clearing on its behalf."
        )


def _act_reduce_or_flatten(
    config: Any, alerts: AlertManager, check_key: str, reason: str, offending_symbols: list[str] | None
) -> dict[str, Any]:
    """Escalated automated action: reduce the identified offending position(s), or fall
    back to a full flatten when no single position can be pinpointed. Goes through the
    exact same exit path scripts/flatten_all_positions.py uses - TradeExecutor.exit_trade
    -> ExitHandler.execute_exit -> order_manager.py - never a bespoke Alpaca call, to
    preserve the fill-vs-cancel race fix (commits bc9b68268/b9c350ee2).
    """
    from algo.trading.executor import TradeExecutor
    from utils.trading import TradeStatus

    executor = TradeExecutor(config)
    execution_mode = str(config["execution_mode"]).lower()

    with DatabaseContext("read") as cur:
        open_statuses = TradeStatus.all_open()
        placeholders = ", ".join(["%s"] * len(open_statuses))
        if offending_symbols:
            cur.execute(
                f"""SELECT trade_id, symbol FROM algo_trades
                    WHERE status IN ({placeholders}) AND symbol = ANY(%s)
                    ORDER BY trade_date ASC""",
                (*open_statuses, offending_symbols),
            )
        else:
            cur.execute(
                f"SELECT trade_id, symbol FROM algo_trades WHERE status IN ({placeholders}) ORDER BY trade_date ASC",
                open_statuses,
            )
        targets = [(row[0], row[1]) for row in cur.fetchall()]

    closed: list[str] = []
    failed: list[tuple[str, str]] = []
    for trade_id, symbol in targets:
        try:
            quote = fetch_live_quote(symbol, execution_mode, log_prefix="UNIFIED_RISK_MONITOR")
        except Exception as e:
            failed.append((symbol, f"quote fetch failed: {type(e).__name__}: {e}"))
            continue
        if isinstance(quote, dict):
            failed.append((symbol, f"quote unavailable: {quote.get('reason', quote)}"))
            continue
        result = executor.exit_trade(
            trade_id=trade_id,
            exit_price=quote,
            exit_reason=f"AUTO_RISK_REDUCE[{check_key}]: {reason}",
            exit_fraction=1.0,
        )
        if result.get("success"):
            closed.append(symbol)
        else:
            failed.append((symbol, str(result.get("message"))))

    logger.critical(
        f"[UNIFIED_RISK_MONITOR] AUTOMATED {'TARGETED REDUCTION' if offending_symbols else 'FLATTEN'} "
        f"for {check_key} breach: closed={closed}, failed={failed}"
    )
    alerts.send_position_alert(
        "PORTFOLIO",
        "RISK_BREACH_AUTO_REDUCED",
        f"{check_key} breach persisted after halt - automatically "
        f"{'reduced offending position(s)' if offending_symbols else 'flattened the book'}: "
        f"closed={closed}, failed={failed}. Reason: {reason}",
        {"closed": closed, "failed": failed},
    )
    return {"closed": closed, "failed": failed}


def check_unified_risk(config: Any, alerts: AlertManager | None = None) -> dict[str, Any]:
    """Single entry point: runs all 4 consolidated checks and applies the escalation
    ladder to each independently (a variance breach and a beta breach have independent
    streaks/actions - one doesn't reset or mask the other).
    """
    alerts = alerts or AlertManager()
    results: dict[str, Any] = {"timestamp": datetime.now(timezone.utc).isoformat(), "checks": {}}

    # 1. Portfolio variance
    try:
        variance_result = _check_portfolio_variance(config)
        threshold = float(config["portfolio_variance_threshold"])
        variance = variance_result["variance"]
        breached = variance > threshold
        verdict = _apply_risk_verdict(
            config,
            alerts,
            "variance",
            breached,
            f"portfolio variance {variance:.1%} exceeds {threshold:.1%}"
            if breached
            else f"portfolio variance {variance:.1%} within {threshold:.1%}",
            variance_result,
        )
        results["checks"]["variance"] = {**variance_result, "verdict": verdict}
    except Exception as e:
        logger.critical(f"[UNIFIED_RISK_MONITOR] variance check failed: {e}", exc_info=True)
        verdict = _apply_risk_verdict(
            config, alerts, "variance", True, f"variance check infrastructure failure: {e}", {"error": str(e)}
        )
        results["checks"]["variance"] = {"error": str(e), "verdict": verdict}

    # 2. Live beta/top-5 concentration (reuses intraday_risk_monitor.py as-is)
    try:
        risk_result = check_intraday_risk(config, alerts=_NoOpAlerts())  # own alerting replaced by the ladder below
        offending = _resolve_offending_symbols(risk_result)
        for check_key, breach_field, label in (
            ("beta", "beta_breach", "portfolio beta"),
            ("concentration", "concentration_breach", "top-5 concentration"),
        ):
            breached = bool(risk_result.get(breach_field))
            reason = f"{label} breach: {risk_result}" if breached else f"{label} within limits"
            verdict = _apply_risk_verdict(
                config, alerts, check_key, breached, reason, risk_result, offending_symbols=offending
            )
            results["checks"][check_key] = {**risk_result, "verdict": verdict}
    except Exception as e:
        logger.critical(f"[UNIFIED_RISK_MONITOR] beta/concentration check failed: {e}", exc_info=True)
        for check_key in ("beta", "concentration"):
            verdict = _apply_risk_verdict(
                config,
                alerts,
                check_key,
                True,
                f"beta/concentration check infrastructure failure: {e}",
                {"error": str(e)},
            )
            results["checks"][check_key] = {"error": str(e), "verdict": verdict}

    # 3. Stop-loss protection verify/repair (self-healing, not part of the halt/act ladder -
    #    it already repairs through the real order path on its own, see that function's docstring)
    try:
        from algo.orchestrator.phase9_reconciliation import _verify_open_position_stop_loss_protection_step

        def _log_result(*args: Any, **kwargs: Any) -> None:
            logger.info(f"[UNIFIED_RISK_MONITOR:stop_loss] {args} {kwargs}")

        _verify_open_position_stop_loss_protection_step(_log_result, config, sync_positions_first=True)
        results["checks"]["stop_loss_protection"] = {"status": "checked"}
    except Exception as e:
        logger.critical(f"[UNIFIED_RISK_MONITOR] stop-loss protection check failed: {e}", exc_info=True)
        results["checks"]["stop_loss_protection"] = {"error": str(e)}

    # 4. True live intraday SPY move (new)
    try:
        market_result = _check_live_intraday_spy_move(config)
        threshold_pct = float(config.get("intraday_spy_drop_halt_pct", -2.0))
        change = market_result["intraday_change_pct"]
        breached = change <= threshold_pct
        verdict = _apply_risk_verdict(
            config,
            alerts,
            "market_health",
            breached,
            f"live SPY intraday move {change:.2f}% breaches {threshold_pct:.2f}%"
            if breached
            else f"live SPY intraday move {change:.2f}% within {threshold_pct:.2f}%",
            market_result,
        )
        results["checks"]["market_health"] = {**market_result, "verdict": verdict}
    except Exception as e:
        logger.critical(f"[UNIFIED_RISK_MONITOR] live market-health check failed: {e}", exc_info=True)
        verdict = _apply_risk_verdict(
            config, alerts, "market_health", True, f"market-health check infrastructure failure: {e}", {"error": str(e)}
        )
        results["checks"]["market_health"] = {"error": str(e), "verdict": verdict}

    return results


class _NoOpAlerts(AlertManager):
    """check_intraday_risk's own alerting is superseded by _apply_risk_verdict's ladder
    above (which needs the debounce state before deciding whether/how loudly to alert) -
    this suppresses its direct alert so a single breach doesn't send two different,
    inconsistent-looking alerts for the same condition. Subclasses AlertManager (rather
    than duck-typing) purely so it satisfies check_intraday_risk's `AlertManager | None`
    type - real alerting for these checks always still happens via _apply_risk_verdict's
    own `alerts` instance, so nothing is lost, only de-duplicated."""

    def send_position_alert(self, *args: Any, **kwargs: Any) -> None:
        return None
