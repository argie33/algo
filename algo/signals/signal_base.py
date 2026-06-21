#!/usr/bin/env python3
"""Signal Base - Common interface for all signal types."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class SignalBase(ABC):
    """Abstract base class for all signal types (momentum, patterns, options, swing)."""

    def __init__(self, config: Any) -> None:
        """Initialize signal with config."""
        self.config = config
        self.signal_type = self.__class__.__name__

    @abstractmethod
    def generate(self, symbol: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Generate signal for given symbol and data."""
        ...

    def format_signal(self, symbol: str, strength: float, reason: str) -> dict[str, Any]:
        """Standard signal formatting."""
        return {
            "symbol": symbol,
            "signal_type": self.signal_type,
            "strength": max(0, min(100, strength)),
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }
