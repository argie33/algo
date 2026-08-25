"""Regression test: a NaN/Infinity entry_price/stop_loss_price/shares must be rejected as a
clean validation failure, not raise decimal.InvalidOperation uncaught.

BUG FOUND 2026-08-11: validate_entry_preconditions() converts its float inputs to Decimal via
`Decimal(str(x))`, then compares with `<= 0`. A NaN float becomes a NaN Decimal, and unlike
float NaN (whose comparisons silently return False), a NaN Decimal RAISES
decimal.InvalidOperation on ordering comparisons - this function's own documented contract
("Returns: (valid: bool, error_message: str|None, ...)") was silently broken for any
NaN/Infinity-tainted input. Worse: phase8_entry_execution.py's per-signal loop only catches
(RuntimeError, ValueError, TypeError, AttributeError, IndexError, psycopg2.Error,
DatabaseError) around each signal - decimal.InvalidOperation (an ArithmeticError) isn't in
that list, so a single symbol with a NaN price would propagate out of the per-signal loop
entirely, aborting entry execution for every OTHER qualified signal that day, not just the
bad one. Same bug class already found and fixed in position_sizer.py's
calculate_position_size() (2026-08-10) - this is the sibling gap in the entry-validation path.
"""

from decimal import Decimal

from algo.trading.trade_validator import TradeValidator


def _make_validator():
    config = {
        "t1_target_r_multiple": 2.0,
        "t2_target_r_multiple": 3.0,
        "t3_target_r_multiple": 4.0,
        "max_reentries_per_name": 3,
        "min_days_before_reentry_same_symbol": 8,
    }
    return TradeValidator(config)


class TestNanEntryPreconditionsFailsClean:
    def test_nan_entry_price_returns_clean_failure_not_raises(self):
        validator = _make_validator()
        valid, error_msg, result = validator.validate_entry_preconditions(
            symbol="TESTSYM",
            entry_price=float("nan"),
            stop_loss_price=90.0,
            shares=10,
            portfolio_value=Decimal("100000"),
        )
        assert valid is False
        assert error_msg is not None
        assert result == {}

    def test_nan_stop_loss_price_returns_clean_failure_not_raises(self):
        validator = _make_validator()
        valid, error_msg, result = validator.validate_entry_preconditions(
            symbol="TESTSYM",
            entry_price=100.0,
            stop_loss_price=float("nan"),
            shares=10,
            portfolio_value=Decimal("100000"),
        )
        assert valid is False
        assert error_msg is not None
        assert result == {}

    def test_infinite_shares_returns_clean_failure_not_raises(self):
        validator = _make_validator()
        valid, error_msg, result = validator.validate_entry_preconditions(
            symbol="TESTSYM",
            entry_price=100.0,
            stop_loss_price=90.0,
            shares=float("inf"),
            portfolio_value=Decimal("100000"),
        )
        assert valid is False
        assert error_msg is not None
        assert result == {}

    def test_valid_inputs_still_pass(self):
        """Sanity check: the fix must not break the normal (finite, valid) path."""
        validator = _make_validator()
        valid, error_msg, result = validator.validate_entry_preconditions(
            symbol="TESTSYM",
            entry_price=100.0,
            stop_loss_price=90.0,
            shares=10,
            portfolio_value=Decimal("100000"),
        )
        assert valid is True
        assert error_msg is None


class TestNanPortfolioValueFailsClean:
    """Regression test for the 2026-08-25 fix: portfolio_value was excluded from the
    finiteness check entry_price/stop_loss_price/shares already get above - a float NaN is
    truthy (`not float("nan")` is False) and `float("nan") <= 0` is always False (NaN
    comparisons never trip in Python), so the `if not portfolio_value or portfolio_value <=
    0:` guard would NOT have caught a NaN portfolio_value - same NaN-comparison-guard bug
    class as entry_price/stop_loss_price/shares, just one field that had been missed."""

    def test_nan_portfolio_value_returns_clean_failure_not_silently_passes(self):
        validator = _make_validator()
        valid, error_msg, result = validator.validate_entry_preconditions(
            symbol="TESTSYM",
            entry_price=100.0,
            stop_loss_price=90.0,
            shares=10,
            portfolio_value=float("nan"),
        )
        assert valid is False
        assert error_msg is not None
        assert result == {}

    def test_infinite_portfolio_value_returns_clean_failure(self):
        validator = _make_validator()
        valid, error_msg, result = validator.validate_entry_preconditions(
            symbol="TESTSYM",
            entry_price=100.0,
            stop_loss_price=90.0,
            shares=10,
            portfolio_value=float("inf"),
        )
        assert valid is False
        assert error_msg is not None
        assert result == {}

    def test_none_portfolio_value_still_returns_its_own_clean_failure(self):
        """Sanity check: None must still hit the existing 'portfolio value unavailable'
        message (a real, expected case), not the new finiteness check's error."""
        validator = _make_validator()
        valid, error_msg, result = validator.validate_entry_preconditions(
            symbol="TESTSYM",
            entry_price=100.0,
            stop_loss_price=90.0,
            shares=10,
            portfolio_value=None,
        )
        assert valid is False
        assert error_msg is not None
        assert "unavailable" in error_msg.lower()
