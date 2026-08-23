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
        # 45% gap that doesn't match any clean split ratio, with low (non-corroborating)
        # volume - must still be rejected
        validator = TickValidator(symbol="BADCO", prior_close=100.0)
        errors = validator.validate(open_price=55.0, high=56.0, low=54.5, close=55.0, volume=5_000)
        assert any("price gap > 30%" in e for e in errors)

    def test_gap_near_but_outside_split_tolerance_still_rejected(self):
        # ~2.15x ratio - not within 2% of any common split ratio (2x tolerance band is [1.96, 2.04]),
        # with low (non-corroborating) volume
        validator = TickValidator(symbol="BADCO2", prior_close=100.0)
        errors = validator.validate(open_price=46.5, high=47.0, low=46.0, close=46.5, volume=5_000)
        assert any("price gap > 30%" in e for e in errors)

    def test_small_gap_under_threshold_not_flagged_by_sequence_check(self):
        validator = TickValidator(symbol="AAPL", prior_close=100.0)
        errors = validator.validate(open_price=110.0, high=111.0, low=109.0, close=110.0, volume=1_000_000)
        assert errors == []


class TestVolumeCorroboratedExtremeMoves:
    """A real meme-stock-style event (short squeeze, FDA outcome, running penny-stock
    pump) produces a legitimate >50% intraday spread backed by real, abnormally high
    volume - live-confirmed against real vendor data for CDTG (real spike, 21-37M
    shares/day, intraday spread up to 246%). No fixed percentage threshold can separate
    this from bad data, but volume can: fabricated/stale prints don't carry real trading
    volume.

    NOTE: this exemption applies ONLY to the intraday spread check (_check_price_bounds),
    not the day-over-day gap check (_check_sequence) - the gap check already has its own,
    different, tested recovery design (single-day anomaly rejected, self-heals once the
    next day confirms the new level - see test_price_transformer_sequence_check_recovery.py
    and the docstring on _check_sequence) that a same-day volume shortcut would undermine.
    """

    def test_high_volume_spread_not_rejected(self):
        # Large intraday spread (>50%), backed by real high volume - not rejected
        validator = TickValidator(symbol="CDTG", prior_close=2.94)
        errors = validator.validate(open_price=2.94, high=8.48, low=2.45, close=3.29, volume=37_465_900)
        assert errors == []

    def test_low_volume_spread_still_rejected(self):
        # Same large spread, but with low volume - no corroboration, still rejected
        validator = TickValidator(symbol="BADCO4", prior_close=2.94)
        errors = validator.validate(open_price=2.94, high=8.48, low=2.45, close=3.29, volume=3_000)
        assert any("spread > 50%" in e for e in errors)


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
