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
    """All technical signals via mixin composition.

    Signal detection is provided via mixin methods:
    - base_detection(): Base pattern detection (Minervini)
    - vcp_detection(): Volatility Contraction Pattern
    - pivot_breakout(): Pivot point breakout
    - power_trend(): Power trend detection
    - mansfield_rs(): Relative strength ranking

    Use SignalAPI (signals/signal_api.py) for the public interface.
    """

    def generate(self, symbol: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """DEPRECATED: Use specific signal detection methods instead.

        This method was a placeholder for mixin composition. Callers should use
        the specific detection methods (base_detection, vcp_detection, etc.)
        or SignalAPI for the public interface.

        Raises:
            NotImplementedError: This method is not implemented. Use specific signal methods instead.
        """
        raise NotImplementedError(
            "SignalComputer.generate() is not implemented. "
            "Use specific signal detection methods instead: "
            "base_detection(), vcp_detection(), pivot_breakout(), power_trend(), or mansfield_rs(). "
            "For public interface, use SignalAPI (signals/signal_api.py)."
        )
