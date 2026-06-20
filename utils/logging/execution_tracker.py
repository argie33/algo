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
from typing import Any, Dict, Optional, Union

from utils.db import DatabaseContext


logger = logging.getLogger(__name__)


class OrchestratorExecutionTracker:
    """Logs orchestrator execution history for debugging and diagnostics."""

    def __init__(self) -> None:
        self.run_id: Optional[str] = None
        self.run_date: Optional[Any] = None
        self.started_at: Optional[datetime] = None
        self.phase_results: Dict[Union[int, str], Dict[str, Any]] = {}

    def set_run_context(self, run_id: str, run_date: Any) -> None:
        """Set the run context (called at orchestrator startup)."""
        self.run_id = run_id
        self.run_date = run_date
        self.started_at = datetime.now(timezone.utc)

    def _ensure_table_exists(self) -> None:
        """Create orchestrator_execution_log if it doesn't exist (self-healing)."""
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

    def log_phase_result(
        self, phase_num: Union[int, str], name: str, status: str, summary: str
    ) -> None:
        """Record a phase result. Called by orchestrator.log_phase_result()."""
        self.phase_results[phase_num] = {
            "phase": str(phase_num),
            "name": name,
            "status": status,
            "summary": summary,
        }

    def save_execution_log(
        self, overall_status: str, halt_reason: Optional[str] = None
    ) -> bool:
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
        except Exception as e:
            raise RuntimeError(
                f"Failed to ensure execution tracking table exists: {e}. "
                "Cannot proceed with execution logging."
            ) from e

        try:
            completed_at = datetime.now(timezone.utc)

            # Count phase outcomes
            phases_completed = sum(
                1 for r in self.phase_results.values() if r["status"] == "success"
            )
            phases_halted = sum(
                1 for r in self.phase_results.values() if r["status"] == "halt"
            )
            phases_errored = sum(
                1 for r in self.phase_results.values() if r["status"] == "error"
            )

            # Build human-readable summary
            if overall_status == "skipped":
                summary = f"Skipped run: {halt_reason or 'unknown reason'}"
            elif overall_status == "success":
                summary = f"All {len(self.phase_results)} phases completed successfully"
            elif overall_status == "halted":
                summary = f"Halted at phase {phases_completed + phases_halted}: {halt_reason or 'unknown'}"
            else:
                summary = f"Error during execution: {halt_reason or 'unknown error'}"

            # Prepare phase results array (sorted by phase number)
            # Keys may be int (1, 2, 3) or str ('3a', '3b') — sort as strings to handle mixed types
            phase_results_array = [
                self.phase_results[n]
                for n in sorted(self.phase_results.keys(), key=str)
            ]

            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO orchestrator_execution_log
                    (run_id, run_date, started_at, completed_at, overall_status, phase_results,
                     summary, halt_reason, phases_completed, phases_halted, phases_errored)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
_tracker: Optional[OrchestratorExecutionTracker] = None


def get_tracker() -> OrchestratorExecutionTracker:
    """Get or create the global execution tracker."""
    global _tracker
    if _tracker is None:
        _tracker = OrchestratorExecutionTracker()
    return _tracker


def reset_tracker() -> None:
    """Reset the tracker (mainly for testing)."""
    global _tracker
    _tracker = None
