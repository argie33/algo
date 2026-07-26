#!/usr/bin/env python3
"""Tests for utils/data/tick_validator.py - price tick validation, including the
stock-split-vs-bad-data distinction in TickValidator._check_sequence."""

from utils.data.tick_validator import TickValidator, validate_price_tick


class TestSequenceCheckSplitDetection:
    """A stock split produces a legitimate >30% single-day close-to-close gap (prices are
    stored raw/unadjusted). This must not be rejected identically to real bad data."""

    def test_two_for_one_split_not_rejected(self):
        validator = TickValidator(symbol="AAPL", prior_close=200.0)
        errors = validator.validate(open_price=100.5, high=101.0, low=99.5, close=100.0, volume=5_000_000)
        assert errors == []

    def test_three_for_one_split_not_rejected(self):
        validator = TickValidator(symbol="NVDA", prior_close=900.0)
        errors = validator.validate(open_price=300.5, high=301.0, low=299.0, close=300.0, volume=5_000_000)
        assert errors == []

    def test_three_for_two_split_not_rejected(self):
        validator = TickValidator(symbol="XYZ", prior_close=150.0)
        errors = validator.validate(open_price=100.2, high=100.5, low=99.8, close=100.0, volume=1_000_000)
        assert errors == []

    def test_reverse_split_one_for_ten_not_rejected(self):
        # Reverse split: price rises ~10x (common for distressed penny stocks avoiding delisting)
        validator = TickValidator(symbol="PENNY", prior_close=1.0)
        errors = validator.validate(open_price=9.9, high=10.1, low=9.8, close=10.0, volume=500_000)
        assert errors == []

    def test_genuine_bad_data_gap_still_rejected(self):
        # 45% gap that doesn't match any clean split ratio - must still be rejected
        validator = TickValidator(symbol="BADCO", prior_close=100.0)
        errors = validator.validate(open_price=55.0, high=56.0, low=54.5, close=55.0, volume=1_000_000)
        assert any("price gap > 30%" in e for e in errors)

    def test_gap_near_but_outside_split_tolerance_still_rejected(self):
        # ~2.15x ratio - not within 2% of any common split ratio (2x tolerance band is [1.96, 2.04])
        validator = TickValidator(symbol="BADCO2", prior_close=100.0)
        errors = validator.validate(open_price=46.5, high=47.0, low=46.0, close=46.5, volume=1_000_000)
        assert any("price gap > 30%" in e for e in errors)

    def test_small_gap_under_threshold_not_flagged_by_sequence_check(self):
        validator = TickValidator(symbol="AAPL", prior_close=100.0)
        errors = validator.validate(open_price=110.0, high=111.0, low=109.0, close=110.0, volume=1_000_000)
        assert errors == []


class TestValidatePriceTickBasics:
    def test_valid_tick_passes(self):
        is_valid, errors = validate_price_tick(
            symbol="AAPL", open_price=150.0, high=152.0, low=149.0, close=151.0, volume=1_000_000
        )
        assert is_valid
        assert errors == []

    def test_negative_price_rejected(self):
        is_valid, _errors = validate_price_tick(
            symbol="AAPL", open_price=-1.0, high=152.0, low=149.0, close=151.0, volume=1_000_000
        )
        assert not is_valid

    def test_high_below_low_rejected(self):
        is_valid, _errors = validate_price_tick(
            symbol="AAPL", open_price=150.0, high=100.0, low=149.0, close=151.0, volume=1_000_000
        )
        assert not is_valid
