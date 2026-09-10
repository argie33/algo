"""Orchestrator mixin (OrchestratorFinalReportMixin), extracted from orchestrator.py
(file-size ratchet split, 2026-09-10). Methods moved verbatim - no behavior change -
except call sites for names some test files patch at module level on
algo.orchestration.orchestrator (DatabaseContext/datetime/get_event_hub/run_phaseN)
now go through `_owner()` so that patching keeps working regardless of which mixin
file actually calls them; see `_owner()`'s own docstring. Mixed into Orchestrator via
multiple inheritance in orchestrator.py - every other `self.` call here resolves
normally through the instance regardless of which mixin file defines it.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from algo.orchestration._orchestrator_protocol import OrchestratorProtocol

    _Base = OrchestratorProtocol
else:
    _Base = object

logger = logging.getLogger(__name__)


class OrchestratorFinalReportMixin(_Base):
    def _final_report(self) -> dict[str, Any]:
        logger.info(f"\n{'#' * 70}")
        logger.info(f"#   FINAL REPORT - {self.run_id}")
        logger.info(f"{'#' * 70}")
        for n, info in sorted(self.phase_results.items(), key=lambda x: str(x[0])):
            # Phase 6's dry-run stub reuses status="degraded" (see the any_degraded exclusion
            # below for why the aggregation logic already treats this as benign) - display it
            # with the same [SKIP] flag as a real skip instead of [DEGRAD], which reads as a
            # genuine per-item exit-execution problem to anyone scanning this report by eye.
            display_status = info["status"]
            if display_status == "degraded" and "DRY-RUN" in (info.get("summary") or ""):
                display_status = "skipped"
            status_flag = self._STATUS_FLAGS.get(display_status, "[?]   ")
            logger.info(f"  {status_flag} Phase {n}: {info['name']:22s} - {info['summary']}")
        logger.info(f"{'#' * 70}\n")

        any_error = any(p["status"] in ("error", "fail") for p in self.phase_results.values())
        any_halt = any(p["status"] == "halted" for p in self.phase_results.values())
        # FIX (2026-07-27): Phase 6 reports status="degraded" for two unrelated reasons -
        # a benign, unconditional "DRY-RUN: execution skipped (no real trades)" stub
        # (phase6_exit_execution.py's dry_run branch returns before any real per-item
        # execution logic even runs, so this text can never coexist with a real error) vs.
        # genuine per-item exit-execution errors (errors > 0). Both used the same "degraded"
        # status string, so any_degraded below used to be true for both - which made the
        # elif chain always take the "real degraded" branch (overall_status="degraded",
        # success=False) whenever a local dry-run test happened to also hit Phase 8's
        # market-hours/freshness guard (status="blocked"), even though that combination -
        # a dry-run stub plus an expected safety block - is exactly what a healthy pre-market
        # local test run looks like. The already-correct "blocked guard + Phase 9 ok = ok"
        # logic further down never got a chance to run. Excluding the dry-run stub from
        # any_degraded lets that existing logic decide the outcome instead.
        # "completed_degraded" (Phase 3's cursor-retry-exhaustion status, phase3_position_monitor.py)
        # was not recognized here, so a genuinely degraded Phase 3 run fell through every any_*
        # check below and landed on overall_status="success" - the dashboard's PHASE EXECUTION
        # DETAILS panel showed it as a real warning while Run History showed the same run as OK.
        any_degraded = any(
            p["status"] in ("degraded", "completed_degraded") and "DRY-RUN" not in (p.get("summary") or "")
            for p in self.phase_results.values()
        )
        any_blocked = any(p["status"] == "blocked" for p in self.phase_results.values())
        any_skipped = any(p["status"] == "skipped" for p in self.phase_results.values())

        # CRITICAL FIX: If a phase has status="halted", it's a policy halt (e.g., circuit breaker),
        # not an error. Don't mark overall as "error" just because a halt occurred.
        # Priority: halted > error (a halt is a controlled stop, error is unexpected)
        if any_halt:
            any_error = False  # Halt takes precedence over error status

        # Determine reason for halt/skip if applicable
        skip_reason = None
        if any_error:
            skip_reason = next(
                (p["summary"] for p in self.phase_results.values() if p["status"] in ("error", "fail")),
                "orchestrator_error",
            )
        elif any_halt:
            skip_reason = next(
                (p["summary"] for p in self.phase_results.values() if p["status"] == "halted"),
                "circuit_breaker_halted",
            )
        elif any_degraded:
            skip_reason = next(
                (
                    p["summary"]
                    for p in self.phase_results.values()
                    if p["status"] in ("degraded", "completed_degraded")
                ),
                "phase_degraded",
            )
        elif any_skipped:
            skip_reason = next(
                (p["summary"] for p in self.phase_results.values() if p["status"] == "skipped"),
                "phase_skipped",
            )

        result = {
            "run_id": self.run_id,
            "run_date": self.run_date.isoformat(),
            "phases": [{"phase": n, **info} for n, info in sorted(self.phase_results.items(), key=lambda x: str(x[0]))],
            "success": not (any_error or any_halt or any_degraded or any_skipped),  # blocked handled separately below
            "halted": any_halt,  # Only actual halts (circuit breaker, errors) - not degraded/skipped
            "skipped": any_halt or any_degraded or any_skipped or any_blocked,  # Required by Lambda handler
            "reason": skip_reason or "none",  # Required by Lambda handler
        }

        # FIXED Issue #6: Save execution log for audit trail
        try:
            if any_error:
                overall_status = "error"
                # Look for error/fail status phases first, then halted (some phases use "halted" for errors)
                halt_reason = next(
                    (p["summary"] for p in self.phase_results.values() if p["status"] in ("error", "fail", "halted")),
                    "Unknown error - no phase summary available",
                )
            elif any_halt:
                overall_status = "halted"
                halt_reason = next(
                    (p["summary"] for p in self.phase_results.values() if p["status"] == "halted"),
                    "Halted - reason unknown",
                )
            elif any_degraded:
                overall_status = "degraded"
                halt_reason = next(
                    (
                        p["summary"]
                        for p in self.phase_results.values()
                        if p["status"] in ("degraded", "completed_degraded")
                    ),
                    "Degraded - reason unknown",
                )
            elif any_blocked:
                # CRITICAL: "blocked" means a safety guard stopped Phase 8 (risk limit, pending orders, market hours).
                # This is EXPECTED and CORRECT behavior - a guard preventing over-leveraging is not a failure.
                # If Phase 9 still runs and succeeds, the run is healthy.
                # FIX (2026-07-27): log_phase_result() stores {"name", "status", "summary"} per phase -
                # it never sets a "phase" key on the inner dict, so the old `p.get("phase") == 8` check
                # was always None == 8 (always False). phase_8_blocked was permanently False, so this
                # entire "blocked guard + Phase 9 ok = healthy run" branch never actually reached the
                # "ok" outcome - it always fell through to the "degraded" else below, silently
                # defeating the exact fix this comment describes. Check the dict key (the real phase
                # number) instead of a field that's never populated.
                phase_8_blocked = any(
                    phase_num == 8 and p["status"] == "blocked" for phase_num, p in self.phase_results.items()
                )
                # FAIL-FAST: Phase 9 must be present (always_run) - no fallback to alternate key type
                # CRITICAL FIX: phase_results should ALWAYS use int keys (9, not "9").
                # Trying both key types masks inconsistency in how phases store results.
                if 9 not in self.phase_results:
                    raise RuntimeError(
                        f"[ORCHESTRATOR CRITICAL] Phase 9 results missing from phase_results. "
                        f"Phase 9 is always_run=True and MUST be present for status determination. "
                        f"Available phase keys: {sorted(self.phase_results.keys())}. "
                        f"Key types should be int only. This indicates a bug in phase_executor or phase execution flow."
                    )
                phase_9_data = self.phase_results[9]
                if not phase_9_data:
                    raise RuntimeError(
                        "[ORCHESTRATOR CRITICAL] Phase 9 result is empty dict. "
                        "Phase 9 must return non-empty result with phase/name/status/summary fields."
                    )
                phase_9_succeeded = phase_9_data.get("status") in ("ok", "success")

                if phase_8_blocked and phase_9_succeeded:
                    # Phase 8 blocked by guard but Phase 9 (always_run) succeeded - healthy run with guard
                    overall_status = "ok"
                    halt_reason = next(
                        (p["summary"] for p in self.phase_results.values() if p["status"] == "blocked"),
                        "Blocked by guard - reason unknown",
                    )
                else:
                    # Block was unexpected or Phase 9 failed - mark as degraded
                    overall_status = "degraded"
                    halt_reason = next(
                        (p["summary"] for p in self.phase_results.values() if p["status"] == "blocked"),
                        "Blocked - reason unknown",
                    )
            elif any_skipped:
                # CRITICAL: Distinguish between "skipped due to market hours" vs "skipped due to upstream failure"
                # Phase 8 skipping due to market hours guard is EXPECTED and CORRECT behavior (9:30 AM - 4:00 PM ET).
                # If Phase 8 skipped for this reason and always-run Phase 9 succeeded, the run is healthy ("ok").
                # Only mark as "degraded" if skip was due to upstream phase failure.
                phase_8_market_hours_skip = any(
                    p["status"] == "skipped" and "MARKET HOURS GUARD" in p.get("summary", "")
                    for p in self.phase_results.values()
                )
                # FAIL-FAST: Phase 9 must be present (always_run) - no fallback to alternate key type
                # CRITICAL FIX: phase_results should ALWAYS use int keys (9, not "9").
                # Trying both key types masks inconsistency in how phases store results.
                if 9 not in self.phase_results:
                    raise RuntimeError(
                        f"[ORCHESTRATOR CRITICAL] Phase 9 results missing from phase_results. "
                        f"Phase 9 is always_run=True and MUST be present for status determination. "
                        f"Available phase keys: {sorted(self.phase_results.keys())}. "
                        f"Key types should be int only. This indicates a bug in phase_executor or phase execution flow."
                    )
                phase_9_data = self.phase_results[9]
                if not phase_9_data:
                    raise RuntimeError(
                        "[ORCHESTRATOR CRITICAL] Phase 9 result is empty dict. "
                        "Phase 9 must return non-empty result with phase/name/status/summary fields."
                    )
                phase_9_succeeded = phase_9_data.get("status") in ("ok", "success")

                if phase_8_market_hours_skip and phase_9_succeeded:
                    # Phase 8 skipped due to market hours but Phase 9 (always_run) succeeded - healthy run
                    overall_status = "ok"
                    halt_reason = next(
                        (p["summary"] for p in self.phase_results.values() if p["status"] == "skipped"),
                        "Skipped - reason unknown",
                    )
                else:
                    # Skip was due to upstream failure or other issue - mark as degraded
                    overall_status = "degraded"
                    halt_reason = next(
                        (p["summary"] for p in self.phase_results.values() if p["status"] == "skipped"),
                        "Skipped - reason unknown",
                    )
            else:
                overall_status = "success"
                halt_reason = None

            # Update result dict to reflect overall_status determination
            # (especially for blocked guards that ended up as ok_status)
            result["success"] = overall_status in ("success", "ok")

            self.execution_tracker.save_execution_log(overall_status, halt_reason)

            # ALSO write to algo_orchestrator_runs for backward compatibility and dashboard visibility
            try:
                self._save_orchestrator_run_status(overall_status, halt_reason)
            except Exception as e:
                logger.warning(f"[EXECUTION_LOG] Failed to save orchestrator run status: {e}")
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"[EXECUTION_LOG] Failed to save execution log: {e}")

        # Publish CloudWatch metrics (non-blocking - never let metrics interrupt trading)
        try:
            from algo.reporting import MetricsPublisher

            with MetricsPublisher(dry_run=self.dry_run) as m:
                m.put_orchestrator_result(bool(result["success"]), {str(k): v for k, v in self.phase_results.items()})

                # Extract numeric data from executor phase results (not self.phase_results)
                if hasattr(self, "executor") and self.executor:
                    # Signal count from phase 7 (signal generation)
                    phase7_result = self.executor.get_result(7)
                    if phase7_result and hasattr(phase7_result, "data"):
                        # CRITICAL: Check phase status before using defaults
                        # Distinguish: "phase halted" (0 attempted) vs "found 0 signals" (0 generated)
                        if phase7_result.halted:
                            # Phase was halted (upstream failure) - don't attempt to extract metrics
                            logger.debug(f"Phase 7 halted (reason: {phase7_result.error}), skipping metrics")
                            # Do NOT put signal count - let it remain None in metrics
                        else:
                            # Phase ran (halted=False) - extract signal count with explicit validation
                            signals = phase7_result.data.get("liquidity_passed")
                            if signals is None:
                                # Phase succeeded but field is missing - this is an error in phase data contract
                                logger.error(
                                    f"Phase 7 succeeded but missing 'liquidity_passed' field. "
                                    f"Data contract violation. Available keys: {list(phase7_result.data.keys())}"
                                )
                                # Don't put count - metrics will show None (data unavailable)
                            elif not isinstance(signals, int):
                                logger.warning(
                                    f"Phase 7 'liquidity_passed' has unexpected type {type(signals).__name__}: {signals!r}. "
                                    f"Signal count should be explicit integer."
                                )
                                # Don't put count - let it remain None
                            else:
                                m.put_signal_count(signals)
                    else:
                        logger.debug("Phase 7 result not found in executor")
                        # Don't put signal count - let it remain None in metrics

                    # Trade count from phase 8 (entry execution)
                    phase8_result = self.executor.get_result(8)
                    if phase8_result and hasattr(phase8_result, "data"):
                        if phase8_result.halted:
                            logger.debug(f"Phase 8 halted (reason: {phase8_result.error}), skipping metrics")
                        else:
                            trades = phase8_result.data.get("entered")
                            if isinstance(trades, int):
                                m.put_trade_count(trades)
                            elif trades is None:
                                logger.error(
                                    f"Phase 8 succeeded but missing 'entered' field. "
                                    f"Data contract violation. Available keys: {list(phase8_result.data.keys())}"
                                )
                            else:
                                logger.warning(f"Phase 8 returned non-int entered count: {type(trades).__name__}")
                    else:
                        logger.debug("Phase 8 result not found in executor")

                    # Open position count from phase 9 (reconciliation)
                    phase9_result = self.executor.get_result(9)
                    if phase9_result and hasattr(phase9_result, "data"):
                        if phase9_result.halted:
                            logger.debug(f"Phase 9 halted (reason: {phase9_result.error}), skipping metrics")
                        else:
                            positions = phase9_result.data.get("positions")
                            if isinstance(positions, int):
                                m.put_open_positions(positions)
                            elif positions is None:
                                logger.error(
                                    f"Phase 9 succeeded but missing 'positions' field. "
                                    f"Data contract violation. Available keys: {list(phase9_result.data.keys())}"
                                )
                            else:
                                logger.warning(f"Phase 9 returned non-int positions: {type(positions).__name__}")
                    else:
                        logger.debug("Phase 9 result not found in executor")
                else:
                    logger.warning("Executor not available for metric extraction")

        except (
            ValueError,
            ZeroDivisionError,
            TypeError,
            KeyError,
            AttributeError,
        ) as e:
            # Never let metrics publishing interrupt trading results
            logger.error(f"CloudWatch metric publish failed: {e}")

        return result
