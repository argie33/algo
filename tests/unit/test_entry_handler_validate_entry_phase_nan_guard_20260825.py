"""Regression test for the 2026-08-25 fix (goal session, entry-validation audit):
EntryHandler._validate_entry_phase() was missing the same NaN-comparison-guard already
applied 8+ times elsewhere in executor_entry_handler.py (e.g. _upsert_position_record's
identical guard on stop_loss_price). A NaN/Infinite entry_price or stop_loss_price would
raise decimal.InvalidOperation on the `stop_dec <= 0` comparison instead of this function's
own documented (bool, str, dict) contract.

Unlike _upsert_position_record's instance of this same gap (caught by a broad
`except Exception` at that call site), execute_entry's own top-level `except Exception`
re-raises after logging rather than swallowing it - so this exception would propagate to
Phase 8's per-signal loop, which does not catch ArithmeticError/InvalidOperation, aborting
entry execution for every OTHER qualified signal that day, not just this one bad one. Same
bug class, same fix, as trade_validator.py's identical NaN-comparison gap fixed the same
session.
"""

from decimal import Decimal
from unittest.mock import MagicMock

from algo.trading.executor_entry_handler import EntryHandler


def _make_handler():
    return EntryHandler(MagicMock())


class TestValidateEntryPhaseNanGuard:
    def test_nan_stop_loss_price_returns_clean_failure_not_raises(self):
        handler = _make_handler()
        valid, error_msg, details = handler._validate_entry_phase(
            cur=MagicMock(),
            symbol="TESTSYM",
            signal_date=None,
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("NaN"),
        )
        assert valid is False
        assert error_msg is not None
        assert details == {}

    def test_infinite_entry_price_returns_clean_failure_not_raises(self):
        handler = _make_handler()
        valid, error_msg, details = handler._validate_entry_phase(
            cur=MagicMock(),
            symbol="TESTSYM",
            signal_date=None,
            entry_price=Decimal("Infinity"),
            stop_loss_price=Decimal("90"),
        )
        assert valid is False
        assert error_msg is not None
        assert details == {}

    def test_valid_inputs_still_reach_downstream_validation(self):
        """Sanity check: the fix must not break the normal (finite, valid) path - a valid
        stop < entry pair must still fall through to _validate_entry_conditions()."""
        handler = _make_handler()
        handler.context._validate_entry_conditions.return_value = (True, "", {})

        valid, error_msg, details = handler._validate_entry_phase(
            cur=MagicMock(),
            symbol="TESTSYM",
            signal_date=None,
            entry_price=Decimal("100"),
            stop_loss_price=Decimal("90"),
        )

        assert valid is True
        handler.context._validate_entry_conditions.assert_called_once()
