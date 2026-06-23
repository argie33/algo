#!/usr/bin/env python3

from typing import Any

from algo.signals.signal_base import SignalBase
from algo.signals.signal_momentum import SignalMomentumMixin
from algo.signals.signal_options import SignalOptionsMixin
from algo.signals.signal_patterns import SignalPatternsMixin
from algo.signals.signal_trend import SignalTrendMixin


class SignalComputer(
    SignalBase,
    SignalTrendMixin,
    SignalPatternsMixin,
    SignalMomentumMixin,
    SignalOptionsMixin,
):
    """All technical signals via mixin composition."""

    def generate(self, symbol: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Generate combined signal (placeholder for mixin composition)."""
        return None
