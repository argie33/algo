#!/usr/bin/env python3

from algo.signals.signal_base import SignalBase
from algo.signals.signal_trend import SignalTrendMixin
from algo.signals.signal_patterns import SignalPatternsMixin
from algo.signals.signal_momentum import SignalMomentumMixin
from algo.signals.signal_options import SignalOptionsMixin


class SignalComputer(SignalBase, SignalTrendMixin, SignalPatternsMixin,
                     SignalMomentumMixin, SignalOptionsMixin):
    """All technical signals via mixin composition."""
    pass
