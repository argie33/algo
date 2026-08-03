"""Regression: _validate_entry_conditions() discarded check_reentry_rules()'s computed
reentry_count on the success path, and _insert_trade_record() wrote a hardcoded literal 0
for every trade regardless. That made max_reentries_per_name permanently inert - every
re-entry read back reentry_count=0 the next time a symbol stopped out again, so
`prior_reentry_count + 1 >= max_reentries_per_name` could never exceed 1, no matter how
many times the symbol actually re-entered and stopped out.

Fix: _validate_entry_conditions() now captures check_reentry_rules()'s 3rd tuple element
directly and returns it via error_details={"reentry_count": N} on the success path;
_execute_entry_txn -> _record_entry_phase -> TradeInsertionRequest.reentry_count carries
it through to the actual INSERT.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from algo.trading.executor import TradeExecutor


def _fake_executor(reentry_count: int) -> SimpleNamespace:
    """A minimal stand-in for `self` inside _validate_entry_conditions - the method only
    touches self.validator and self._process_validation_result (stateless), so a real
    TradeExecutor (which needs DB/broker config) isn't required."""
    validator = MagicMock()
    validator.check_idempotent_duplicate.return_value = (False, None, None)
    validator.check_open_position_in_symbol.return_value = (False, None)
    validator.check_signal_fingerprint_duplicate.return_value = (False, None, None)
    validator.check_pending_trades.return_value = (False, None, 0)
    validator.check_reentry_rules.return_value = (True, None, reentry_count)
    fake_self = SimpleNamespace(validator=validator)
    fake_self._process_validation_result = TradeExecutor._process_validation_result.__get__(fake_self)
    return fake_self


def test_reentry_count_is_returned_via_error_details_on_success():
    fake_self = _fake_executor(reentry_count=2)

    is_valid, error_msg, error_details = TradeExecutor._validate_entry_conditions(
        fake_self, cur=MagicMock(), symbol="AAPL", signal_date=None, entry_price=100, stop_loss_price=95
    )

    assert is_valid is True
    assert error_details == {"reentry_count": 2}


def test_zero_reentry_count_when_no_prior_stopout():
    fake_self = _fake_executor(reentry_count=0)

    is_valid, error_msg, error_details = TradeExecutor._validate_entry_conditions(
        fake_self, cur=MagicMock(), symbol="AAPL", signal_date=None, entry_price=100, stop_loss_price=95
    )

    assert is_valid is True
    assert error_details == {"reentry_count": 0}
