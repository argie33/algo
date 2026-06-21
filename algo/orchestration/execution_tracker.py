#!/usr/bin/env python3
"""Execution Tracker - Phase logging and execution tracking."""

import logging
from datetime import date as _date
from typing import Any

from utils.logging import get_tracker


logger = logging.getLogger(__name__)

class ExecutionTracker:
    """Tracks orchestration execution and phase completion."""

    def __init__(self, run_id: str, run_date: _date) -> None:
        """Initialize execution tracker."""
        self.run_id = run_id
        self.run_date = run_date
        self.phase_results: dict[int | str, Any] = {}
        self.execution_tracker = get_tracker()
        self.execution_tracker.set_run_context(self.run_id, self.run_date)

    def log_phase_start(self, phase_num: int | str, name: str) -> None:
        """Log phase start."""
        logger.info(f"[PHASE {phase_num}] {name} starting...")
        self.execution_tracker.start_phase(phase_num, name)

    def log_phase_result(self, phase_num: int | str, name: str, status: str = "OK", summary: str = "") -> None:
        """Log phase result."""
        self.phase_results[phase_num] = {"phase": name, "status": status, "summary": summary}
        if status == "OK":
            logger.info(f"[PHASE {phase_num}] {name} completed successfully")
        elif status == "FAILED":
            logger.error(f"[PHASE {phase_num}] {name} FAILED: {summary}")
        self.execution_tracker.record_phase_result(phase_num, status, summary)

    def get_phase_results(self) -> dict[int | str, Any]:
        """Get phase results."""
        return self.phase_results.copy()
