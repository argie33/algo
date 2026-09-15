"""Regression tests for the deterministic OCC-symbol/expiration helpers in
run_options_backtest_real.py - a wrong construction silently returns empty/404 from Alpaca
rather than erroring loudly, so these are worth pinning down explicitly."""

from datetime import date

from algo.backtest.run_options_backtest_real import (
    _nearest_monthly_expiration,
    _occ_symbol,
    _round_to_standard_strike,
    _third_friday,
)


def test_occ_symbol_matches_live_verified_contract() -> None:
    # AAPL240621P00190000 returned real bars from Alpaca's /v1beta1/options/bars, 2026-09-15.
    assert _occ_symbol("AAPL", date(2024, 6, 21), "put", 190.0) == "AAPL240621P00190000"


def test_occ_symbol_call_and_fractional_strike() -> None:
    assert _occ_symbol("MSFT", date(2024, 3, 15), "call", 402.5) == "MSFT240315C00402500"


def test_third_friday_known_dates() -> None:
    assert _third_friday(2024, 6) == date(2024, 6, 21)
    assert _third_friday(2024, 3) == date(2024, 3, 15)


def test_nearest_monthly_expiration_within_dte_band() -> None:
    entry = date(2024, 5, 20)
    target = date(2024, 6, 26)  # entry + 37 days
    exp = _nearest_monthly_expiration(target, dte_low=27, dte_high=48, entry_date=entry)
    assert exp is not None
    dte = (exp - entry).days
    assert 27 <= dte <= 48


def test_nearest_monthly_expiration_none_when_no_month_fits() -> None:
    entry = date(2024, 5, 1)
    assert _nearest_monthly_expiration(date(2024, 5, 3), dte_low=27, dte_high=48, entry_date=entry) is None


def test_round_to_standard_strike_bands() -> None:
    assert _round_to_standard_strike(19.7) == 19.5
    assert _round_to_standard_strike(63.2) == 63.0
    assert _round_to_standard_strike(187.3) == 187.5
    assert _round_to_standard_strike(255.0) == 255.0
