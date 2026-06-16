#!/usr/bin/env python3

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union


@dataclass
class PhaseResult:
    """Standardized result envelope every orchestrator phase returns."""

    phase_num: Union[int, str]
    phase_name: str
    status: str  # 'ok' | 'halted' | 'degraded' | 'skipped'
    data: Dict[str, Any] = field(default_factory=dict)
    halted: bool = False
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        """Returns True if phase completed successfully."""
        return self.status == "ok"
