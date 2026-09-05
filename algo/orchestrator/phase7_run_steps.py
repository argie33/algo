"""PHASE 7 helper: named steps extracted from `run()` in
algo/orchestrator/phase7_signal_generation.py.

Pure extract-method split - no gate condition, halt/degraded status, error message, or
control-flow order changed. `run()` itself now reads as a sequential list of named steps
with early-return halts, calling into this module.

Kept in a separate module (rather than as further module-level functions in
phase7_signal_generation.py) because none of these steps reference
`compute_signal_quality_components` - the two call sites of that shared scoring formula
(the main inline scorer inside `_get_candidates_from_buysell` and the orphaned-signal
backfill scorer) both stay in phase7_signal_generation.py itself, since
tests/unit/test_signal_quality_score_single_source_of_truth_20260820.py inspects that
module's own source text and asserts it contains >= 2 occurrences of that call.

Functions here that need names defined in phase7_signal_generation.py (the module-level
constant `_BUYSELL_LOOKBACK_DAYS`, and helpers `_check_market_regime`,
`_get_candidates_from_buysell`, `_should_halt_on_zero_scored_symbols`,
`_detect_upstream_data_quality_drift`, `_validate_composite_score_for_ranking`,
`_check_liquidity_parallel`) import them locally inside each function body rather than at
module level, to avoid a circular import - phase7_signal_generation.py imports this module's
functions at module load time, so a top-level import back the other way would deadlock.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import date as _date
from typing import Any

from algo.orchestrator.phase_data_contract import ExposureConstraints, validate_phase_data
from algo.orchestrator.phase_result import PhaseResult
from algo.orchestrator.validation_thresholds import LIQUIDITY_CHECK_LIMIT, PHASE7_LIQUIDITY_CHECK_WORKERS
from utils.db.context import DatabaseContext
from utils.loaders.timeout_enforcement import cancel_loader_timeout, setup_loader_timeout

logger = logging.getLogger(__name__)


def _compute_signal_quality_scores_for_run(
    run_date: _date, dry_run: bool, log_phase_result_fn: Callable[..., Any]
) -> tuple[dict[str, Any], PhaseResult | None]:
    """SESSION 367 FIX: Compute signal quality scores BEFORE Phase 8 entry.

    CRITICAL: Signal quality scores must be available for Phase 8 to apply quality gates.
    This prevents trades from entering without SQS >= 75 validation (root cause of 38.5% win rate).
    OPTIMIZATION (Session Current): Reduced backfill_days from 60 to 3 to eliminate lock contention.
    Phase 7 runs 3x daily (9:30 AM, 1 PM, 3 PM) so 3-day lookback ensures all recent signals scored.
    This reduces processing from 5468 symbols for 60 days -> ~1-2k symbol-days, holding lock 5 min instead of 35 min.
    CRITICAL FIX: Skip signal quality score computation in dry-run mode (no trades will execute anyway).

    Returns (score_result, halt_result). If halt_result is not None, the caller must return it
    immediately (score_result is not meaningful in that case).
    """
    from algo.orchestrator.phase7_signal_generation import _BUYSELL_LOOKBACK_DAYS, _should_halt_on_zero_scored_symbols

    if dry_run:
        logger.info("[PHASE 7] DRY-RUN: Skipping signal quality score computation (not needed for dry-run)")
        score_result: dict[str, Any] = {"symbols_processed": 0, "symbols_failed": 0}
    else:
        # CRITICAL FIX (Session Current): Check if today's signal_quality_scores are already computed.
        # Phase 7 runs 3x daily (9:30 AM, 1 PM, 3 PM) and all three runs were calling loader.run(),
        # causing lock contention. If run_date's scores are already in the table, skip the loader call.
        today_scores_exist = False
        try:
            with DatabaseContext("read") as cur:
                # Use run_date (the caller's Eastern trading date), not bare CURRENT_DATE -
                # CURRENT_DATE resolves in the DB session's timezone, which may not track
                # the Eastern trading day (e.g. UTC flips over ~4-5h before Eastern midnight,
                # so an evening run would see "today" as tomorrow and wrongly conclude no
                # scores exist yet, re-running the loader unnecessarily and reintroducing the
                # lock-contention this check exists to prevent).
                cur.execute(
                    "SELECT COUNT(*) FROM signal_quality_scores WHERE date = %s",
                    (run_date,),
                )
                result = cur.fetchone()
                count = result[0] if result else 0
                today_scores_exist = count > 0
                if today_scores_exist:
                    logger.info(f"[PHASE 7] Today's signal_quality_scores already computed ({count} rows exist)")
        except Exception as check_err:
            logger.warning(f"[PHASE 7] Could not check if today's scores exist (will proceed with loader): {check_err}")

        try:
            from concurrent.futures import TimeoutError as _FutureTimeoutError

            from loaders.load_signal_quality_scores import SignalQualityScoresLoader

            if today_scores_exist:
                logger.info("[PHASE 7] Skipping signal quality score loader (today's scores already available)")
                score_result = {"symbols_processed": 0, "symbols_failed": 0, "already_computed_today": True}
            else:
                logger.info("[PHASE 7] Computing signal quality scores before Phase 8 entry execution")
                loader = SignalQualityScoresLoader()

                # OPTIMIZATION: Only compute scores for symbols with actual BUY signals, not all 4896 symbols.
                # This cuts execution time by ~80% (600-900 symbols vs 4896 total).
                # Query buy_sell_daily for recent BUY signals to get the target symbol list.
                with DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT DISTINCT symbol FROM buy_sell_daily
                        WHERE signal = 'BUY' AND date >= CURRENT_DATE - %s
                        ORDER BY symbol
                    """,
                        (_BUYSELL_LOOKBACK_DAYS,),
                    )
                    signal_symbols = [row[0] for row in cur.fetchall()]

                if not signal_symbols:
                    # No BUY signals at all - fall back to empty result (Phase 8 handles gracefully)
                    logger.warning(
                        "[PHASE 7] No BUY signals found in buy_sell_daily. Skipping quality score computation."
                    )
                    score_result = {"symbols_processed": 0, "symbols_failed": 0, "no_signals_found": True}
                else:
                    logger.info(
                        f"[PHASE 7] Computing scores for {len(signal_symbols)} symbols with BUY signals (vs 4896 total active). "
                        f"Optimization: 80% reduction in computation scope."
                    )
                    # Use watermark-based incremental loading: only recompute scores for symbols
                    # whose underlying data (buy_sell_daily signals, technical indicators) have changed
                    # since the last score update. This is tracked via updated_at watermark.
                    loader_start = time.time()
                    # CRITICAL FIX (Session 96): Use centralized timeout config instead of hardcoded 600s
                    # Hardcoded 600s was timing out signal_quality at 10m despite config allowing 15m (900s)
                    # This caused Phase 7 timeouts cascading from other loader delays
                    from loaders.loader_timeout_config import get_loader_timeout

                    loader_timeout_secs = get_loader_timeout("signal_quality")

                    # SESSION 111 FIX: Set up timeout enforcement for in-process loader
                    # This prevents hung signal_quality_scores from blocking entire orchestrator
                    setup_loader_timeout("signal_quality_scores", loader_timeout_secs)
                    try:
                        score_result = loader.run(
                            symbols=signal_symbols,
                            parallelism=8,
                        )
                    finally:
                        # SESSION 111 FIX: Cancel timeout to prevent it firing on unrelated code
                        cancel_loader_timeout()

                    loader_elapsed = time.time() - loader_start
                    if loader_elapsed > loader_timeout_secs:
                        logger.warning(
                            f"[PHASE 7] Signal quality score loader took {loader_elapsed:.0f}s (exceeded {loader_timeout_secs}s timeout)"
                        )
                        msg = (
                            f"[PHASE 7 CRITICAL] Signal quality score computation exceeded timeout ({loader_elapsed:.0f}s > {loader_timeout_secs}s). "
                            f"This indicates the loader is stalled or locked. Cannot proceed without valid signal scores."
                        )
                        logger.critical(msg)
                        log_phase_result_fn(7, "signal_generation", "halt", msg)
                        return {}, PhaseResult(
                            7,
                            "signal_generation",
                            "halted",
                            {"qualified_trades": [], "liquidity_passed": 0},
                            True,
                            msg,
                        )
        except Exception as e:
            # Handle LockAcquisitionError FIRST - don't halt on temporary lock contention
            # CRITICAL: This must come before TimeoutError, as both may indicate lock issues
            from algo.exceptions import LockAcquisitionError

            # Check multiple ways: isinstance, type name, string message
            # Lock errors can be wrapped or have import timing issues
            error_str = str(e)
            error_type_name = type(e).__name__
            is_lock_error = (
                isinstance(e, LockAcquisitionError)
                or error_type_name == "LockAcquisitionError"
                or "LockAcquisitionError" in error_type_name
                or "lock" in error_str.lower()
            )
            if is_lock_error:
                # Temporary lock issue - log warning but don't halt
                msg = (
                    "[PHASE 7 WARNING] Signal quality score loader could not acquire lock (temporary contention). "
                    "Will proceed without updated scores. Trades will use previously cached scores if available."
                )
                logger.warning(msg)
                log_phase_result_fn(7, "signal_generation", "degraded", msg)
                # Return empty result - downstream Phase 8 will detect and handle gracefully
                score_result = {"symbols_processed": 0, "symbols_failed": 0, "lock_contention": True}
            elif isinstance(e, (TimeoutError, _FutureTimeoutError)):
                # Timeout (separate from lock acquisition) - also graceful degradation
                msg = (
                    "[PHASE 7 WARNING] Signal quality score computation timed out. "
                    "Will proceed without updated scores. Trades will use previously cached scores if available."
                )
                logger.warning(msg)
                log_phase_result_fn(7, "signal_generation", "degraded", msg)
                score_result = {"symbols_processed": 0, "symbols_failed": 0, "timeout": True}
            else:
                # CRITICAL: Other errors halt Phase 7
                # Signal quality scores are REQUIRED for Phase 8 entry gates.
                # If computation fails, trades cannot proceed safely - must halt and investigate.
                msg = (
                    f"[PHASE 7 CRITICAL] Signal quality score computation failed: {type(e).__name__}: {e}. "
                    f"Signal quality scores are REQUIRED for Phase 8 entry validation. "
                    f"Cannot proceed without valid signal scores. Check loader logs for details."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return {}, PhaseResult(
                    7,
                    "signal_generation",
                    "halted",
                    {"qualified_trades": [], "liquidity_passed": 0},
                    True,
                    msg,
                )

        # CRITICAL: Validate result structure before using it
        if not isinstance(score_result, dict):
            raise RuntimeError(
                f"Signal quality score loader returned invalid type: {type(score_result).__name__}. "
                f"Expected dict with 'symbols_failed' and 'symbols_processed' keys."
            )

        if "symbols_failed" not in score_result:
            raise RuntimeError(
                f"Signal quality score result missing 'symbols_failed' key. "
                f"Loader must return complete result structure. Got keys: {score_result.keys()}"
            )

        symbols_failed = score_result["symbols_failed"]
        if symbols_failed > 0:
            logger.warning(f"[PHASE 7] Signal quality score computation had {symbols_failed} failures: {score_result}")

        if "symbols_processed" not in score_result:
            raise RuntimeError(
                f"Signal quality score result missing 'symbols_processed' key. "
                f"Loader must return complete result structure. Got keys: {score_result.keys()}"
            )

        symbols_processed = score_result["symbols_processed"]
        logger.info(f"[PHASE 7] Signal quality scores computed: {symbols_processed} symbols")

        # CRITICAL: Validate that scores were actually computed.
        # If symbols_processed == 0, the loader couldn't acquire lock or hit an error.
        # This happens when signal_quality_scores lock is held by stale process.
        # EXCEPTION: If lock_contention flag is set, we already logged this as degraded mode
        # and should NOT halt - Phase 8 will proceed without updated scores.
        # EXCEPTION: If already_computed_today is set, symbols_processed=0 is the skip
        # sentinel from the "today's scores already exist" fast path above, not a failure -
        # live-confirmed 2026-08-03: the loader completed successfully at 09:39-09:40
        # (53,353 rows, loader_execution_history status=success), then Phase 7 re-ran at
        # 09:42, correctly skipped re-computing, and this check treated that intentional
        # skip as "loader failed to acquire lock" and halted the entire orchestrator -
        # blocking Phase 8 entries on data that was valid and current.
        # EXCEPTION: If no_signals_found is set, symbols_processed=0 means there were simply
        # no BUY signals in buy_sell_daily to score (e.g. stale upstream data, quiet market) -
        # live-confirmed 2026-08-10: this legitimately-empty result was falling through to the
        # same "failed to acquire the processing lock" halt message despite the no_signals_found
        # branch's own comment saying "Phase 8 handles gracefully", cascading a benign
        # zero-signals morning into a full orchestrator halt (Phase 7 halted -> Phase 8/9 errored).
        if symbols_processed == 0 and _should_halt_on_zero_scored_symbols(score_result):
            msg = (
                "[PHASE 7 CRITICAL] Signal quality score computation produced 0 symbols processed. "
                "This indicates the loader failed to acquire the processing lock (likely held by stale process) "
                "or completed with no symbols to process. Signal quality scores are REQUIRED for Phase 8 entry validation. "
                "Check: (1) Stale signal_quality_scores locks in database, (2) Upstream data availability, "
                "(3) Loader infrastructure status. Cannot proceed without valid signal scores."
            )
            logger.critical(msg)
            log_phase_result_fn(7, "signal_generation", "halt", msg)
            return {}, PhaseResult(
                7,
                "signal_generation",
                "halted",
                {"qualified_trades": [], "liquidity_passed": 0},
                True,
                msg,
            )

    return score_result, None


def _check_halt_flag_gate(
    check_halt_flag: Callable[..., bool] | None, log_phase_result_fn: Callable[..., Any]
) -> PhaseResult | None:
    """Halt flag check before generating signals - can be set by Phase 1 (data quality) or
    Phase 2 (circuit breaker)."""
    if check_halt_flag and check_halt_flag():
        # Check halt_reason to provide clearer diagnostics
        halt_reason = "unknown halt condition"
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT halt_reason FROM algo_runtime_state WHERE state_key = 'orchestrator_halt'")
                result = cur.fetchone()
                if result and result[0]:
                    halt_reason = result[0]
        except Exception as diagnostic_err:
            logger.debug(f"[PHASE 7] Could not fetch halt reason for diagnostics: {diagnostic_err}")

        logger.critical(f"[PHASE 7] Halt flag detected (reason: {halt_reason[:100]}). Halting signal generation.")
        log_phase_result_fn(7, "signal_generation", "halt", f"Halt flag set: {halt_reason[:150]}")
        return PhaseResult(
            7,
            "signal_generation",
            "halted",
            {"qualified_trades": [], "liquidity_passed": 0},
            True,
            f"Halt flag set: {halt_reason}",
        )
    # Not an error: no halt flag set, caller continues signal generation as normal.
    return None


def _check_market_regime_gate(
    run_date: _date, log_phase_result_fn: Callable[..., Any]
) -> tuple[dict[str, Any], PhaseResult | None]:
    """Market regime gate: halt if entries not allowed per market_exposure_daily."""
    from algo.orchestrator.phase7_signal_generation import _check_market_regime

    regime = _check_market_regime(run_date)
    logger.info(
        f"[PHASE 7] Market regime: {regime['regime']} "
        f"exposure={regime['exposure_pct']:.0f}% "
        f"entry_allowed={regime['is_entry_allowed']}"
    )
    if not regime["is_entry_allowed"]:
        reasons = "; ".join(regime["halt_reasons"]) if regime["halt_reasons"] else "no halt reasons logged"
        logger.warning(f"[PHASE 7] Entries halted by market regime: {reasons}")
        log_phase_result_fn(
            7,
            "signal_generation",
            "halt",
            f"Market regime halted entries: {reasons[:500]}",
        )
        return regime, PhaseResult(
            7,
            "signal_generation",
            "halted",
            {"qualified_trades": [], "liquidity_passed": 0},
            True,
            reasons[:500],
        )
    return regime, None


def _check_exposure_constraints_gate(
    exposure_constraints: ExposureConstraints | None, log_phase_result_fn: Callable[..., Any]
) -> PhaseResult | None:
    """ISSUE #7 FIX: Exposure policy gate - fail-closed if constraints not provided."""
    if exposure_constraints is None:
        msg = (
            "[PHASE 7 CRITICAL] Exposure constraints not provided by Phase 5. "
            "Cannot proceed with signal generation without knowing market exposure limits. "
            "Check that Phase 5 (Exposure Policy) completed successfully."
        )
        logger.critical(msg)
        log_phase_result_fn(7, "signal_generation", "halt", msg)
        phase_data = {"qualified_trades": [], "liquidity_passed": 0}
        validate_phase_data(7, phase_data)
        return PhaseResult(7, "signal_generation", "halted", phase_data, True, msg)

    # VALIDATION: Detect if Phase 5 failed and we're using fallback defaults (fail-safe mode)
    if (
        exposure_constraints
        and exposure_constraints.get("tier_name") == "CORRECTION"
        and exposure_constraints.get("risk_multiplier") == 0.0
        and exposure_constraints.get("max_new_positions_today") == 0
    ):
        logger.warning(
            "[PHASE 7] Using fallback CORRECTION constraints (tier_name=CORRECTION, risk_multiplier=0.0). "
            "Phase 5 (Exposure Policy) may have failed - verify via orchestrator logs. "
            "Trading is restricted to exits and rebalancing only."
        )

    if exposure_constraints and exposure_constraints.get("halt_new_entries"):
        reason = exposure_constraints.get("halt_reason")
        if not reason:
            logger.critical(
                "CRITICAL: Exposure policy halted entries but no halt_reason provided. "
                "Cannot determine why trading is halted. Exposure policy data incomplete."
            )
            raise ValueError(
                "Exposure constraints: halt_new_entries=True but halt_reason missing. "
                "Must provide explicit reason for halt."
            )
        logger.warning(f"[PHASE 7] {reason}")
        log_phase_result_fn(7, "signal_generation", "halt", reason)
        return PhaseResult(
            7, "signal_generation", "halted", {"qualified_trades": [], "liquidity_passed": 0}, True, reason
        )

    # Not an error: exposure constraints permit new entries, caller continues.
    return None


def _fetch_and_handle_candidates(
    run_date: _date,
    min_composite_score: float,
    min_close_quality: float,
    log_phase_result_fn: Callable[..., Any],
) -> tuple[list[dict[str, Any]], PhaseResult | None]:
    """Primary: buy_sell_daily pivot-breakout BUY signals filtered by stock_scores ranking.

    NO FALLBACK: If buy_sell_daily is unexpectedly empty, anomaly detection caught it in
    _check_critical_dependencies() and halted. If we reach here, buy_sell_daily must have data.
    """
    from algo.orchestrator.phase7_signal_generation import _get_candidates_from_buysell

    try:
        raw_candidates = _get_candidates_from_buysell(
            run_date, min_composite_score, min_close_quality=min_close_quality
        )

        if not raw_candidates:
            msg = (
                f"[PHASE 7] No BUY signals found in lookback window (prior trading day through {run_date}, "
                f"min_composite_score={min_composite_score}). Possible causes: (1) buy_sell_daily has no recent signals "
                f"(EOD pipeline may not have run yet), (2) all signals below min_score threshold, "
                f"(3) market regime prevents entries. Check market_exposure_daily for regime/halt_entries."
            )
            logger.warning(msg)
            log_phase_result_fn(7, "signal_generation", "no_signals", msg)
            # Report truth: no trades generated (degraded state, not success)
            return [], PhaseResult(
                7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
            )
    except ValueError as e:
        # CONSISTENCY FIX #2: Validation errors now raise exceptions (not silent degradation)
        # Categorize as DATA_INVALID so operators know why signals are missing
        from algo.orchestrator.phase_error_handling import (
            ErrorCategory,
            PhaseError,
            log_phase_error,
        )

        error = PhaseError(
            category=ErrorCategory.DATA_INVALID,
            message=f"Signal validation failed: {str(e)[:200]}",
            root_cause="Required fields missing from buy_sell_daily signals",
            recoverable=False,
            log_level="critical",
        )
        log_phase_error(7, error, log_phase_result_fn)
        return [], PhaseResult(
            7,
            "signal_generation",
            "halted",
            {"qualified_trades": [], "liquidity_passed": 0},
            True,
            error.message,
        )
    except RuntimeError as e:
        # DB or data loading error
        from algo.orchestrator.phase_error_handling import (
            ErrorCategory,
            PhaseError,
            log_phase_error,
        )

        error = PhaseError(
            category=ErrorCategory.DATA_MISSING,
            message=f"Failed to fetch buy_sell_daily signals: {str(e)[:200]}",
            root_cause="Check that EOD pipeline (4:05 PM ET) has completed and buy_sell_daily loader ran",
            recoverable=False,
            log_level="critical",
        )
        log_phase_error(7, error, log_phase_result_fn)
        return [], PhaseResult(
            7,
            "signal_generation",
            "halted",
            {"qualified_trades": [], "liquidity_passed": 0},
            True,
            error.message,
        )

    if not raw_candidates:
        msg = (
            "[PHASE 7] No candidates found (buy_sell_daily empty AND stock_scores fallback returned 0 rows). "
            "Check: (1) stock_scores table has data, (2) market regime allows entries, "
            "(3) price_daily has recent data for trending symbols."
        )
        logger.warning(msg)
        log_phase_result_fn(7, "signal_generation", "no_signals", msg)
        return [], PhaseResult(
            7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
        )

    return raw_candidates, None


def _apply_post_fetch_quality_filters(
    raw_candidates: list[dict[str, Any]],
    run_date: _date,
    signal_source: str,
    log_phase_result_fn: Callable[..., Any],
) -> tuple[list[dict[str, Any]], PhaseResult | None]:
    """Sequential post-fetch signal-quality-score filters + final composite_score-descending sort.

    All trend and close quality validation happens at SQL level in _get_candidates_from_buysell().
    Candidates here are already filtered for: close > sma_50, close_position > min_close_quality.
    This eliminates wasted I/O and ensures data quality drift is detected immediately.
    """
    from algo.orchestrator.phase7_signal_generation import (
        _detect_upstream_data_quality_drift,
        _validate_composite_score_for_ranking,
    )

    quality_filtered = raw_candidates

    # CRITICAL FIX (Session 383): Signal quality scores already computed in _get_candidates_from_buysell()
    # All candidates here already have signal_quality_score from technical data (RSI, MACD, Minervini, Weinstein)
    # Removed redundant computation - just validate they exist
    if quality_filtered:
        missing_scores = sum(1 for c in quality_filtered if c.get("signal_quality_score") is None)
        if missing_scores > 0:
            logger.info(
                f"[PHASE 7] {missing_scores}/{len(quality_filtered)} candidates missing signal quality scores "
                f"(insufficient technical data during candidate fetch). These will be rejected."
            )
            # Filter out signals without valid SQS (fail-fast validation)
            quality_filtered = [c for c in quality_filtered if c.get("signal_quality_score") is not None]
            if not quality_filtered:
                # No candidates have signal_quality_scores (likely due to missing technical data)
                # This is an expected state - some days have no tradeable signals with sufficient history
                msg = "[PHASE 7] All candidates rejected due to missing signal quality scores (insufficient technical data)"
                logger.info(msg)
                log_phase_result_fn(7, "signal_generation", "no_data", msg)
                return [], PhaseResult(
                    7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
                )

    # Check for upstream data quality issues (e.g., composite_score not populated)
    upstream_drift = _detect_upstream_data_quality_drift(run_date, signal_source)
    if upstream_drift.get("has_drift"):
        logger.warning(
            f"[PHASE 7] Upstream data quality drift detected: {upstream_drift.get('drift_message', 'Unknown issue')}. "
            f"This may suppress valid candidates."
        )

    # signal_quality_score is still required to be present here even though it's no longer the
    # ranking key (RESTORED to composite_score 2026-08-27 - see module docstring for the full
    # history/evidence): Phase 8's separate min_signal_quality_score floor gate still needs a
    # real numeric SQS for every surviving candidate, so a candidate without one is still
    # rejected at this stage rather than deferred to a less clear failure downstream.

    # Defensive: Filter out any candidates with None signal_quality_score (shouldn't happen but catch edge cases)
    before_filter = len(quality_filtered)
    quality_filtered = [c for c in quality_filtered if c.get("signal_quality_score") is not None]
    after_filter = len(quality_filtered)
    if before_filter > after_filter:
        logger.warning(
            f"[PHASE 7] Filtered out {before_filter - after_filter}/{before_filter} candidates with None signal_quality_score. "
            f"Remaining: {after_filter} candidates."
        )

    if not quality_filtered:
        msg = "[PHASE 7] All candidates rejected due to missing signal quality scores (edge case after filtering)"
        logger.warning(msg)
        log_phase_result_fn(7, "signal_generation", "no_data", msg)
        return [], PhaseResult(
            7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
        )

    # Final defensive filter: Remove any None values that made it through previous filters
    # Edge case handling: if a signal's technical data became unavailable or an earlier filter missed it,
    # this catches it and removes it gracefully instead of crashing Phase 7
    none_sqs_candidates = [c for c in quality_filtered if c.get("signal_quality_score") is None]
    if none_sqs_candidates:
        error_symbols = [c.get("symbol") for c in none_sqs_candidates]
        logger.warning(
            f"[PHASE 7] {len(none_sqs_candidates)} candidates with None signal_quality_score "
            f"escaped prior filters: {error_symbols}. Filtering out and continuing."
        )
        # Remove them gracefully instead of crashing
        quality_filtered = [c for c in quality_filtered if c.get("signal_quality_score") is not None]

    # Verify we still have candidates after the final filter
    if not quality_filtered:
        msg = "[PHASE 7] All candidates rejected (final filter removed all with None signal_quality_score)"
        logger.warning(msg)
        log_phase_result_fn(7, "signal_generation", "no_data", msg)
        return [], PhaseResult(
            7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
        )

    for sig in quality_filtered:
        _validate_composite_score_for_ranking(sig.get("composite_score"), sig.get("symbol"))

    # CRITICAL: Final defensive filter - remove ANY signals with None scores before sorting
    # (defensive in case filtering above had gaps)
    quality_filtered = [s for s in quality_filtered if s.get("signal_quality_score") is not None]
    if not quality_filtered:
        msg = (
            "[PHASE 7 CRITICAL] All signals filtered out in final defensive check. "
            "This should not happen if quality filter worked correctly above."
        )
        logger.critical(msg)
        return [], PhaseResult(
            7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
        )

    # RANKING KEY (restored 2026-08-27 - see module docstring): composite_score descending.
    quality_filtered.sort(key=lambda s: float(s["composite_score"]), reverse=True)

    return quality_filtered, None


def _run_liquidity_checks(
    quality_filtered: list[dict[str, Any]], run_date: _date, config: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], int]:
    """Liquidity checks on top candidates - parallelized.

    ISSUE 13 FIX: Improved timeout handling with per-task monitoring.
    """
    from algo.orchestrator.phase7_signal_generation import _check_liquidity_parallel

    liq_passed: list[dict[str, Any]] = []
    liq_checked = 0
    to_check = quality_filtered[:LIQUIDITY_CHECK_LIMIT]

    if to_check:
        try:
            executor = ThreadPoolExecutor(max_workers=PHASE7_LIQUIDITY_CHECK_WORKERS, thread_name_prefix="phase7_liq")
            pending_symbols = []
            completed_results = {}

            try:
                # Submit all tasks
                future_to_symbol = {
                    executor.submit(_check_liquidity_parallel, cand, run_date, config): cand for cand in to_check
                }

                # ISSUE 13 FIX: Wait with timeout per completed future
                executor_timeout = 60  # seconds - overall limit for all futures

                for future in as_completed(future_to_symbol, timeout=executor_timeout):
                    liq_checked += 1
                    candidate = future_to_symbol[future]
                    symbol = candidate.get("symbol", "UNKNOWN")

                    try:
                        result = future.result(timeout=2)  # Per-future timeout is shorter
                        candidate_result, passed = result
                        completed_results[symbol] = passed
                        if passed:
                            liq_passed.append(candidate_result)
                    except FutureTimeoutError:
                        logger.warning(
                            f"[PHASE 7] Liquidity check timed out for {symbol} (exceeds 2s per-future limit)"
                        )
                        pending_symbols.append(symbol)
                    except Exception as e:
                        logger.error(f"[PHASE 7] Liquidity check failed for {symbol}: {e}")
                        pending_symbols.append(symbol)

            except FutureTimeoutError:
                logger.critical(
                    f"[PHASE 7] Overall liquidity check timeout - {len(pending_symbols)} symbols still pending "
                    f"(exceeded {executor_timeout}s overall limit)"
                )
            finally:
                # ISSUE 13 FIX: Kill hanging threads instead of waiting
                executor.shutdown(wait=False)

            # Log skipped symbols
            if pending_symbols:
                logger.warning(
                    f"[PHASE 7] Skipping {len(pending_symbols)} symbols due to timeout: {pending_symbols[:10]}"
                )

            # Continue with results we got
            logger.info(
                f"[PHASE 7] Liquidity check completed: {len(liq_passed)} passed, "
                f"{len(pending_symbols)} skipped (timeout)"
            )

        except Exception as executor_exc:
            # CRITICAL FIX: Re-raise exceptions instead of silently continuing
            # If executor setup fails or critical errors occur, halt Phase 7
            logger.critical(
                f"[PHASE 7 CRITICAL] ThreadPoolExecutor failure during liquidity checks: {type(executor_exc).__name__}: {executor_exc}. "
                f"Cannot verify liquidity for {len(to_check)} candidates. "
                f"Liquidity checks are critical for trading safety - failing fast instead of proceeding with unverified candidates."
            )
            msg = (
                f"[PHASE 7] Liquidity check system failure: {type(executor_exc).__name__}. "
                f"Cannot proceed with signal generation without liquidity validation. "
                f"Check system resources (thread pool, memory, database connections) and retry."
            )
            raise RuntimeError(msg) from executor_exc

    logger.info(
        f"[PHASE 7] Liquidity check: {liq_checked} checked, {len(liq_passed)} passed. "
        f"{len(quality_filtered) - liq_checked} unchecked candidates dropped."
    )

    return liq_passed, liq_checked


def _filter_inactive_symbols(liq_passed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter out inactive symbols (symbols not available in Alpaca/trading platforms)."""
    if liq_passed:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """SELECT symbol FROM stock_symbols WHERE symbol = ANY(%s) AND active = false""",
                    ([sig.get("symbol") for sig in liq_passed],),
                )
                inactive_set = {row[0] for row in cur.fetchall()}

            inactive_removed = [sig for sig in liq_passed if sig.get("symbol") in inactive_set]
            if inactive_removed:
                logger.warning(
                    f"[PHASE 7] Filtering {len(inactive_removed)} inactive symbols: "
                    f"{', '.join(sig['symbol'] for sig in inactive_removed)}"
                )
            liq_passed = [sig for sig in liq_passed if sig.get("symbol") not in inactive_set]
        except Exception as e:
            logger.warning(f"[PHASE 7] Could not filter inactive symbols: {e}. Continuing with current list.")
    return liq_passed


def _finalize_ranking_and_log(liq_passed: list[dict[str, Any]], signal_source: str) -> None:
    """Final ranking by composite_score (already validated by quality_filtered sort, but
    re-validate for safety), then log the top 10 qualified signals. Mutates liq_passed in
    place (sorts it)."""
    from algo.orchestrator.phase7_signal_generation import _validate_composite_score_for_ranking

    if liq_passed:
        for sig in liq_passed:
            # composite_score and signal_date are critical; market_stage is optional (used only for logging)
            required_fields = ["composite_score", "signal_date"]
            missing_fields = [f for f in required_fields if f not in sig or sig[f] is None]
            if missing_fields:
                sym = sig.get("symbol", "UNKNOWN_SYMBOL")
                raise ValueError(
                    f"[PHASE 7 CRITICAL] Liquidity-passed signal {sym} missing required fields: {missing_fields}. "
                    f"Cannot log or execute incomplete signal data. Signal keys: {list(sig.keys())}. "
                    f"Check upstream signal generation pipeline for data quality issues."
                )
            # market_stage is optional - provide default if missing (used only for logging)
            if not sig.get("market_stage"):
                sig["market_stage"] = "unknown"
        for sig in liq_passed:
            _validate_composite_score_for_ranking(sig.get("composite_score"), sig.get("symbol"))
        liq_passed.sort(key=lambda s: float(s["composite_score"]), reverse=True)

    logger.info(f"[PHASE 7] Top 10 qualified signals (source={signal_source}):")
    for i, sig in enumerate(liq_passed[:10]):

        def _fmt(v: Any, spec: str = ":.1f") -> str:
            return format(v, spec[1:]) if v is not None else "?"

        buylevel_str = (
            f" buylevel={_fmt(sig.get('buylevel'), ':.2f')} signal_date={sig['signal_date']}"
            if sig.get("buylevel")
            else ""
        )
        logger.info(
            f"  {i + 1}. {sig['symbol']:6s} "
            f"sqs={_fmt(sig.get('signal_quality_score'))} "
            f"composite={_fmt(sig.get('composite_score'))} "
            f"momentum={_fmt(sig.get('momentum_score'))} "
            f"rs_pct={_fmt(sig.get('rs_percentile'))} "
            f"stage={sig['market_stage']}"
            f"{buylevel_str}"
        )
