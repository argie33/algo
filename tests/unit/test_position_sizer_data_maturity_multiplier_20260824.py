"""Regression test for get_data_maturity_multiplier() (2026-08-24, real-money-readiness
goal session): position_sizer.py previously had no signal at all for "how much of the
long-lookback technical indicators (roc_252d, beta, volatility_252d) driving this trade are
still built on the pre-2026-05-26 bulk historical price_daily seed rather than real,
incrementally loaded data." scripts/check_synthetic_price_data.py already documented the gap
(only ~21 of 252 real trading days accumulated as of this fix) and load_technical_indicators.py's
ROC_OVERFLOW_SKIP only catches the most extreme seed-period corruption - anything less extreme
fed scores/position sizing at full confidence with zero visibility.

get_data_maturity_multiplier() closes that gap: a system-wide (not per-symbol) discount,
floored at 0.5x (never blocks entries outright - seed data still carries real signal, just
less trustworthy), reaching 1.0x once 252 real trading days have accumulated since
full-universe real collection began.
"""

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from algo.trading.position_sizer import PositionSizer

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "min_risk_pct_floor": 0.5,
    "max_position_size_pct": 10.0,
    "max_concentration_pct": 15.0,
    "max_total_invested_pct": 90.0,
    "max_total_risk_pct": 4.0,
    "risk_reduction_at_minus_5": 0.75,
    "risk_reduction_at_minus_10": 0.5,
    "risk_reduction_at_minus_15": 0.25,
    "risk_reduction_at_minus_20": 0.0,
    "vix_caution_threshold": 25.0,
    "vix_max_threshold": 35.0,
    "vix_caution_risk_reduction": 0.5,
}


def _make_sizer() -> PositionSizer:
    return PositionSizer(config=dict(CONFIG))


def _mock_db(full_coverage_start: date | None, real_trading_days: int) -> Any:
    """Two sequential fetchone() calls: MIN(date) full_coverage_start, then COUNT(*) real days."""
    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = [(full_coverage_start,), (real_trading_days,)]
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return patch("algo.trading.position_sizer.DatabaseContext", return_value=mock_ctx)


class TestDataMaturityMultiplierComputation:
    def test_zero_real_trading_days_floors_at_half(self) -> None:
        sizer = _make_sizer()
        with _mock_db(full_coverage_start=date(2026, 7, 16), real_trading_days=0):
            result = sizer.get_data_maturity_multiplier()
        assert result == Decimal("0.5")

    def test_full_252_days_coverage_reaches_full_multiplier(self) -> None:
        sizer = _make_sizer()
        with _mock_db(full_coverage_start=date(2026, 7, 16), real_trading_days=252):
            result = sizer.get_data_maturity_multiplier()
        assert result == Decimal("1.0")

    def test_more_than_252_days_does_not_exceed_full_multiplier(self) -> None:
        sizer = _make_sizer()
        with _mock_db(full_coverage_start=date(2020, 1, 1), real_trading_days=1000):
            result = sizer.get_data_maturity_multiplier()
        assert result == Decimal("1.0")

    def test_halfway_coverage_gives_halfway_discount(self) -> None:
        """126/252 = 0.5 coverage_ratio -> 0.5 + 0.5*0.5 = 0.75x."""
        sizer = _make_sizer()
        with _mock_db(full_coverage_start=date(2026, 7, 16), real_trading_days=126):
            result = sizer.get_data_maturity_multiplier()
        assert result == Decimal("0.75")

    def test_no_full_universe_coverage_detected_floors_at_half(self) -> None:
        """MIN(date) query returns no row at all - maximally conservative, not a crash."""
        sizer = _make_sizer()
        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [(None,)]
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False
        with patch("algo.trading.position_sizer.DatabaseContext", return_value=mock_ctx):
            result = sizer.get_data_maturity_multiplier()
        assert result == Decimal("0.5")
        # Second query (COUNT real trading days) must never run without a start date to count from.
        assert mock_cur.execute.call_count == 1

    def test_result_cached_across_calls_within_one_instance(self) -> None:
        """Phase 8 constructs one PositionSizer per run and reuses it across every symbol
        sized that run - re-running the full-table GROUP BY per symbol would be wasteful."""
        sizer = _make_sizer()
        with _mock_db(full_coverage_start=date(2026, 7, 16), real_trading_days=21) as mock_dc:
            first = sizer.get_data_maturity_multiplier()
            second = sizer.get_data_maturity_multiplier()
        assert first == second
        mock_dc.assert_called_once()


class TestDataMaturityMultiplierWiredIntoSizing:
    def test_discount_reduces_shares_and_appears_in_audit_reasons(self) -> None:
        sizer = _make_sizer()
        with (
            patch.object(sizer, "get_position_count", return_value=0),
            patch.object(sizer, "get_active_positions_value", return_value=Decimal("0")),
            patch.object(sizer, "get_risk_adjustment", return_value=Decimal("1.0")),
            patch.object(sizer, "get_market_exposure_multiplier", return_value=Decimal("1.0")),
            patch.object(sizer, "get_phase_size_multiplier", return_value=1.0),
            patch.object(sizer, "get_vix_caution_multiplier", return_value=Decimal("1.0")),
            patch.object(sizer, "get_data_maturity_multiplier", return_value=Decimal("0.5")),
            patch.object(sizer, "_record_sizing_audit") as mock_audit,
        ):
            result = sizer._calculate_with_external_cursor(
                symbol="AAPL",
                entry_price=Decimal("100"),
                stop_loss_price=Decimal("90"),
                portfolio_value=Decimal("100000"),
                enforce_total_risk_limit=False,
            )

        assert result["status"] == "ok"
        # unscaled: $1000 risk / $10 per share = 100 shares. 0.5x data_maturity_mult -> 50.
        assert result["shares"] == 50, (
            f"expected data_maturity_mult=0.5 to halve the unscaled 100-share base, got {result['shares']}"
        )
        assert mock_audit.call_args.kwargs["multipliers"]["data_maturity_mult"] == 0.5
        assert "data_maturity_mult" in mock_audit.call_args.kwargs["reasons"]

    def test_no_discount_when_data_is_fully_mature(self) -> None:
        sizer = _make_sizer()
        with (
            patch.object(sizer, "get_position_count", return_value=0),
            patch.object(sizer, "get_active_positions_value", return_value=Decimal("0")),
            patch.object(sizer, "get_risk_adjustment", return_value=Decimal("1.0")),
            patch.object(sizer, "get_market_exposure_multiplier", return_value=Decimal("1.0")),
            patch.object(sizer, "get_phase_size_multiplier", return_value=1.0),
            patch.object(sizer, "get_vix_caution_multiplier", return_value=Decimal("1.0")),
            patch.object(sizer, "get_data_maturity_multiplier", return_value=Decimal("1.0")),
        ):
            result = sizer._calculate_with_external_cursor(
                symbol="AAPL",
                entry_price=Decimal("100"),
                stop_loss_price=Decimal("90"),
                portfolio_value=Decimal("100000"),
                enforce_total_risk_limit=False,
            )

        assert result["status"] == "ok"
        assert result["shares"] == 100
