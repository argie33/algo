#!/usr/bin/env python3
"""
Orchestrator execution history tracking.

Logs orchestrator runs to orchestrator_execution_log table so you can:
- View what happened in previous runs
- Diagnose patterns (e.g., always fails at Phase 3 on Wednesdays)
- Track when halt flags are triggered and why
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class OrchestratorExecutionTracker:
    """Logs orchestrator execution history for debugging and diagnostics."""

    def __init__(self) -> None:
        self.run_id: str | None = None
        self.run_date: Any | None = None
        self.started_at: datetime | None = None
        self.phase_results: dict[int | str, dict[str, Any]] = {}

    def set_run_context(self, run_id: str, run_date: Any) -> None:
        self.run_id = run_id
        self.run_date = run_date
        self.started_at = datetime.now(timezone.utc)

    def _ensure_table_exists(self) -> None:
        with DatabaseContext("write") as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orchestrator_execution_log (
                    id SERIAL PRIMARY KEY,
                    run_id VARCHAR(50) NOT NULL UNIQUE,
                    run_date DATE NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    overall_status VARCHAR(20) NOT NULL,
                    phase_results JSONB,
                    summary TEXT,
                    halt_reason TEXT,
                    phases_completed INTEGER,
                    phases_halted INTEGER,
                    phases_errored INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_run_date
                ON orchestrator_execution_log(run_date DESC)
            """)

    def log_phase_result(self, phase_num: int | str, name: str, status: str, summary: str) -> None:
        """Record a phase result. Called by orchestrator.log_phase_result()."""
        self.phase_results[phase_num] = {
            "phase": str(phase_num),
            "name": name,
            "status": status,
            "summary": summary,
        }

    def save_execution_log(self, overall_status: str, halt_reason: str | None = None) -> bool:
        """Save the complete execution log to database.

        Args:
            overall_status: 'success', 'halted', 'error', or 'skipped'
            halt_reason: If halted, the reason why

        Returns: True if saved successfully, False on error
        """
        if not self.run_id or not self.run_date:
            logger.warning("[EXECUTION_LOG] Cannot save: run context not set")
            return False

        try:
            self._ensure_table_exists()
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"Failed to ensure execution tracking table exists: {e}. Cannot proceed with execution logging."
            ) from e

        try:
            completed_at = datetime.now(timezone.utc)

            # Count phase outcomes. Phase implementations log via two DIFFERENT status
            # vocabularies that were never reconciled: the PhaseResult object they return uses
            # "ok"/"halted"/"error"/"degraded"/"skipped", but the log_phase_result_fn() callback
            # they call during execution (which populates self.phase_results, read here) uses
            # "success"/"halt"/"error"/"warn"/"alert"/"degraded"/"skipped" instead - phase4 in
            # particular logs its failure case as "alert", not "error". Matching only "ok"/
            # "halted"/"error" here meant phases_completed and phases_halted were silently 0 on
            # EVERY run regardless of what actually happened (confirmed live via
            # /api/algo/last-run showing "Completed successfully (0 phases)" for a run where all
            # 9 phases succeeded) - phases_errored partially worked, since "error" happens to be
            # used by both vocabularies for some phases. Recognize both vocabularies.
            phases_completed = sum(1 for r in self.phase_results.values() if r["status"] in ("ok", "success"))
            phases_halted = sum(1 for r in self.phase_results.values() if r["status"] in ("halted", "halt"))
            phases_errored = sum(1 for r in self.phase_results.values() if r["status"] in ("error", "alert"))

            # Build human-readable summary
            if overall_status == "skipped":
                summary = f"Skipped run: {halt_reason or 'unknown reason'}"
            elif overall_status == "success":
                summary = f"All {len(self.phase_results)} phases completed successfully"
            elif overall_status == "halted":
                # "phases_completed + phases_halted" is NOT the halted phase number - always-run
                # phases (3, 6, 9) execute AFTER a halt too, so e.g. phase 2 halting plus phases
                # 1/3/6/9 completing (4 completed + 1 halted) previously mislabeled this "Halted
                # at phase 5" when phase 2 is what actually halted. Report the phase(s) whose
                # own status is actually halted/halt instead of deriving a number from counts.
                halted_phase_nums = sorted(
                    (str(n) for n, r in self.phase_results.items() if r["status"] in ("halted", "halt")),
                    key=str,
                )
                phase_label = "/".join(halted_phase_nums) if halted_phase_nums else "unknown"
                summary = f"Halted at phase {phase_label}: {halt_reason or 'unknown'}"
            elif overall_status == "degraded":
                # NOT an error - e.g. every DRY-RUN reports Phase 6 as "degraded" (dry-run
                # skips real trade execution by design, see phase6_exit_execution.py). Before
                # this branch existed, "degraded" fell into the else clause below and every
                # dry-run's audit-log entry (surfaced verbatim by the dashboard/API, see
                # lambda/api/routes/algo_handlers/orchestration.py) read "Error during
                # execution: DRY-RUN: execution skipped (no real trades)" - a false alarm for
                # completely expected behavior.
                summary = f"Degraded: {halt_reason or 'unknown reason'}"
            else:
                summary = f"Error during execution: {halt_reason or 'unknown error'}"

            # Prepare phase results array (sorted by phase number)
            # Keys may be int (1, 2, 3) or str ('3a', '3b') - sort as strings to handle mixed types
            phase_results_array = [self.phase_results[n] for n in sorted(self.phase_results.keys(), key=str)]

            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO orchestrator_execution_log
                    (run_id, run_date, started_at, completed_at, overall_status, phase_results,
                     summary, halt_reason, phases_completed, phases_halted, phases_errored)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                      completed_at = EXCLUDED.completed_at,
                      overall_status = EXCLUDED.overall_status,
                      phase_results = EXCLUDED.phase_results,
                      summary = EXCLUDED.summary,
                      halt_reason = EXCLUDED.halt_reason,
                      phases_completed = EXCLUDED.phases_completed,
                      phases_halted = EXCLUDED.phases_halted,
                      phases_errored = EXCLUDED.phases_errored
                    """,
                    (
                        self.run_id,
                        self.run_date,
                        self.started_at,
                        completed_at,
                        overall_status,
                        json.dumps(phase_results_array),
                        summary,
                        halt_reason or "",
                        phases_completed,
                        phases_halted,
                        phases_errored,
                    ),
                )
            logger.info(f"[EXECUTION_LOG] Saved run {self.run_id}: {overall_status}")
            return True
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e


# Global instance (accessible from orchestrator)
_tracker: OrchestratorExecutionTracker | None = None


def get_tracker() -> OrchestratorExecutionTracker:
    global _tracker
    if _tracker is None:
        _tracker = OrchestratorExecutionTracker()
    return _tracker


def reset_tracker() -> None:
    """Reset the tracker (mainly for testing)."""
    global _tracker
    _tracker = None
