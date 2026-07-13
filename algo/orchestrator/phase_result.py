#!/usr/bin/env python3

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PhaseResult:
    """Standardized result envelope every orchestrator phase returns."""

    phase_num: int | str | None = None
    phase_name: str | None = None
    status: str | None = None  # 'ok' | 'halted' | 'degraded' | 'skipped'
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
        """Initialize phase result, accepting both naming conventions."""
        self.phase_num = phase_num or phase_number
        self.phase_name = phase_name
        self.status = status
        self.data = data if data is not None else {}
        self.halted = is_error if is_error is not None else halted
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
        return self.status == "ok"
