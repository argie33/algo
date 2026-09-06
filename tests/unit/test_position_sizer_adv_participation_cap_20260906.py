"""Regression test for a 2026-09-06 addition to algo/trading/position_sizer.py (real-money-
readiness audit finding): every existing sizing cap (max_position_size_pct,
absolute_max_dollars_per_trade, etc.) is sized off portfolio_value alone - none of them
reference the STOCK's OWN trading volume, so a large-enough account could size a single
trade as a big fraction of a thinly-traded name's actual daily turnover even while clearing
LiquidityChecks' fixed ADV floor by a wide margin.

Added an OPTIONAL, opt-in max_pct_of_adv_dollars cap - skipped entirely when unset (zero
behavior change), only enforced when signal_date is provided (matches
LiquidityChecks.run_all's own windowing discipline).
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

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
        patch.object(sizer, "get_data_maturity_multiplier", return_value=Decimal("1.0")),
    )


def _db_context_with_adv(avg_dollar_vol):
    cur = MagicMock()
    cur.fetchone.return_value = (avg_dollar_vol,) if avg_dollar_vol is not None else None
    ctx = MagicMock()
    ctx.__enter__.return_value = cur
    ctx.__exit__.return_value = False
    return ctx


class TestMaxPctOfAdvDollars:
    def test_unset_by_default_no_behavior_change(self):
        """Not in CONFIG at all - must size normally, no ADV query executed at all (the
        function still uses DatabaseContext elsewhere, e.g. the sizing-audit INSERT, so this
        checks no query mentions price_daily/volume rather than asserting zero DB calls)."""
        sizer = _make_sizer()
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with patch("algo.trading.position_sizer.DatabaseContext") as mock_db_ctx:
                result = sizer._calculate_with_external_cursor(
                    symbol="AAPL",
                    entry_price=Decimal("100"),
                    stop_loss_price=Decimal("90"),
                    signal_date=date(2026, 9, 6),
                    portfolio_value=Decimal("1000000"),
                    enforce_total_risk_limit=False,
                )
            executed_queries = [
                call.args[0] for call in mock_db_ctx.return_value.__enter__.return_value.execute.call_args_list
            ]
            assert not any("price_daily" in q for q in executed_queries)
        assert result["status"] == "ok"
        assert result["shares"] * 100 > 5000

    def test_no_signal_date_skips_the_cap_even_if_configured(self):
        """The preliminary Phase 8 prefilter pass doesn't pass signal_date - the cap must be
        skipped there (not fail closed), not raise or block."""
        sizer = _make_sizer(max_pct_of_adv_dollars=1.0)
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with patch("algo.trading.position_sizer.DatabaseContext") as mock_db_ctx:
                result = sizer._calculate_with_external_cursor(
                    symbol="AAPL",
                    entry_price=Decimal("100"),
                    stop_loss_price=Decimal("90"),
                    signal_date=None,
                    portfolio_value=Decimal("1000000"),
                    enforce_total_risk_limit=False,
                )
            executed_queries = [
                call.args[0] for call in mock_db_ctx.return_value.__enter__.return_value.execute.call_args_list
            ]
            assert not any("price_daily" in q for q in executed_queries)
        assert result["status"] == "ok"

    def test_scales_down_position_to_fit_participation_cap(self):
        """1% of $1M avg dollar volume = $10,000 ceiling - a $1M portfolio with loose
        percentage caps would normally size a much larger position."""
        sizer = _make_sizer(max_pct_of_adv_dollars=1.0)
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with patch(
                "algo.trading.position_sizer.DatabaseContext",
                return_value=_db_context_with_adv(1_000_000.0),
            ):
                result = sizer._calculate_with_external_cursor(
                    symbol="AAPL",
                    entry_price=Decimal("100"),
                    stop_loss_price=Decimal("90"),
                    signal_date=date(2026, 9, 6),
                    portfolio_value=Decimal("1000000"),
                    enforce_total_risk_limit=False,
                )
        assert result["status"] == "ok"
        position_value = result["shares"] * 100
        assert position_value <= 10000
        assert result["shares"] == 100  # floor(10000 / 100), ROUND_DOWN

    def test_rejects_with_no_room_when_even_one_share_exceeds_cap(self):
        sizer = _make_sizer(max_pct_of_adv_dollars=1.0)
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with patch(
                "algo.trading.position_sizer.DatabaseContext",
                return_value=_db_context_with_adv(1000.0),  # 1% = $10 ceiling, entry is $100
            ):
                result = sizer._calculate_with_external_cursor(
                    symbol="THIN",
                    entry_price=Decimal("100"),
                    stop_loss_price=Decimal("90"),
                    signal_date=date(2026, 9, 6),
                    portfolio_value=Decimal("1000000"),
                    enforce_total_risk_limit=False,
                )
        assert result["shares"] == 0
        assert result["status"] == "no_room"
        assert "max_pct_of_adv_dollars" in result["reason"]

    def test_missing_adv_data_does_not_block_falls_through_to_other_caps(self):
        """Missing ADV data here is a refinement gap, not a tradability gate - unlike
        LiquidityChecks.run_all, this must never fail closed on missing data (that gate's
        job, not this cap's)."""
        sizer = _make_sizer(max_pct_of_adv_dollars=1.0)
        patches = _patched(sizer)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with patch(
                "algo.trading.position_sizer.DatabaseContext",
                return_value=_db_context_with_adv(None),
            ):
                result = sizer._calculate_with_external_cursor(
                    symbol="NODATA",
                    entry_price=Decimal("100"),
                    stop_loss_price=Decimal("90"),
                    signal_date=date(2026, 9, 6),
                    portfolio_value=Decimal("1000000"),
                    enforce_total_risk_limit=False,
                )
        assert result["status"] == "ok"
        assert result["shares"] > 0

    def test_raises_on_non_positive_config_value(self):
        sizer = _make_sizer(max_pct_of_adv_dollars=0)
        patches = _patched(sizer)
        try:
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
                sizer._calculate_with_external_cursor(
                    symbol="AAPL",
                    entry_price=Decimal("100"),
                    stop_loss_price=Decimal("90"),
                    signal_date=date(2026, 9, 6),
                    portfolio_value=Decimal("1000000"),
                    enforce_total_risk_limit=False,
                )
            raise AssertionError("Expected ValueError for non-positive max_pct_of_adv_dollars")
        except ValueError as e:
            assert "max_pct_of_adv_dollars" in str(e)
