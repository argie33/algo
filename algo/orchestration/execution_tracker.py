#!/usr/bin/env python3
"""Execution Tracker - Phase logging and execution tracking with event publishing."""

import logging
from datetime import date as _date
from typing import Any

from utils.logging import get_tracker

logger = logging.getLogger(__name__)


class ExecutionTracker:
    """Tracks orchestration execution and phase completion."""

    def __init__(self, run_id: str = "test", run_date: _date = None) -> None:
        """Initialize execution tracker."""
        if run_date is None:
            run_date = _date.today()
        self.run_id = run_id
        self.run_date = run_date
        self.phase_results: dict[int | str, Any] = {}
        self.execution_tracker = get_tracker()
        self.execution_tracker.set_run_context(self.run_id, self.run_date)

    def log_phase_start(self, phase_num: int | str, name: str) -> None:
        """Log phase start. Publishes phase_started event."""
        logger.info(f"[PHASE {phase_num}] {name} starting...")

        # Publish event for subscribers (dashboard, monitoring, etc)
        try:
            from algo.orchestration.phase_event_hub import (
                PhaseStartedEvent,
                get_event_hub,
            )

            hub = get_event_hub()
            hub.publish(PhaseStartedEvent(phase_num, name))
        except Exception as e:
            # CRITICAL: Phase event publishing failure disables monitoring/dashboard tracking
            raise RuntimeError(
                f"[EXECUTION_TRACKER CRITICAL] Failed to publish phase_started event for phase {phase_num}: {e}. "
                f"Dashboard and monitoring systems cannot track phase execution. "
                f"Orchestration event hub required for operational visibility. Check event hub service."
            ) from e

    def log_phase_result(self, phase_num: int | str, name: str, status: str = "OK", summary: str = "") -> None:
        """Log phase result. Publishes phase_completed event."""
        self.phase_results[phase_num] = {
            "phase": name,
            "status": status,
            "summary": summary,
        }
        if status == "OK":
            logger.info(f"[PHASE {phase_num}] {name} completed successfully")
        elif status == "FAILED":
            logger.error(f"[PHASE {phase_num}] {name} FAILED: {summary}")
        self.execution_tracker.log_phase_result(phase_num, name, status, summary)

        # Publish event for subscribers (dashboard, monitoring, etc)
        try:
            from algo.orchestration.phase_event_hub import (
                PhaseCompletedEvent,
                PhaseStatus,
                get_event_hub,
            )

            hub = get_event_hub()
            phase_status = (
                PhaseStatus.SUCCESS
                if status == "OK"
                else (
                    PhaseStatus(status.lower())
                    if status.upper() in [s.name for s in PhaseStatus]
                    else PhaseStatus.DEGRADED
                )
            )
            hub.publish(PhaseCompletedEvent(phase_num, name, phase_status, summary))
        except Exception as e:
            # CRITICAL: Phase event publishing failure disables monitoring/dashboard tracking
            raise RuntimeError(
                f"[EXECUTION_TRACKER CRITICAL] Failed to publish phase_completed event for phase {phase_num}: {e}. "
                f"Dashboard and monitoring systems cannot track phase completion. "
                f"Orchestration event hub required for operational visibility. Check event hub service."
            ) from e

    def get_phase_results(self) -> dict[int | str, Any]:
        """Get phase results."""
        return self.phase_results.copy()
