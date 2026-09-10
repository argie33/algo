"""Orchestrator mixin (OrchestratorPhasesMixin), extracted from orchestrator.py
(file-size ratchet split, 2026-09-10). Methods moved verbatim - no behavior change -
except call sites for names some test files patch at module level on
algo.orchestration.orchestrator (DatabaseContext/datetime/get_event_hub/run_phaseN)
now go through `_owner()` so that patching keeps working regardless of which mixin
file actually calls them; see `_owner()`'s own docstring. Mixed into Orchestrator via
multiple inheritance in orchestrator.py - every other `self.` call here resolves
normally through the instance regardless of which mixin file defines it.
"""

import logging
import os
import time
from datetime import timezone
from typing import TYPE_CHECKING, Any, cast

from algo.orchestration.position_sync import sync_positions_from_trades, validate_position_count
from algo.orchestrator.phase_data_contract import ExposureConstraints
from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.orchestrator.phase_registry import PhaseRegistry

if TYPE_CHECKING:
    from algo.orchestration._orchestrator_protocol import OrchestratorProtocol

    _Base = OrchestratorProtocol
else:
    _Base = object

logger = logging.getLogger(__name__)


def _owner() -> Any:
    """Lazy reference to the owner module (algo.orchestration.orchestrator), resolved at
    call time not import time. Several tests patch `algo.orchestration.orchestrator.
    DatabaseContext` / `.datetime` / `.get_event_hub` / `.run_phase1` / `.run_phase2` /
    `.run_phase9` directly (module-level monkeypatching) - a plain top-level import of
    those names in THIS file would bind this module's own separate copy, which those
    patches can never reach. Going through `_owner().X` always reads whatever the owner
    module's current attribute is, mocked or real - same pattern as loaders/helpers/
    vqg_quality.py's `_owner()` for the identical reason. Importing lazily (inside this
    function body, not at module level) also avoids a circular import, since the owner
    module is what imports THIS module.
    """
    from algo.orchestration import orchestrator as _owner_mod

    return _owner_mod


class OrchestratorPhasesMixin(_Base):
    def phase_1_data_freshness(self) -> bool:
        """Thin delegation to phase1_data_freshness module.

        New version only checks: are today's prices loaded? 95%+ coverage?
        Removes all the complex grace period / hung task detection logic.
        """
        self.log_phase_start(1, "DATA FRESHNESS CHECK")
        try:
            result = _owner().run_phase1(
                self.config,
                self.run_date,
                self.dry_run,
                self.alerts,
                self.verbose,
                self.log_phase_result,
            )
        except Exception as e:
            # CRITICAL FIX (real-money-readiness audit, found 2026-09-06): an unhandled
            # exception here (e.g. psycopg2.OperationalError, or any bug inside
            # phase1_data_freshness.py/phase1_price_freshness.py/phase1_table_freshness.py)
            # used to propagate straight up to phase_executor.py's generic Exception catch,
            # which sets PhaseResult(status="error", halted=False) - never reaching any of
            # the degraded/halted/ok branches below that are the ONLY places this method
            # calls set_halt_flag(). Since phases 3/4/5/6/7/8/9 are all always_run=True and
            # Phase 5's exposure constraints don't depend on Phase 1, a Phase 1 crash left
            # the global halt flag completely untouched - Phase 8 would check
            # check_halt_flag(), see it False, and place real entry orders on data Phase 1
            # never actually validated. Mirrors the "halted" branch's own set_halt_flag
            # pattern: a crash is at least as dangerous as an explicit "halted" verdict, so
            # it must halt at least as hard, not silently skip the safety mechanism entirely.
            halt_reason = f"Phase 1 crashed: {type(e).__name__}: {e}"
            logger.error(f"[PHASE 1] {halt_reason}", exc_info=True)
            halt_set_result = self.halt_manager.set_halt_flag(halt_reason, triggered_by="phase1_data_freshness")
            if not halt_set_result:
                raise RuntimeError(
                    "[GOVERNANCE VIOLATION] Halt flag could not be set after Phase 1 crashed. "
                    "This is a critical safety failure - data freshness is unverified but we can't "
                    "stop trading. Orchestrator MUST fail. Check database connectivity (RDS and "
                    "DynamoDB) and AWS credentials."
                ) from e
            raise
        # Store result for Phase 5 to check degradation status
        self._phase1_result = result

        # Informational DynamoDB write (phase1_degraded_mode key) - separate from halt flag
        # management so a DynamoDB write failure never prevents the halt flag from being cleared.
        # Skip in LOCAL_MODE (no AWS credentials available)
        local_mode = os.getenv("LOCAL_MODE", "").lower() in ("1", "true", "yes")
        logger.info(f"[PHASE1_DYNAMODB] LOCAL_MODE={local_mode}, env={os.getenv('LOCAL_MODE')}")
        if not local_mode:
            try:
                import boto3
                from botocore.exceptions import ClientError

                dynamodb = boto3.resource("dynamodb")
                table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
                table = dynamodb.Table(table_name)
                degraded_status = result.status == "degraded"
                table.put_item(
                    Item={
                        "key": "phase1_degraded_mode",
                        "degraded": degraded_status,
                        "timestamp": _owner().datetime.now(timezone.utc).isoformat(),
                        "reason": result.error if degraded_status else None,
                        "ttl": int(time.time()) + 3600,  # 1-hour TTL
                    }
                )
            except ClientError as e:
                # Handle invalid AWS credentials gracefully.
                # DynamoDB write failures (permission denied, invalid token) don't block Phase 1.
                # This is informational only - halt flag management happens separately below.
                try:
                    error_dict = (
                        e.response.get("Error", {}) if hasattr(e, "response") and isinstance(e.response, dict) else {}
                    )
                    error_code = error_dict.get("Code", "UNKNOWN")
                    if error_code in ("UnrecognizedClientException", "AccessDenied", "AccessDeniedException"):
                        logger.info(
                            f"[PHASE1_DYNAMODB] Write skipped (invalid credentials): {error_code}. This is non-blocking."
                        )
                    else:
                        logger.warning(f"[PHASE1_DYNAMODB] Write failed ({error_code}): {e!s}")
                except Exception as validation_error:
                    logger.warning(
                        f"[PHASE1_DYNAMODB] Error parsing AWS response: {validation_error}. Original error: {e}"
                    )
            except Exception as e:
                # Catch any other boto3 errors (missing env vars, network issues, etc.)
                logger.warning(f"[PHASE1_DYNAMODB] Unexpected error during DynamoDB write: {type(e).__name__}: {e}")
        else:
            logger.debug("[LOCAL_MODE] Skipping DynamoDB write for phase1_degraded_mode")

        # Halt flag lifecycle: MUST succeed or orchestrator fails
        # Halt flag is the safety mechanism that prevents trading during data issues.
        # If we can't manage halt flags, we have no safety guarantees - must fail-fast.
        degraded_status = result.status == "degraded"
        if degraded_status:
            logger.info(f"[DEGRADED_MODE] Phase 1 returned degraded status: {result.error}")
            halt_set_result = self.halt_manager.set_halt_flag(
                f"Phase 1 degraded: {result.error}", triggered_by="phase1_data_freshness"
            )
            if not halt_set_result:
                raise RuntimeError(
                    "[GOVERNANCE VIOLATION] Halt flag could not be set despite degraded data status. "
                    "This is a critical safety failure - data may be stale but we can't stop trading. "
                    "Orchestrator MUST fail. Check database connectivity (RDS and DynamoDB) and AWS credentials."
                )
        elif result.status == "halted":
            # CRITICAL FIX (found 2026-09-06 pre-real-money audit): this branch was missing
            # entirely - "degraded" set the flag, "ok" cleared it, but Phase 1's actual most
            # common failure mode (stale RUNNING loaders, dependency-freshness validation
            # errors, stale price_daily/table data, failed readiness checks - see
            # phase1_data_freshness.py/phase1_price_freshness.py/phase1_readiness_checks.py/
            # phase1_table_freshness.py, all of which construct PhaseResult(status="halted")
            # for these cases) fell through both branches and left the global halt flag
            # completely untouched. Phase 8 checks only this global flag
            # (phase8_entry_execution.py's check_halt_flag()), and the phase-dependency graph
            # gives it no other path back to Phase 1's result - so a Phase 1 "halted" verdict
            # was entirely invisible to entry execution, which could place orders using data
            # Phase 1 had explicitly determined was too stale/unavailable to trade on. Mirrors
            # Phase 2's and Phase 9's identical set_halt_flag-on-halted pattern below.
            halt_reason = f"Phase 1 halted: {result.error}"
            logger.info(f"[PHASE 1] Setting halt flag due to halted status: {halt_reason}")
            halt_set_result = self.halt_manager.set_halt_flag(halt_reason, triggered_by="phase1_data_freshness")
            if not halt_set_result:
                raise RuntimeError(
                    "[GOVERNANCE VIOLATION] Halt flag could not be set despite halted data status. "
                    "This is a critical safety failure - data is unusable but we can't stop trading. "
                    "Orchestrator MUST fail. Check database connectivity (RDS and DynamoDB) and AWS credentials."
                )
        elif result.status == "ok":
            # BUG FOUND 2026-08-10 (live-reproduced): this used to unconditionally clear
            # the halt flag whenever Phase 1's OWN freshness check passed, regardless of
            # which phase had actually set the currently-active halt. Phase 2 (circuit
            # breaker) and Phase 9 (reconciliation governance - set at the END of a run
            # specifically to block Phase 8 from trading on the *next* run with an
            # unverified portfolio state) both persist halts through this same flag. Since
            # Phase 1 runs before Phase 8/9 in the next run, this silently erased Phase 9's
            # halt before it - or anything else - ever got a chance to re-verify the
            # underlying problem was resolved. Live-reproduced: manually set halt_flag=True
            # with an unrelated reason, ran a full orchestrator invocation, confirmed via
            # "[HALT_FLAG_CLEARED] Phase 1 verified data is fresh" that it was wiped
            # regardless of origin. Phase 1 may only clear a halt it recognizes as its own.
            current_trigger = self.halt_manager.get_halt_triggered_by()
            if current_trigger is None or current_trigger == "phase1_data_freshness":
                # If this fails (both DynamoDB and RDS unavailable), clear_halt_flag() raises RuntimeError
                # allowed_triggers repeats this same check inside clear_halt_flag() itself - defense
                # in depth, not redundant with the pre-check above (see that method's docstring).
                self.halt_manager.clear_halt_flag(
                    f"Phase 1 verified data is fresh at {_owner().datetime.now(timezone.utc).isoformat()}",
                    allowed_triggers=frozenset({None, "phase1_data_freshness"}),
                )
            else:
                logger.warning(
                    f"[PHASE 1] Data is fresh, but the active halt flag was set by '{current_trigger}', "
                    "not Phase 1's own freshness check - leaving it in place. That phase's own logic "
                    "(or explicit manual intervention) must resolve and clear it."
                )

        return not result.halted

    def phase_2_circuit_breakers(self) -> bool:
        """Thin delegation to phase2_circuit_breakers module."""
        self.log_phase_start(2, "CIRCUIT BREAKERS")
        try:
            result = _owner().run_phase2(
                self.config,
                self.run_date,
                self.dry_run,
                self.alerts,
                self.verbose,
                self.log_phase_result,
            )
        except Exception as e:
            # CRITICAL FIX (real-money-readiness audit, found 2026-09-07): same bug class
            # already fixed for Phase 1 (see phase_1_data_freshness's identical try/except,
            # "Phase 1 crashed" comment) but never applied here - and this gap is arguably
            # worse, since Phase 2 IS the circuit breaker. An unhandled exception inside
            # run_phase2() (e.g. a transient DB error while computing live drawdown) used to
            # propagate straight past the halted/else branches below - which are the ONLY
            # places this method calls set_halt_flag()/clear_halt_flag() - and hit
            # phase_executor.py's generic Exception handler instead, which records
            # PhaseResult(status="error", halted=False) without ever touching the halt flag.
            # Since phases 3/4/5/6/7/8/9 are all always_run=True, a Phase 2 crash left the
            # global halt flag exactly as it was before this run - Phase 8 would check
            # check_halt_flag(), see whatever stale value was already there, and place real
            # entry orders with this run's circuit-breaker check never actually evaluated.
            halt_reason = f"Phase 2 crashed: {type(e).__name__}: {e}"
            logger.error(f"[PHASE 2] {halt_reason}", exc_info=True)
            halt_set_result = self.halt_manager.set_halt_flag(halt_reason, triggered_by="phase2_circuit_breaker")
            if not halt_set_result:
                raise RuntimeError(
                    "[GOVERNANCE VIOLATION] Halt flag could not be set after Phase 2 crashed. "
                    "This is a critical safety failure - circuit breakers are unverified but we "
                    "can't stop trading. Orchestrator MUST fail. Check database connectivity (RDS "
                    "and DynamoDB) and AWS credentials."
                ) from e
            raise
        self._phase2_result = result
        # CRITICAL FIX: Set halt flag when circuit breaker fires so Phase 8 respects it
        # Previously only Phase 1 called set_halt_flag, leaving Phase 2 halts unheeded by later phases
        if result.halted:
            halt_reason = result.error or "Circuit breaker check failed"
            logger.info(f"[PHASE 2] Setting halt flag due to circuit breaker: {halt_reason}")
            self.halt_manager.set_halt_flag(halt_reason, triggered_by="phase2_circuit_breaker")
        else:
            # FIX 2026-08-10 (companion to halt_flag_cleared_by_unrelated_phase_fix): Phase 1
            # now refuses to auto-clear a halt it didn't set, so a phase2_circuit_breaker halt
            # that later recovers would otherwise stay set forever (Phase 2 previously only
            # ever SET this flag, never cleared it - the only thing that used to unstick it
            # was Phase 1's blanket clear, which was itself the bug). Safe to self-clear here
            # specifically: Phase 2 just freshly re-evaluated live drawdown/circuit-breaker
            # data THIS run and found it healthy, and runs before Phase 8 in this same run -
            # unlike Phase 9 (see that phase's own comment), there's no "next run" gap where
            # trading could proceed on stale reassurance. Only clears a halt it recognizes as
            # its own - never touches one set by Phase 1 or Phase 9.
            current_trigger = self.halt_manager.get_halt_triggered_by()
            if current_trigger == "phase2_circuit_breaker":
                logger.info("[PHASE 2] Circuit breaker checks now clear - clearing the halt flag it previously set.")
                self.halt_manager.clear_halt_flag(
                    "Phase 2 circuit breaker checks are clear",
                    allowed_triggers=frozenset({"phase2_circuit_breaker"}),
                )
        return not result.halted

    def phase_3_position_monitor(self) -> bool:
        """Thin delegation to phase3_position_monitor module."""
        self.log_phase_start(3, "POSITION MONITOR")
        result = _owner().run_phase3(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
        )
        self._phase3_result = result
        if not result.ok:
            if result.halted:
                # REAL-MONEY-READINESS FINDING (2026-09-10, orchestration re-audit): Phase 3
                # setting result.halted=True (position-monitor crash - see
                # phase3_position_monitor.py's PAPER MODE and live-mode crash branches) never
                # reached the shared halt flag. Phase 6 already treats Phase 3's own result as
                # informational-only and continues (documented "always_run" behavior), and
                # Phase 5/7/8 never look at Phase 3's result at all - they only check
                # self.halt_manager's shared flag. Without this call, Phase 8 could still
                # submit brand-new entry orders in the same run despite Phase 3 believing
                # position monitoring - and therefore trading - should be halted. Mirrors
                # Phase 1/2/9's identical set_halt_flag-on-halted pattern.
                halt_reason = f"Phase 3 halted: {result.error}"
                logger.critical(f"[PHASE 3] Setting halt flag due to halted status: {halt_reason}")
                halt_set_result = self.halt_manager.set_halt_flag(halt_reason, triggered_by="phase3_position_monitor")
                if not halt_set_result:
                    raise RuntimeError(
                        "[GOVERNANCE VIOLATION] Halt flag could not be set despite Phase 3 "
                        "(position monitor) halted status. This is a critical safety failure - "
                        "we can no longer safely monitor open positions but can't stop new "
                        "entries. Orchestrator MUST fail. Check database connectivity (RDS and "
                        "DynamoDB) and AWS credentials."
                    )
            return False
        # GOVERNANCE: Fail-fast on data contract violations. Phase 3 MUST provide recommendations.
        if result.data is None or "recommendations" not in result.data:
            self.log_phase_result(
                3,
                "POSITION MONITOR",
                "error",
                "Phase 3 data contract violated: missing 'recommendations' key in result",
            )
            logger.error("Phase 3 returned ok=True but missing recommendations in data contract")
            return False
        recs = result.data["recommendations"]
        if not isinstance(recs, list):
            self.log_phase_result(
                3,
                "POSITION MONITOR",
                "error",
                f"Phase 3 data contract violated: recommendations must be list, got {type(recs).__name__}",
            )
            logger.error(f"Phase 3 recommendations not a list: {type(recs)}")
            return False
        self._position_recs = recs
        return True

    def phase_5_exposure_policy(self) -> bool:
        """Thin delegation to phase5_exposure_policy module."""
        self.log_phase_start(5, "EXPOSURE POLICY ACTIONS")
        result = _owner().run_phase5(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
        )
        self._phase5_result = result
        if not result.ok:
            return False
        # GOVERNANCE: Fail-fast on data contract violations. Phase 5 MUST provide actions.
        if result.data is None or "actions" not in result.data:
            self.log_phase_result(
                5,
                "EXPOSURE POLICY ACTIONS",
                "error",
                "Phase 5 data contract violated: missing 'actions' key in result",
            )
            logger.error("Phase 5 returned ok=True but missing actions in data contract")
            return False
        actions = result.data["actions"]
        if not isinstance(actions, list):
            self.log_phase_result(
                5,
                "EXPOSURE POLICY ACTIONS",
                "error",
                f"Phase 5 data contract violated: actions must be list, got {type(actions).__name__}",
            )
            logger.error(f"Phase 5 actions not a list: {type(actions)}")
            return False
        self._exposure_constraints = result.data.get("constraints")
        self._exposure_actions = actions
        return True

    def phase_9_reconcile(self) -> bool:
        """Thin delegation to phase9_reconciliation module."""
        self.log_phase_start(9, "RECONCILIATION & SNAPSHOT")
        # No halt flag check: snapshot must always be written so circuit breakers
        # have accurate portfolio state on the next invocation.
        try:
            result = _owner().run_phase9(self.config, self.run_date, self.log_phase_result)
        except Exception as e:
            # CRITICAL FIX (real-money-readiness audit, found 2026-09-07): same bug class
            # already fixed for Phase 1/Phase 2 (see their identical try/except blocks) but
            # never applied here. An unhandled exception inside run_phase9() (broker API
            # failure, DB error mid-reconciliation) used to propagate straight past the
            # `if result.halted` branch below - the only place this method calls
            # set_halt_flag() - and hit phase_executor.py's generic Exception handler
            # instead, which never touches the halt flag. Phase 9 writes the portfolio
            # snapshot circuit breakers read on the NEXT invocation (see this method's own
            # "No halt flag check" comment above) - a crash here means that snapshot is
            # stale or missing, so the next run's Phase 2 circuit-breaker check and Phase 8
            # entry gate could both be operating on unverified portfolio state with no halt
            # flag raised to say so.
            halt_reason = f"Phase 9 crashed: {type(e).__name__}: {e}"
            logger.error(f"[PHASE 9] {halt_reason}", exc_info=True)
            halt_set_result = self.halt_manager.set_halt_flag(
                halt_reason, triggered_by="phase9_reconciliation_governance"
            )
            if not halt_set_result:
                raise RuntimeError(
                    "[GOVERNANCE VIOLATION] Halt flag could not be set after Phase 9 crashed. "
                    "This is a critical safety failure - the portfolio reconciliation snapshot "
                    "is unverified but we can't stop trading. Orchestrator MUST fail. Check "
                    "database connectivity (RDS and DynamoDB) and AWS credentials."
                ) from e
            raise
        self._phase9_result = result
        # CRITICAL FIX: mirror Phase 2's pattern. result.halted is only True for the
        # execution_mode=auto governance halt (see phase9_reconciliation.py's
        # is_governance_halt) - a real broker/DB reconciliation failure that previously never
        # reached set_halt_flag(), letting Phase 8 submit real orders on the next run despite
        # an unverified portfolio state.
        if result.halted:
            halt_reason = result.error or "Phase 9 reconciliation governance halt"
            logger.info(f"[PHASE 9] Setting halt flag due to reconciliation failure: {halt_reason}")
            self.halt_manager.set_halt_flag(halt_reason, triggered_by="phase9_reconciliation_governance")
        if "positions" in result.data:
            self.phase_results.setdefault(9, {})["open_positions"] = result.data["positions"]
        else:
            logger.warning(
                "Phase 9 reconciliation returned without positions data "
                "(broker unavailable or reconciliation failed). "
                f"Got keys: {list(result.data.keys())}"
            )
        return not result.halted

    # ---------- Executor setup (Phase 2: Phase Executor Framework) ----------

    def _setup_executor(self, skip_phases: list[int | str] | None = None) -> OrchestratorPhaseExecutor:
        """Create and configure the phase executor.

        Loads phase definitions from PhaseRegistry and wires executor methods.
        Eliminates Shotgun Surgery: adding a phase is now a single registry entry,
        not multiple method additions and orchestrator changes.

        Args:
            skip_phases: Optional list of phase numbers to skip (e.g., trading phases on non-trading days)

        Returns:
            OrchestratorPhaseExecutor ready to execute all phases.
        """
        executor = OrchestratorPhaseExecutor(
            config=self.config,
            halt_check_fn=self.halt_manager.check_halt_flag,
            skip_phases=skip_phases,
            halt_reason_fn=self.halt_manager.get_halt_reason,
        )

        # Wire phase executor functions from registry
        phase_executors: dict[int | str, Any] = {
            1: self._executor_phase_1,
            2: self._executor_phase_2,
            3: self._executor_phase_3,
            4: self._executor_phase_4,
            5: self._executor_phase_5,
            6: self._executor_phase_6,
            7: self._executor_phase_7,
            8: self._executor_phase_8,
            9: self._executor_phase_9,
        }

        # Register all phases from registry with their metadata
        for phase_entry in PhaseRegistry.get_all_phases():
            # Wire the executor function for this phase
            execute_fn = phase_executors.get(phase_entry.phase_num)
            if execute_fn is None:
                raise RuntimeError(f"No executor registered for phase {phase_entry.phase_num}")

            # Convert registry entry to PhaseDefinition for executor
            phase_def = PhaseDefinition(
                phase_num=phase_entry.phase_num,
                phase_name=phase_entry.phase_name,
                dependencies=phase_entry.dependencies,
                execute_fn=execute_fn,
                skip_if_halted=phase_entry.skip_if_halted,
                always_run=phase_entry.always_run,
            )
            executor.register_phase(phase_def)

        return executor

    def _executor_phase_1(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 1.

        CRITICAL FIX (2026-08-01): Sync positions from trades before Phase 1.
        Ensures algo_positions table stays in sync with actual trades throughout the day.
        Without this, positions go stale between midnight loader runs.
        """
        # CRITICAL: Sync positions from trades BEFORE Phase 1
        # This ensures algo_positions is fresh for Phase 3/8/9
        try:
            inserted, updated, errors, error_details = sync_positions_from_trades()
            if errors > 0:
                failed_symbols = [e["symbol"] for e in error_details]
                logger.warning(
                    f"[POSITION_SYNC] Completed with {errors} errors. "
                    f"Failed symbols: {', '.join(failed_symbols[:3])}"
                    f"{' ... and ' + str(len(failed_symbols) - 3) + ' more' if len(failed_symbols) > 3 else ''}"
                )
            else:
                logger.info(f"[POSITION_SYNC] Completed: {inserted} inserted, {updated} updated")

            # Validate position counts are sane
            if not validate_position_count():
                logger.warning("[POSITION_SYNC_VALIDATE] Position count validation failed - possible data mismatch")
                # BUG FOUND 2026-09-01 (real-money-readiness pass): this only ever logged a
                # warning - validate_position_count()'s own CRITICAL log lines (for the
                # "trades with no position" case specifically: "Positions were lost during
                # sync or entry execution") never reached a real alert channel. That case is
                # dangerous, not cosmetic: circuit_breaker.py's portfolio-risk/total-risk
                # checks read from algo_positions, not algo_trades, so a symbol missing from
                # algo_positions is invisible to risk management - its exposure silently
                # isn't counted against any limit at all, with no operator ever notified.
                # Same "computed but never delivered" bug class already found and fixed for
                # Phase 9's VaR/concentration/beta alerts (commit 5ac092eea). This runs before
                # Phase 1, so self.alerts (AlertManager) is already initialized in __init__.
                self.alerts.critical(
                    "[POSITION_SYNC_VALIDATE] Position count validation failed after sync - "
                    "algo_positions and algo_trades disagree on open symbols. If any symbol is "
                    "missing from algo_positions, its risk is NOT being counted by circuit "
                    "breaker checks. See orchestrator logs for the specific symbol list."
                )
        except RuntimeError as e:
            logger.error(f"[POSITION_SYNC] CRITICAL: {e}")
            raise

        self.phase_1_data_freshness()
        if not hasattr(self, "_phase1_result"):
            raise RuntimeError("[PHASE 1] phase_1_data_freshness() did not set _phase1_result")
        return self._phase1_result

    def _executor_phase_2(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 2."""
        self.phase_2_circuit_breakers()
        if not hasattr(self, "_phase2_result"):
            raise RuntimeError("[PHASE 2] phase_2_circuit_breakers() did not set _phase2_result")
        return self._phase2_result

    def _executor_phase_3(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 3."""
        self.phase_3_position_monitor()
        if not hasattr(self, "_phase3_result"):
            raise RuntimeError("[PHASE 3] phase_3_position_monitor() did not set _phase3_result")
        return self._phase3_result

    def _executor_phase_4(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 4: Reconciliation."""
        result = _owner().run_phase4(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
        )
        return result

    def _executor_phase_5(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 5: Exposure Policy."""
        self.phase_5_exposure_policy()
        if not hasattr(self, "_phase5_result"):
            raise RuntimeError("[PHASE 5] phase_5_exposure_policy() did not set _phase5_result")
        return self._phase5_result

    def _executor_phase_6(self, executor: Any = None, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 6: Exit Execution.

        PHASE DEPENDENCY FIX: Phase 6 has always_run=True, so it must execute even if Phase 3/5 fail.
        Falls back to database reads if phase data unavailable.

        CRITICAL: Even though Phase 6 always runs, we MUST log if dependencies are halted
        so operators understand why exit logic might be degraded.
        """
        if not executor:
            raise RuntimeError(
                "[PHASE 6] CRITICAL: Executor is None. Phase 6 requires validated data from Phases 3 and 5. "
                "This should never happen - check phase_executor.py initialization."
            )

        from algo.orchestrator.phase_data_contract import MissingPhaseDataError

        position_recs = []
        exposure_actions = []

        # Try to get Phase 3 data (position recommendations)
        # Note: Phase 6 always runs even if Phase 3 failed, but we must log degradation
        phase3_result = executor.get_result(3)
        if phase3_result and phase3_result.halted:
            logger.warning(
                f"[PHASE 6] Phase 3 halted: {phase3_result.error or 'unknown reason'}. "
                f"Phase 6 (always_run) continuing with degraded position monitoring. "
                f"Exits will proceed based on database state only."
            )

        try:
            position_recs = executor.get_phase_data_required(3, "recommendations")
        except MissingPhaseDataError as e:
            logger.warning(
                f"[PHASE 6] Phase 3 data unavailable: {e}. "
                f"Phase 6 (always_run) continuing with empty position_recs. "
                f"Exits will proceed based on database state only."
            )

        # Try to get Phase 5 data (exposure actions)
        # Note: Phase 6 always runs even if Phase 5 failed, but we must log degradation
        phase5_result = executor.get_result(5)
        if phase5_result and phase5_result.halted:
            # CRITICAL FIX: Phase 6 must ALWAYS run, even if Phase 5 (exposure policy) fails
            # Market regime data is used for NEW ENTRIES (Phase 8) not exits (Phase 6)
            # Phase 6 exits based on: stops, targets, concentration limits (not market regime)
            # Blocking Phase 6 because Phase 5 failed would prevent EXITING positions during crisis
            # which is the opposite of what we want
            halt_reason = phase5_result.error or "unknown reason"
            logger.warning(
                f"[PHASE 6] Phase 5 halted: {halt_reason}. "
                f"Phase 6 (always_run) continuing with position-monitor-only exits. "
                f"Exposure policy enforcement (entry blocking) may be degraded, but exits still run."
            )

        try:
            exposure_actions = executor.get_phase_data_required(5, "actions")
            exposure_constraints = executor.get_phase_data_required(5, "constraints")
        except MissingPhaseDataError as e:
            logger.warning(
                f"[PHASE 6] Phase 5 data unavailable: {e}. "
                f"Phase 6 (always_run) continuing with empty exposure_actions and constraints. "
                f"Exits will proceed with position-monitor-only logic."
            )
            exposure_constraints = None

        result = _owner().run_phase6(
            self.config,
            self.run_date,
            self.dry_run,
            self.alerts,
            self.verbose,
            self.log_phase_result,
            position_recs,
            exposure_actions,
            executor=executor,
            exposure_constraints=exposure_constraints,
        )
        if result.halted:
            # REAL-MONEY-READINESS FINDING (2026-09-10, orchestration re-audit): Phase 6
            # (exit execution) returns PhaseResult(halted=True) on a DB error or any
            # unexpected exception during exit/stop evaluation (see phase6_exit_execution.py's
            # DatabaseError and generic Exception handlers), but this executor wrapper only
            # ever returned that result straight to OrchestratorPhaseExecutor.execute_phase(),
            # which just logs it at CRITICAL - it never reaches self.halt_manager's shared halt
            # flag. Phase 8 only consults Phase 5's exposure_constraints (unrelated to Phase 6),
            # so it had no way of knowing exit execution had catastrophically failed - it could
            # still submit brand-new entry orders in the same run while existing positions were
            # left with unverified/unmanaged exits. Mirrors Phase 3/9's identical
            # set_halt_flag-on-halted pattern (see phase_3_position_monitor / _executor_phase_9).
            halt_reason = f"Phase 6 (exit execution) halted: {result.error}"
            logger.critical(f"[PHASE 6] Setting halt flag due to halted status: {halt_reason}")
            halt_set_result = self.halt_manager.set_halt_flag(halt_reason, triggered_by="phase6_exit_execution")
            if not halt_set_result:
                raise RuntimeError(
                    "[GOVERNANCE VIOLATION] Halt flag could not be set despite Phase 6 "
                    "(exit execution) halted status. This is a critical safety failure - exit "
                    "execution failed and we can't stop new entries from proceeding this run. "
                    "Orchestrator MUST fail. Check database connectivity (RDS and DynamoDB) and "
                    "AWS credentials."
                )
        return result

    def _executor_phase_7(self, executor: Any = None, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 7: Signal Generation.

        CRITICAL FIX (2026-08-06): If Phase 5 is unavailable (skipped/halted),
        Phase 7 now proceeds with conservative default constraints rather than
        halting. This maintains orchestration continuity while ensuring safety.
        """
        if not executor:
            raise RuntimeError(
                "[PHASE 7] CRITICAL: Executor is None. Phase 7 requires exposure constraints from Phase 5. "
                "Cannot execute signal generation without validated market exposure constraints. "
                "This should never happen - check phase_executor.py initialization."
            )

        # CRITICAL FIX: Check if Phase 5 was halted/failed, then use fallback constraints
        # instead of halting Phase 7. This allows signal generation to proceed safely
        # even when Phase 5 is skipped or fails.
        phase5_result = executor.get_result(5)

        # Use safe default constraints if Phase 5 is unavailable
        if phase5_result is None or phase5_result.halted or not phase5_result.ok:
            phase5_status = "never executed" if phase5_result is None else "halted/failed"
            logger.warning(
                f"[PHASE 7] Phase 5 {phase5_status} - proceeding with conservative default constraints "
                f"(no new entries). Signal generation will create trades, but Phase 8 will not execute them "
                f"due to halt_new_entries=True in fallback constraints."
            )
            # Use same safe defaults as Phase 5 skip data
            exposure_constraints = cast(
                ExposureConstraints,
                {
                    "tier_name": "CORRECTION",
                    "regime": "CORRECTION",
                    "risk_multiplier": 0.0,
                    "max_new_positions_today": 0,
                    "halt_new_entries": True,
                    "max_concentration_pct": 0.0,
                    "halt_reason": "Phase 5 unavailable - using conservative defaults",
                },
            )
        else:
            exposure_constraints = executor.get_phase_data_required(5, "constraints")

        result = _owner().run_phase7(
            self.run_date,
            self.dry_run,
            self.verbose,
            self.log_phase_result,
            exposure_constraints=exposure_constraints,
            check_halt_flag=self.halt_manager.check_halt_flag,
            config=self.config,
        )
        return result

    def _executor_phase_8(self, executor: Any = None, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 8: Entry Execution.

        PHASE DEPENDENCY FIX: Now passes executor so phase can fetch validated data
        from Phase 7 and 5 instead of relying on instance attributes.
        CRITICAL FIX (2026-08-06): Pass exposure_constraints parameter explicitly
        so Phase 8 can use it as fallback when executor data unavailable.
        """
        # Get Phase 5 constraints for fallback (Phase 8 normally gets via executor,
        # but also needs parameter for edge cases where executor is unavailable)
        exposure_constraints = None
        try:
            exposure_constraints = executor.get_phase_data_required(5, "constraints")
        except Exception as phase5_data_err:
            logger.debug(
                f"[PHASE 8] Could not get Phase 5 constraints from executor for parameter fallback: {phase5_data_err}"
            )
            exposure_constraints = None

        result = _owner().run_phase8(
            self.config,
            self.run_date,
            self.dry_run,
            self.verbose,
            self.log_phase_result,
            check_halt_flag=self.halt_manager.check_halt_flag,
            executor=executor,
            exposure_constraints=exposure_constraints,
            alerts=self.alerts,
        )
        return result

    def _executor_phase_9(self, **kwargs: Any) -> Any:
        """Executor wrapper for Phase 9: Final Reconciliation."""
        self.phase_9_reconcile()
        if not hasattr(self, "_phase9_result"):
            raise RuntimeError("[PHASE 9] phase_9_reconcile() did not set _phase9_result")
        return self._phase9_result
