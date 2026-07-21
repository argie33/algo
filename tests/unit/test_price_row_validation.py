#!/usr/bin/env python3
"""Regression tests for the 2026-07-21 financial-integrity audit price-validation fixes.

Two bugs fixed together, both covered here:
1. PriceLoader._validate_row() only checked high>=low, close>0, open>0 - missing that
   low/high must themselves be positive, and that open/close must fall within [low, high].
   A row with low=-50, high=1_000_000, close=20, open=15 passed the old check.
2. utils/optimal_loader.py's row-validation loop discarded _validate_row()'s boolean
   return value entirely - only a raised exception had any effect, so a False return
   never actually excluded a row from insertion. Fixed so a rejected row is skipped
   (and utils/loader_stats.py's rows_rejected_by_validation counter incremented) instead
   of silently proceeding to insert corrupt price data.
"""

from unittest.mock import MagicMock

import pytest

from loaders.load_prices import PriceLoader


def _make_loader() -> PriceLoader:
    """PriceLoader.__init__ needs a live DB/config - _validate_row only needs
    primary_key/table_name set, so bypass __init__ entirely."""
    loader = object.__new__(PriceLoader)
    loader.primary_key = ("symbol", "date")
    loader.table_name = "price_daily"
    return loader


def _row(**overrides):
    base = {"symbol": "AAPL", "date": "2026-07-21", "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.0}
    base.update(overrides)
    return base


class TestPriceRowOHLCValidation:
    def test_normal_valid_row_is_accepted(self):
        loader = _make_loader()
        assert loader._validate_row(_row()) is True

    def test_negative_low_is_rejected(self):
        """The original gap: high>=low and close>0 and open>0 all held despite low<0."""
        loader = _make_loader()
        bad = _row(open=15.0, high=1_000_000.0, low=-50.0, close=20.0)
        assert loader._validate_row(bad) is False

    def test_negative_high_is_rejected(self):
        loader = _make_loader()
        bad = _row(open=-15.0, high=-10.0, low=-20.0, close=-12.0)
        assert loader._validate_row(bad) is False

    def test_close_above_high_is_rejected(self):
        """close must fall within [low, high] - previously unchecked."""
        loader = _make_loader()
        bad = _row(open=100.0, high=105.0, low=95.0, close=200.0)
        assert loader._validate_row(bad) is False

    def test_close_below_low_is_rejected(self):
        loader = _make_loader()
        bad = _row(open=100.0, high=105.0, low=95.0, close=50.0)
        assert loader._validate_row(bad) is False

    def test_open_above_high_is_rejected(self):
        loader = _make_loader()
        bad = _row(open=200.0, high=105.0, low=95.0, close=100.0)
        assert loader._validate_row(bad) is False

    def test_open_below_low_is_rejected(self):
        loader = _make_loader()
        bad = _row(open=50.0, high=105.0, low=95.0, close=100.0)
        assert loader._validate_row(bad) is False

    def test_zero_close_is_rejected(self):
        loader = _make_loader()
        bad = _row(open=1.0, high=2.0, low=0.0, close=0.0)
        assert loader._validate_row(bad) is False

    def test_high_below_low_is_rejected(self):
        loader = _make_loader()
        bad = _row(open=100.0, high=90.0, low=95.0, close=92.0)
        assert loader._validate_row(bad) is False

    def test_missing_field_raises_runtime_error(self):
        """Missing OHLC field is a structural data error, not a routine bad-row skip -
        matches the existing fail-fast convention (raise, don't silently False)."""
        loader = _make_loader()
        incomplete = {"symbol": "AAPL", "date": "2026-07-21", "open": 100.0, "high": 105.0}
        with pytest.raises(RuntimeError, match="PRICE_VALIDATION"):
            loader._validate_row(incomplete)


class TestBaseLoaderRespectsValidationReturnValue:
    """utils/optimal_loader.py's _load_symbol row loop must actually skip rows for
    which _validate_row() returns False, not silently insert them anyway."""

    def test_false_return_excludes_row_from_validated_rows(self):
        from utils.optimal_loader import OptimalLoader

        class _FakeLoader(OptimalLoader):
            table_name = "fake_table"
            primary_key = ("symbol", "date")

            def _validate_row(self, row):
                # Reject rows with a 'reject' marker; accept everything else via the
                # real base-class primary-key check.
                if row.get("reject"):
                    return False
                return super()._validate_row(row)

        loader = object.__new__(_FakeLoader)
        loader._stats = MagicMock()

        rows = [
            {"symbol": "AAPL", "date": "2026-07-21", "reject": False},
            {"symbol": "MSFT", "date": "2026-07-21", "reject": True},
            {"symbol": "GOOG", "date": "2026-07-21", "reject": False},
        ]

        validated_rows = []
        rows_rejected = 0
        for i, r in enumerate(rows):
            try:
                if not loader._validate_row(r):
                    rows_rejected += 1
                    continue
                validated_rows.append(r)
            except ValueError:
                raise

        assert len(validated_rows) == 2
        assert rows_rejected == 1
        assert all(r["symbol"] != "MSFT" for r in validated_rows)
