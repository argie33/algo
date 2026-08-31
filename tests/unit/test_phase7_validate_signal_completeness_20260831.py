"""Coverage test for algo/orchestrator/phase7_signal_generation.py's
_validate_signal_completeness() - found 2026-08-31 via the same objective coverage-analysis pass
as commits 5b4ae35ce/8e3479e5d/d242f84aa/79ed3b3/8cc21ce70 to have zero dedicated tests despite
being a deliberate fail-loud data-integrity gate. Its own docstring documents the design intent:
"CONSISTENCY FIX #2: Now FAILS if ANY signals are incomplete (not silent filtering)... This
prevents silent data loss from propagating downstream" - a regression here (e.g. reverting to
silent filtering) would reintroduce exactly the bug class this function was built to close.
"""

from typing import Any

import pytest

from algo.orchestrator.phase7_signal_generation import (
    _REQUIRED_SIGNAL_FIELDS,
    _validate_signal_completeness,
)


def _complete_signal(symbol: str = "AAPL", **overrides: Any) -> dict[str, Any]:
    signal: dict[str, Any] = dict.fromkeys(_REQUIRED_SIGNAL_FIELDS, 1.0)
    signal["symbol"] = symbol
    signal["signal_date"] = "2026-01-15"
    signal["base_quality"] = "good"
    signal.update(overrides)
    return signal


class TestValidateSignalCompleteness:
    def test_empty_list_returns_empty_with_zero_incomplete(self):
        complete, incomplete_count = _validate_signal_completeness([], source="test")
        assert complete == []
        assert incomplete_count == 0

    def test_all_complete_signals_pass_through_unchanged(self):
        signals = [_complete_signal("AAPL"), _complete_signal("MSFT")]
        complete, incomplete_count = _validate_signal_completeness(signals, source="test")
        assert len(complete) == 2
        assert incomplete_count == 0

    def test_raises_on_missing_symbol(self):
        signal = _complete_signal()
        del signal["symbol"]
        with pytest.raises(ValueError, match="missing symbol"):
            _validate_signal_completeness([signal], source="test")

    def test_raises_on_empty_string_symbol(self):
        signal = _complete_signal(symbol="")
        with pytest.raises(ValueError, match="missing symbol"):
            _validate_signal_completeness([signal], source="test")

    def test_raises_fail_loud_not_silent_filter_on_one_incomplete_signal(self):
        """The documented design intent: even ONE incomplete signal among many complete ones
        must raise, not silently drop just that one and let the batch proceed."""
        good = _complete_signal("AAPL")
        bad = _complete_signal("MSFT")
        del bad["entry_price"]
        with pytest.raises(ValueError, match="Cannot proceed with incomplete signals"):
            _validate_signal_completeness([good, bad], source="test")

    def test_error_message_reports_correct_counts(self):
        good1 = _complete_signal("AAPL")
        good2 = _complete_signal("MSFT")
        bad = _complete_signal("GOOG")
        del bad["close"]
        with pytest.raises(ValueError, match=r"Incomplete count: 1, Complete count: 2"):
            _validate_signal_completeness([good1, good2, bad], source="test")

    @pytest.mark.parametrize("missing_field", sorted(_REQUIRED_SIGNAL_FIELDS.keys() - {"symbol"}))
    def test_raises_when_any_single_required_field_is_none(self, missing_field):
        signal = _complete_signal()
        signal[missing_field] = None
        with pytest.raises(ValueError, match="Cannot proceed with incomplete signals"):
            _validate_signal_completeness([signal], source="test")

    @pytest.mark.parametrize("missing_field", sorted(_REQUIRED_SIGNAL_FIELDS.keys() - {"symbol"}))
    def test_raises_when_any_single_required_field_is_absent_entirely(self, missing_field):
        signal = _complete_signal()
        del signal[missing_field]
        with pytest.raises(ValueError, match="Cannot proceed with incomplete signals"):
            _validate_signal_completeness([signal], source="test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
