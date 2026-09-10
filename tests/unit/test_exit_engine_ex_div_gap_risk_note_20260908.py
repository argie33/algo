"""price_daily has no reliable dividend-adjusted close (adj_close falls back to raw close
whenever yfinance omits "Adj Close" - see loaders/price_transformer.py), so a stop-loss can
trigger on an ex-dividend gap that is indistinguishable in the data from a real decline.
_gap_risk_note() must annotate (not suppress) a stop that looks gap-driven, and must be a
no-op for ordinary single-day moves - it never changes whether the stop fires.
"""

from decimal import Decimal

from algo.trading.exit_engine import _GAP_RISK_PCT_THRESHOLD, _gap_risk_note


def test_large_gap_triggers_annotation() -> None:
    note = _gap_risk_note(Decimal("93.00"), Decimal("100.00"))
    assert "GAP RISK" in note
    assert "7.0%" in note
    assert "ex-dividend" in note


def test_ordinary_move_is_silent() -> None:
    assert _gap_risk_note(Decimal("98.00"), Decimal("100.00")) == ""


def test_missing_prev_close_is_silent() -> None:
    assert _gap_risk_note(Decimal("93.00"), None) == ""


def test_zero_or_negative_prev_close_is_silent() -> None:
    assert _gap_risk_note(Decimal("93.00"), Decimal("0")) == ""
    assert _gap_risk_note(Decimal("93.00"), Decimal("-5")) == ""


def test_threshold_boundary_exact_match_triggers() -> None:
    prev_close = Decimal("100.00")
    cur_price = prev_close * (1 - Decimal(str(_GAP_RISK_PCT_THRESHOLD)))
    assert _gap_risk_note(cur_price, prev_close) != ""


def test_accepts_float_prev_close() -> None:
    note = _gap_risk_note(Decimal("93.00"), 100.0)
    assert "GAP RISK" in note
