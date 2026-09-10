"""Phase 8 entry-execution pre-flight guards, extracted from phase8_entry_execution.py
(2026-09-05, file-size ratchet: phase8_entry_execution.py is already over its baseline and
may not grow further - see .file-size-baseline.json). Bodies are verbatim, no logic changed.

`datetime` and `DatabaseContext` are accessed via the `phase8_entry_execution` module object
at call time (not imported by name here) because several tests patch
`algo.orchestrator.phase8_entry_execution.datetime` / `.DatabaseContext` expecting that to
affect these guards - a plain `from ... import datetime` here would bind its own reference
and silently stop seeing those patches. `algo.orchestrator.phase8_entry_execution` itself
imports this module at load time, so the reference below is resolved lazily (inside the
function bodies, not at import time) to avoid a circular-import failure.
"""

import logging
import os
from collections.abc import Callable
from datetime import date as _date
from datetime import time as dt_time
from datetime import timedelta
from typing import Any

import algo.orchestrator.phase8_entry_execution as _p8e
from algo.infrastructure.market_calendar import MarketCalendar
from algo.orchestrator.phase_result import PhaseResult
from utils.infrastructure import EASTERN_TZ as _EASTERN_TZ

logger = logging.getLogger(__name__)


def _check_market_hours_guards(
    config: Any, execution_mode: str, log_phase_result_fn: Callable[..., Any]
) -> PhaseResult | None:
    """Enforce market hours (9:30 AM - 4:00 PM ET, 9:30 AM - 1:00 PM ET on early-close days)
    plus the optional market-open-exclusion window.

    Returns a blocking PhaseResult if either guard fires, else None to let run() proceed.
    """
    # CRITICAL GUARD: Enforce market hours (9:30 AM - 4:00 PM ET, 9:30 AM - 1:00 PM ET on
    # NYSE/NASDAQ early-close days). Entries executed outside market hours will be queued as
    # pre-market/after-hours orders and may fill at unexpected prices or not fill at all.
    # Risk: duplicate orders on next run.
    # MUST use MarketCalendar.is_market_open() (early-close aware), not a raw comparison
    # against the fixed MARKET_OPEN_TIME/MARKET_CLOSE_TIME constants - those ignore early
    # closes entirely, which would let this guard wave entries through from 1-4 PM ET on a
    # day the market has already closed.
    # CRITICAL FIX: Always check market hours, even in dry-run, so testing can verify
    # the guard works correctly on early-close days and outside market hours.

    # TEST MODE: Allow override for testing outside market hours (PHASE_8_TEST_MODE=true or ALLOW_OUTSIDE_MARKET_HOURS=true)
    test_mode = os.environ.get("PHASE_8_TEST_MODE", "false").lower() == "true"
    allow_outside_hours = os.environ.get("ALLOW_OUTSIDE_MARKET_HOURS", "false").lower() == "true"

    # SAFETY HARDENING (2026-08-23): these two env vars are never set by any deployed
    # terraform/infra config (confirmed via full-repo grep) - they're a local-testing
    # mechanism only, documented in CLAUDE.md for exercising Phase 8 outside real market
    # hours. But nothing previously stopped either from ALSO taking effect in
    # execution_mode="auto" (live trading with a real broker) if either var were ever left
    # set by human error (e.g. a stale shell env, a copy-pasted .env). Force both off in
    # live mode regardless of the env var, so this debug escape hatch can never bypass the
    # market-hours guard for a real order - loud CRITICAL log if it would have mattered, so
    # a real misconfiguration is never silently swallowed.
    if execution_mode == "auto" and (test_mode or allow_outside_hours):
        logger.critical(
            "[PHASE 8 SAFETY] PHASE_8_TEST_MODE/ALLOW_OUTSIDE_MARKET_HOURS is set but "
            "execution_mode='auto' (live trading) - ignoring both. These bypasses are for "
            "paper/dry/review testing only and are never honored in live mode. If this was "
            "intentional, it cannot be: no override may bypass the market-hours guard for "
            "real order execution."
        )
        test_mode = False
        allow_outside_hours = False

    # CRITICAL FIX (Session 30): Import EASTERN_TZ at function level to ensure availability
    # Previous: UnboundLocalError "cannot access local variable 'EASTERN_TZ'" due to scope shadowing
    # This ensures we always have access to the timezone regardless of outer scope
    now_dt = _p8e.datetime.now(_EASTERN_TZ)  # type: ignore[attr-defined]
    now_et = now_dt.time()
    is_market_open = MarketCalendar.is_market_open(now_dt)

    logger.info(
        f"[PHASE 8 MARKET HOURS CHECK] Current time: {now_dt.strftime('%Y-%m-%d %H:%M:%S %Z')} ET, "
        f"is_market_open={is_market_open}, test_mode={test_mode}, allow_outside_hours={allow_outside_hours}"
    )

    if not is_market_open and not test_mode and not allow_outside_hours:
        close_time = "1:00 PM" if MarketCalendar.is_early_close(now_dt.date()) else "4:00 PM"
        msg = (
            f"[PHASE 8 MARKET HOURS GUARD] Cannot execute entries outside market hours. "
            f"Current time: {now_et.strftime('%H:%M:%S')} ET, "
            f"market hours: 9:30 AM - {close_time} ET. Skipping Phase 8."
        )
        logger.warning(msg)
        log_phase_result_fn(8, "entry_execution", "blocked", msg)
        result = PhaseResult(
            8,
            "entry_execution",
            "blocked",
            {"entered": 0},
            False,  # halted=False: guard is just blocking entries, not halting orchestration
            msg,
        )
        return result

    # CRITICAL FIX (Session 32): Market-open exclusion (9:30-10:30 AM) hard cutoff
    # Previous: Guard at line 2089 only fired if current_time_et was 09:30-10:30
    # Problem: Morning runs at 09:03 AM passed because check was FALSE (before 09:30)
    # Result: All 5 market-open false breakouts entered at 09:03-09:12, stopped out 3 hours later (62.5% loss rate)
    # FIX: Hard cutoff - skip Phase 8 entirely if current_time_et < 10:30 AM ET
    # This prevents ALL market-open entries regardless of when orchestrator runs
    market_open_exclusion_enabled = config.get("market_open_exclusion_enabled", False)
    if market_open_exclusion_enabled and not test_mode and not allow_outside_hours:
        exclusion_minutes = config.get("market_open_exclusion_minutes", 30)
        market_open_start = dt_time(9, 30)  # 9:30 AM ET market open
        market_open_end = (
            _p8e.datetime.combine(now_dt.date(), market_open_start)  # type: ignore[attr-defined]
            + timedelta(minutes=exclusion_minutes)
        ).time()
        if now_et < market_open_end:
            msg = (
                f"[PHASE 8 MARKET-OPEN EXCLUSION] Blocking entries during high-volatility market open window. "
                f"Current time: {now_et.strftime('%H:%M:%S')} ET. "
                f"Entries allowed only after {market_open_end.strftime('%H:%M')} AM ET "
                f"({exclusion_minutes}-minute window after 9:30 AM market open). "
                f"Reason: Market-open false breakouts cause 62.5% loss rate within 3 hours."
            )
            logger.warning(msg)
            log_phase_result_fn(8, "entry_execution", "blocked", msg)
            result = PhaseResult(
                8,
                "entry_execution",
                "blocked",
                {"entered": 0},
                False,  # halted=False: guard is blocking entries, not halting orchestration
                msg,
            )
            return result

    if test_mode:
        logger.warning("[PHASE 8 TEST MODE] Market hours guard BYPASSED for testing")
    elif allow_outside_hours and not is_market_open:
        logger.warning(
            f"[PHASE 8 MARKET HOURS GUARD] BYPASSED via ALLOW_OUTSIDE_MARKET_HOURS=true: current time "
            f"{now_et.strftime('%H:%M:%S')} ET is outside market hours. Proceeding anyway because "
            f"the guard was explicitly overridden."
        )
    return None


def _check_pending_orders_guard(
    execution_mode: str, run_date: _date, log_phase_result_fn: Callable[..., Any]
) -> PhaseResult | None:
    """Block entries if positions from the current run_date were created in the last 10
    minutes (orders from a prior run may still be filling).
    """
    # CRITICAL GUARD: Check for pending/recent orders that may still be filling
    # If orders from prior run are still pending, executing new entries risks duplicates
    # NOTE: Skip this guard in paper mode since there are no real pending orders in simulation
    # BUG FOUND 2026-08-11: "dry" mode is equally simulation-only (same allowlist distinction
    # already fixed in executor.py's credential-fetch handling and
    # phase2_circuit_breakers.py's leniency check) - a bare `!= "paper"` here missed it, so
    # this pending-order DB check (meaningless for a mode that never places real orders) ran
    # in dry mode too. "review" mode deliberately keeps the guard active - unlike dry, it
    # persists real (locally-pending) trade/position rows that a hasty re-run could duplicate.
    if execution_mode not in ("paper", "dry"):
        try:
            with _p8e.DatabaseContext("read") as cur:  # type: ignore[attr-defined]
                # Check for positions created in the last 10 minutes (indicates recent fills or pending orders)
                # If we just created positions very recently, the orders may still be in flight
                cur.execute(
                    """
                    SELECT COUNT(*) as recent_position_count
                    FROM algo_positions
                    WHERE entry_date = %s
                    AND created_at > NOW() - INTERVAL '10 minutes'
                    AND status = 'open'
                    """,
                    (run_date,),
                )
                result = cur.fetchone()
                recent_count = result[0] if result else 0

                if recent_count > 0:
                    msg = (
                        f"[PHASE 8 PENDING ORDERS GUARD] Blocking Phase 8: {recent_count} positions "
                        f"created in last 10 min (orders may still be pending/filling). Re-run in 5 minutes."
                    )
                    logger.warning(msg)
                    log_phase_result_fn(8, "entry_execution", "blocked", msg)
                    result = PhaseResult(
                        8,
                        "entry_execution",
                        "blocked",
                        {"entered": 0},
                        False,  # halted=False: guard worked but didn't halt orchestration
                        msg,
                    )
                    return result
        except Exception as e:
            msg = (
                f"[PHASE 8 CRITICAL] Could not verify pending orders status: {e}. "
                f"Cannot safely execute new entries without knowing if prior orders are still pending. "
                f"Risk of order duplication or conflicts. Must halt and investigate."
            )
            logger.critical(msg, exc_info=True)
            log_phase_result_fn(8, "entry_execution", "halt", msg)
            raise RuntimeError(msg) from e
    else:
        logger.info(f"[PHASE 8 PENDING ORDERS GUARD] Skipping in {execution_mode} mode (no real broker orders)")
    return None


def _check_signal_freshness_guard(log_phase_result_fn: Callable[..., Any]) -> PhaseResult | None:
    """Block entries if buy_sell_daily signals are stale relative to the price data they were
    computed from (algo/risk/stale_signal_circuit_breaker.py).
    """
    # SIGNAL FRESHNESS GUARD: algo/risk/stale_signal_circuit_breaker.py was written
    # ("ROOT CAUSE #4 fix") specifically to catch entries placed off stale signals -
    # buy_sell_daily generated from price data older than the threshold, or lagging behind
    # price_daily entirely - but was never actually called from anywhere in the orchestrator.
    # Phase 1 validates price_daily/market_health/market_exposure freshness but explicitly
    # excludes buy_sell_daily (not generated yet at that point in the run); nothing downstream
    # ever checked whether the signals Phase 8 is about to trade on are themselves fresh
    # relative to the price data they were computed from. Block (not halt orchestration)
    # entries this run if stale, matching the market-hours/pending-orders guards above.
    try:
        from algo.risk.stale_signal_circuit_breaker import StaleSignalCircuitBreaker

        signals_fresh, freshness_msg = StaleSignalCircuitBreaker.check_signal_freshness()
        if not signals_fresh:
            msg = f"[PHASE 8 SIGNAL FRESHNESS GUARD] Blocking Phase 8: {freshness_msg}"
            logger.critical(msg)
            log_phase_result_fn(8, "entry_execution", "blocked", msg)
            result = PhaseResult(
                8,
                "entry_execution",
                "blocked",
                {"entered": 0},
                False,  # halted=False: guard is just blocking entries, not halting orchestration
                msg,
            )
            return result
    except RuntimeError as e:
        msg = (
            f"[PHASE 8 CRITICAL] Could not verify signal freshness: {e}. "
            f"Cannot safely execute new entries without knowing if signals are stale. Must halt and investigate."
        )
        logger.critical(msg, exc_info=True)
        log_phase_result_fn(8, "entry_execution", "halt", msg)
        raise RuntimeError(msg) from e
    return None


def _check_price_freshness_guard(run_date: _date, log_phase_result_fn: Callable[..., Any]) -> PhaseResult | None:
    """Re-validate price_daily is fresh enough for entry execution (Phase 1 validated it at
    orchestrator start, but Phase 8 may run hours later).
    """
    # PRICE DATA FRESHNESS GUARD: Re-validate that price_daily is fresh for afternoon/evening runs
    # Phase 1 validates at 9:00 AM, but Phase 8 may run at 1-5 PM. Price loader may fail between phases.
    # Without this check: trades execute on stale morning prices (risk: wrong entry prices, no intraday updates)
    price_fresh, price_msg = _p8e._check_price_data_freshness(run_date)
    if not price_fresh:
        msg = f"[PHASE 8 PRICE FRESHNESS GUARD] Blocking Phase 8: {price_msg}"
        logger.critical(msg)
        log_phase_result_fn(8, "entry_execution", "blocked", msg)
        result = PhaseResult(
            8,
            "entry_execution",
            "blocked",
            {"entered": 0},
            False,  # halted=False: guard is just blocking entries, not halting orchestration
            msg,
        )
        return result
    return None


def _check_drawdown_daily_loss_guard(
    config: Any, run_date: _date, log_phase_result_fn: Callable[..., Any]
) -> PhaseResult | None:
    """Re-check drawdown/daily-loss right before Phase 8 submits any new risk (2026-09-07
    real-money-readiness audit fix).

    Phase 2's circuit-breaker check ran earlier this cycle, before Phase 3/4 (position
    monitor/reconciliation, which can write a fresher algo_portfolio_snapshots row) and before
    this phase's own candidate loop - a real drawdown/daily-loss breach reflected only by
    Phase 4's reconciliation write would otherwise not be caught until the NEXT cycle's Phase
    2. Re-runs just the two cheap, pure-DB-read breakers (drawdown/daily_loss - no Alpaca API
    calls, unlike VIX/market-stage/PDT) once here against whatever this cycle's freshest
    snapshot is.

    Deliberately NOT re-run per-candidate inside Phase 8's own loop: both checks key off
    algo_portfolio_snapshots.adjusted_equity, which only updates on the NEXT reconciliation
    pass (a future cycle's Phase 4, or Phase 9's end-of-day snapshot) - nothing rewrites it
    mid-Phase-8, so polling it repeatedly inside the loop would add cost with zero incremental
    signal. Fully closing the "breach occurs from live price movement DURING the Phase 8 loop
    itself" case would require a live Alpaca equity poll per candidate - a real latency/
    rate-limit cost, deliberately left as a separate decision, not guessed at here.

    Fails closed (blocks entries) on any error, matching CircuitBreaker.check_all()'s own
    established convention: if this safety re-check itself cannot be verified, do not proceed.
    """
    try:
        from algo.risk.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(config)
        with _p8e.DatabaseContext("read") as cb_cur:  # type: ignore[attr-defined]
            drawdown_state = cb._checks["drawdown"](run_date, cb_cur)
            daily_loss_state = cb._checks["daily_loss"](run_date, cb_cur)
        breached = [s for s in (drawdown_state, daily_loss_state) if s.get("halted")]
        if not breached:
            return None
        reasons = "; ".join(str(s.get("reason", "unknown")) for s in breached)
        msg = f"[PHASE 8] Fresh drawdown/daily-loss re-check breached ({reasons}) - entries blocked this cycle"
    except Exception as e:
        msg = f"[PHASE 8] Drawdown/daily-loss re-check failed - blocking entries this cycle: {e}"
    logger.critical(msg)
    log_phase_result_fn(8, "entry_execution", "blocked", msg)
    return PhaseResult(8, "entry_execution", "blocked", {"entered": 0}, False, msg)
