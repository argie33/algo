#!/usr/bin/env python3

import logging
from dataclasses import dataclass, field
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class PhaseResultData(TypedDict, total=False):
    """Typed schema for phase result data field. All fields optional (each phase defines its own contract)."""

    summary: str | None
    status: str | None
    reason: str | None
    error: str | None
    halted: bool
    skipped: bool
    data_unavailable: bool


@dataclass
class PhaseResult:
    """Standardized result envelope every orchestrator phase returns."""

    phase_num: int | str | None = None
    phase_name: str | None = None
    status: str | None = None  # 'ok' | 'halted' | 'degraded' | 'skipped' | 'blocked'
    data: dict[str, Any] = field(default_factory=dict)
    halted: bool = False
    error: str | None = None
    dependencies: list[int | str] = field(default_factory=list)

    def __init__(
        self,
        phase_num: int | str | None = None,
        phase_name: str | None = None,
        status: str | None = None,
        data: dict[str, Any] | None = None,
        halted: bool = False,
        error: str | None = None,
        dependencies: list[int | str] | None = None,
        # Accept alternate field names for backwards compatibility
        phase_number: int | str | None = None,
        is_error: bool | None = None,
    ) -> None:
        """Initialize phase result, accepting both naming conventions.

        NOTE: is_error parameter is deprecated. Use halted= instead.
        is_error and halted are SEMANTICALLY DISTINCT:
        - is_error: an error occurred in phase execution
        - halted: trading was halted (may occur with or without error)
        The is_error parameter is IGNORED; only halted parameter affects behavior.
        """
        self.phase_num = phase_num or phase_number
        # Auto-populate canonical phase name from registry if not provided
        if phase_name is None and self.phase_num is not None:
            try:
                from algo.orchestrator.phase_registry import PhaseRegistry

                self.phase_name = PhaseRegistry.get_phase_name(self.phase_num)
            except ImportError as e:
                # Import failures indicate corrupted/missing phase_registry module
                logger.error(
                    f"[PHASE RESULT] Failed to import PhaseRegistry: {e}. "
                    f"Phase {self.phase_num} name lookup failed. Check orchestrator code integrity."
                )
                self.phase_name = phase_name
            except KeyError as e:
                # Phase number not found in registry - indicates invalid phase number or registry misconfiguration
                logger.error(
                    f"[PHASE RESULT] Phase {self.phase_num} not found in PhaseRegistry: {e}. "
                    f"Check phase_num is valid and registry is up-to-date."
                )
                self.phase_name = phase_name
            except Exception as e:
                # Unexpected error - log with full traceback
                logger.error(
                    f"[PHASE RESULT] Unexpected error looking up phase name for {self.phase_num}: {e}", exc_info=True
                )
                self.phase_name = phase_name
        else:
            self.phase_name = phase_name
        self.status = status
        self.data = data if data is not None else {}
        self.halted = halted
        self.error = error
        self.dependencies = dependencies if dependencies is not None else []

    # Support accessing phase_number as an alias for phase_num
    @property
    def phase_number(self) -> int | str | None:
        """Backwards compatibility: phase_number is an alias for phase_num."""
        return self.phase_num

    @phase_number.setter
    def phase_number(self, value: int | str) -> None:
        """Backwards compatibility: set phase_num via phase_number."""
        self.phase_num = value

    # Support accessing is_error as an alias for halted
    @property
    def is_error(self) -> bool:
        """Backwards compatibility: is_error is an alias for halted."""
        return self.halted

    @is_error.setter
    def is_error(self, value: bool) -> None:
        """Backwards compatibility: set halted via is_error."""
        self.halted = value

    @property
    def ok(self) -> bool:
        # "ok", "degraded", "skipped", and "blocked" are successful states
        # "degraded" means the phase worked but produced suboptimal results
        # "skipped" means phase intentionally didn't run (due to upstream halt)
        # "blocked" means a safety guard prevented execution (guard working as designed)
        # Only "error", "halted", "fail" are actual failures
        return self.status in ("ok", "degraded", "skipped", "blocked")
