from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from utils.db import DatabaseContext
from utils.db.advisory_locks import (
    ALGO_POSITIONS_LOCK_ID,
    ALGO_TRADES_LOCK_ID,
    acquire_advisory_lock,
    release_advisory_lock,
)
from utils.infrastructure.timezone import EASTERN_TZ

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

Plus 9 more real checks in `_check_registry` that predate/postdate the CB1-CB9 numbering
above and were never folded into it (this list undercounted the file's own behavior until
2026-08-25 - see [[circuit_breaker_full_audit_20260825]] in memory):
  - DRAWDOWN RE-ENGAGEMENT   halts (re-halts) during the post-drawdown-halt recovery
                             lockout window even after `dd` itself drops back under CB1's
                             threshold - see _check_drawdown_re_engagement's docstring
  - VIX/DAILY/WEEKLY/TOTAL-RISK RE-ENGAGEMENT  same minimum-elapsed-trading-days lockout
                             as drawdown re-engagement, generalized via
                             _check_min_reengagement_days - added 2026-09-04 after an
                             audit found only drawdown had this protection, letting the
                             other four breachable-and-clearable checks flap (trip, clear,
                             trip again) the instant the metric ticked back under
                             threshold with no minimum recovery time enforced.
  - INTRADAY MARKET HEALTH   halts if SPY fell > 2% the prior trading day (wait for
                             stability before adding new exposure)
  - WIN RATE FLOOR           halts if the rolling last-30-closed-trades win rate <
                             min_win_rate_pct (after a 10-trade bootstrap grace period)
  - SECTOR CONCENTRATION     advisory only, never halts - logged for Phase 6's own
                             per-trade sector-cap enforcement
  - DAILY PROFIT CAP         advisory only, never halts - flags `exceed_profit_cap` for
                             the orchestrator to optionally skip new entries, exits unaffected

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
    "daily_loss_re_engagement": "Daily Loss Recovery Period",
    "drawdown": "Portfolio Drawdown Limit",
    "drawdown_re_engagement": "Drawdown Recovery Period",
    "consecutive_losses": "Consecutive Losses Limit",
    "total_risk": "Total Open Risk Limit",
    "total_risk_re_engagement": "Total Open Risk Recovery Period",
    "vix_spike": "Market Volatility Spike",
    "vix_spike_re_engagement": "Volatility Spike Recovery Period",
    "market_stage": "Market Stage Break",
    "weekly_loss": "Weekly Loss Limit Exceeded",
    "weekly_loss_re_engagement": "Weekly Loss Recovery Period",
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
    # BUG FOUND 2026-08-11 (via fuzzing pathological inputs): the NaN/Inf check used to run
    # inside this same try block, so its own `raise ValueError("Invalid float ... (NaN/Inf)")`
    # was immediately caught by the `except (ValueError, TypeError)` below and silently
    # rewritten into the generic "Failed to convert ... to float" message - the more specific,
    # deliberately-written diagnostic (distinguishing "couldn't parse a number at all" from
    # "parsed fine but the value itself is NaN/Infinity", two different data-quality failure
    # modes worth telling apart when debugging a real circuit-breaker halt) was unreachable as
    # the top-level message. Not a safety gap (still correctly raises/returns default either
    # way), just a diagnostics gap. Split the conversion (which can legitimately raise
    # ValueError/TypeError) from the NaN/Inf validation (which must not be caught by the same
    # handler) into separate steps.
    try:
        f = float(value)
    except (ValueError, TypeError) as e:
        if default is None:
            raise ValueError(f"Failed to convert {value!r} to float {context}") from e
        return default
    if math.isnan(f) or math.isinf(f):
        if default is None:
            raise ValueError(f"Invalid float {value!r} (NaN/Inf) {context}")
        return default
    return f


# Imported here (not at module top) as a visual cue that these mixin modules themselves
# `import algo.risk.circuit_breaker as _cb` to reach `_float`/`logger` above (same
# qualified-attribute convention as algo/monitoring/position_monitor.py's split) - the
# import machinery tolerates this regardless of ordering since it's a module import, not an
# attribute pull, but keeping it below the pieces the mixins reference documents the
# dependency direction for a future reader.
from algo.risk.circuit_breaker_alerting import CircuitBreakerAlertingMixin  # noqa: E402
from algo.risk.circuit_breaker_market_conditions import CircuitBreakerMarketConditionsMixin  # noqa: E402
from algo.risk.circuit_breaker_portfolio_risk import CircuitBreakerPortfolioRiskMixin  # noqa: E402
from algo.risk.circuit_breaker_trade_sector import CircuitBreakerTradeSectorMixin  # noqa: E402


class CircuitBreaker(
    CircuitBreakerPortfolioRiskMixin,
    CircuitBreakerMarketConditionsMixin,
    CircuitBreakerTradeSectorMixin,
    CircuitBreakerAlertingMixin,
):
    """Pre-trade kill-switch checks."""

    _check_registry = [
        "daily_loss",
        "daily_loss_re_engagement",
        "drawdown",
        "drawdown_re_engagement",
        "consecutive_losses",
        "total_risk",
        "total_risk_re_engagement",
        "vix_spike",
        "vix_spike_re_engagement",
        "market_stage",
        "weekly_loss",
        "weekly_loss_re_engagement",
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
            "daily_loss_re_engagement": self._check_daily_loss_re_engagement,
            "drawdown": self._check_drawdown,
            "drawdown_re_engagement": self._check_drawdown_re_engagement,
            "consecutive_losses": self._check_consecutive_losses,
            "total_risk": self._check_total_risk,
            "total_risk_re_engagement": self._check_total_risk_re_engagement,
            "vix_spike": self._check_vix_spike,
            "vix_spike_re_engagement": self._check_vix_spike_re_engagement,
            "market_stage": self._check_market_stage,
            "weekly_loss": self._check_weekly_loss,
            "weekly_loss_re_engagement": self._check_weekly_loss_re_engagement,
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
                # LOCK (2026-09-07 real-money-readiness audit): every writer to algo_positions/
                # algo_trades (executor.py, phase9_reconciliation.py, phase6_exit_execution.py)
                # acquires these same advisory locks before touching either table, but this
                # read path never did - a concurrent write elsewhere (only reachable if the
                # orchestrator's own run-lock has failed, since phases otherwise execute
                # strictly sequentially within one run - see executor.py's own "CONCURRENCY
                # ASSUMPTION" docstring) could be observed mid-flight, feeding a transiently
                # inconsistent view into drawdown/daily-loss/total-risk. A lock-acquisition
                # failure/timeout here is caught by this function's own outer `except
                # Exception` below and correctly converted into a fail-closed halt - the same
                # safe outcome as any other circuit-breaker check failure, not a new failure
                # mode. Explicitly released in `finally` (not left to connection teardown)
                # since DatabaseContext connections can be pooled/reused across calls.
                acquire_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                acquire_advisory_lock(cur, ALGO_TRADES_LOCK_ID, "algo_trades")
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
                finally:
                    release_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                    release_advisory_lock(cur, ALGO_TRADES_LOCK_ID, "algo_trades")
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
