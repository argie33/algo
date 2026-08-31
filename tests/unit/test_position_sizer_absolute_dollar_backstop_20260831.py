"""Regression test for a 2026-08-31 addition to algo/trading/position_sizer.py: every existing
risk limit (max_position_size_pct, max_concentration_pct, max_total_invested_pct,
max_total_risk_pct) is a PERCENTAGE of portfolio_value - if portfolio_value were ever wrong
(a bug upstream of _validate_alpaca_equity's relative sanity check, or a bad snapshot that check
can't itself catch), every percentage-based limit would look "compliant" while authorizing an
arbitrarily large real-dollar trade. See absolute_dollar_backstop_missing_open_recommendation_20260831
in project memory for the full finding.

Added two OPTIONAL, opt-in absolute-dollar ceilings - absolute_max_dollars_per_trade (per
position, scales down like the sibling max_position_size_pct cap) and
absolute_max_total_exposure_dollars (aggregate, blocks like the sibling max_total_invested_pct
check) - that are completely independent of portfolio_value. Deliberately skipped entirely when
unset (zero behavior change for anyone who hasn't configured them - the right dollar figure
depends on the account's real intended size, not something to invent).
"""

from decimal import Decimal
from unittest.mock import patch

from algo.trading.position_sizer import PositionSizer

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "min_risk_pct_floor": 0.5,
    "max_position_size_pct": 50.0,
    "max_concentration_pct": 50.0,
    "max_total_invested_pct": 90.0,
    "max_total_risk_pct": 50.0,
    "risk_reduction_at_minus_5": 0.75,
    "risk_reduction_at_minus_10": 0.5,
    "risk_reduction_at_minus_15": 0.25,
    "risk_reduction_at_minus_20": 0.0,
    "vix_caution_threshold": 25.0,
    "vix_max_threshold": 35.0,
    "vix_caution_risk_reduction": 0.5,
}


def _make_sizer(**overrides):
    config = dict(CONFIG)
    config.update(overrides)
    return PositionSizer(config=config)


def _patched(sizer, active_positions_value="0"):
    return (
        patch.object(sizer, "get_position_count", return_value=1),
        patch.object(sizer, "get_active_positions_value", return_value=Decimal(active_positions_value)),
        patch.object(sizer, "get_risk_adjustment", return_value=Decimal("1.0")),
        patch.object(sizer, "get_market_exposure_multiplier", return_value=Decimal("1.0")),
        patch.object(sizer, "get_phase_size_multiplier", return_value=1.0),
        patch.object(sizer, "get_vix_caution_multiplier", return_value=Decimal("1.0")),
    )


class TestAbsoluteMaxDollarsPerTrade:
    def test_unset_by_default_no_behavior_change(self):
        """Not in CONFIG at all - must size normally, exactly as before this feature existed."""
        sizer = _make_sizer()
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = sizer._calculate_with_external_cursor(
                symbol="AAPL",
                entry_price=Decimal("100"),
                stop_loss_price=Decimal("90"),
                portfolio_value=Decimal("1000000"),
                enforce_total_risk_limit=False,
            )
        assert result["status"] == "ok"
        # Large portfolio + loose percentage caps would normally allow a large position -
        # confirms the absolute cap isn't silently active with some implicit default.
        assert result["shares"] * 100 > 5000

    def test_scales_down_position_to_fit_absolute_ceiling(self):
        """A $1M portfolio with loose percentage caps would normally size a much larger
        position - the absolute ceiling must cap it independent of portfolio_value."""
        sizer = _make_sizer(absolute_max_dollars_per_trade=5000)
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = sizer._calculate_with_external_cursor(
                symbol="AAPL",
                entry_price=Decimal("100"),
                stop_loss_price=Decimal("90"),
                portfolio_value=Decimal("1000000"),
                enforce_total_risk_limit=False,
            )
        assert result["status"] == "ok"
        position_value = result["shares"] * 100
        assert position_value <= 5000
        assert result["shares"] == 50  # floor(5000 / 100), ROUND_DOWN

    def test_rejects_with_no_room_when_even_one_share_exceeds_ceiling(self):
        sizer = _make_sizer(absolute_max_dollars_per_trade=50)
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = sizer._calculate_with_external_cursor(
                symbol="EXPENSIVE",
                entry_price=Decimal("100"),
                stop_loss_price=Decimal("90"),
                portfolio_value=Decimal("1000000"),
                enforce_total_risk_limit=False,
            )
        assert result["shares"] == 0
        assert result["status"] == "no_room"

    def test_raises_on_non_positive_config_value(self):
        sizer = _make_sizer(absolute_max_dollars_per_trade=0)
        patches = _patched(sizer)
        try:
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                sizer._calculate_with_external_cursor(
                    symbol="AAPL",
                    entry_price=Decimal("100"),
                    stop_loss_price=Decimal("90"),
                    portfolio_value=Decimal("1000000"),
                    enforce_total_risk_limit=False,
                )
            raise AssertionError("Expected ValueError for non-positive absolute_max_dollars_per_trade")
        except ValueError as e:
            assert "absolute_max_dollars_per_trade" in str(e)


class TestAbsoluteMaxTotalExposureDollars:
    def test_unset_by_default_no_behavior_change(self):
        sizer = _make_sizer()
        patches = _patched(sizer, active_positions_value="500000")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = sizer._calculate_with_external_cursor(
                symbol="AAPL",
                entry_price=Decimal("100"),
                stop_loss_price=Decimal("90"),
                portfolio_value=Decimal("1000000"),
                enforce_total_risk_limit=False,
            )
        assert result["status"] == "ok"

    def test_blocks_entry_when_total_exposure_would_exceed_absolute_ceiling(self):
        """Existing positions already worth $9,000; ceiling is $10,000 total. A new position
        that would push total exposure past that must be rejected, even though the
        percentage-based max_total_invested_pct (90% of a $1M portfolio) wouldn't itself fire."""
        sizer = _make_sizer(absolute_max_total_exposure_dollars=10000)
        patches = _patched(sizer, active_positions_value="9000")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = sizer._calculate_with_external_cursor(
                symbol="AAPL",
                entry_price=Decimal("100"),
                stop_loss_price=Decimal("90"),
                portfolio_value=Decimal("1000000"),
                enforce_total_risk_limit=False,
            )
        assert result["shares"] == 0
        assert result["status"] == "no_room"
        assert "absolute_max_total_exposure_dollars" in result["reason"]

    def test_allows_entry_when_total_exposure_stays_within_absolute_ceiling(self):
        sizer = _make_sizer(absolute_max_total_exposure_dollars=1000000)
        patches = _patched(sizer, active_positions_value="0")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = sizer._calculate_with_external_cursor(
                symbol="AAPL",
                entry_price=Decimal("100"),
                stop_loss_price=Decimal("90"),
                portfolio_value=Decimal("1000000"),
                enforce_total_risk_limit=False,
            )
        assert result["status"] == "ok"
        assert result["shares"] >= 1

    def test_raises_on_non_positive_config_value(self):
        sizer = _make_sizer(absolute_max_total_exposure_dollars=-1)
        patches = _patched(sizer)
        try:
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                sizer._calculate_with_external_cursor(
                    symbol="AAPL",
                    entry_price=Decimal("100"),
                    stop_loss_price=Decimal("90"),
                    portfolio_value=Decimal("1000000"),
                    enforce_total_risk_limit=False,
                )
            raise AssertionError("Expected ValueError for non-positive absolute_max_total_exposure_dollars")
        except ValueError as e:
            assert "absolute_max_total_exposure_dollars" in str(e)
