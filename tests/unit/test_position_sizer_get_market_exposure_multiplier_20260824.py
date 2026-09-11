"""Regression tests for the real behavior of PositionSizer.get_market_exposure_multiplier(),
found untested as a unit during the 2026-08-24 exposure-system audit (every other
position-sizer test patches this method out via `patch.object(..., return_value=...)` -
see [[exposure_system_full_audit_and_vol_managed_multiplier_activated_20260824]]). This is
the multiplier applied to every single trade's size, so its own fail-fast/staleness/
data-unavailable logic deserves direct coverage rather than only ever being exercised as a
pre-canned mock in other tests.

Patches `_with_cursor` to actually invoke the real `fetch_exposure` closure with a fake
cursor (unlike the pre-canned-return-value pattern used elsewhere in this file's siblings),
so the closure's own branches - not just the outer wiring - are under test.
"""

from datetime import date as _date
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from algo.trading.position_sizer import PositionSizer
from utils.infrastructure.timezone import EASTERN_TZ

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "min_risk_pct_floor": 0.1,
    "max_position_size_pct": 100.0,
    "max_concentration_pct": 100.0,
    "max_total_invested_pct": 100.0,
    "max_total_risk_pct": 100.0,
    "risk_reduction_at_minus_5": 0.75,
    "risk_reduction_at_minus_10": 0.5,
    "risk_reduction_at_minus_15": 0.25,
    "risk_reduction_at_minus_20": 0.0,
    "vix_caution_threshold": 25.0,
    "vix_max_threshold": 35.0,
    "vix_caution_risk_reduction": 0.5,
}


def _sizer() -> PositionSizer:
    return PositionSizer(config=dict(CONFIG))


def _today_et() -> _date:
    return datetime.now(EASTERN_TZ).date()


def _run_with_row(row: tuple[Any, ...]) -> Decimal:
    sizer = _sizer()
    cur = MagicMock()
    cur.fetchone.return_value = row
    with patch.object(sizer, "_with_cursor", side_effect=lambda op: op(cur)):
        return sizer.get_market_exposure_multiplier()


def test_fresh_available_data_returns_pct_over_100_as_decimal() -> None:
    row = (65.0, _today_et(), False, None)
    result = _run_with_row(row)
    assert result == Decimal("65") / Decimal(100)


def test_no_row_raises() -> None:
    sizer = _sizer()
    cur = MagicMock()
    cur.fetchone.return_value = None
    with patch.object(sizer, "_with_cursor", side_effect=lambda op: op(cur)):
        with pytest.raises(ValueError, match="unavailable"):
            sizer.get_market_exposure_multiplier()


def test_null_exposure_pct_raises() -> None:
    row = (None, _today_et(), False, None)
    with pytest.raises(ValueError, match="unavailable"):
        _run_with_row(row)


def test_data_unavailable_with_reason_raises_with_reason_in_message() -> None:
    row = (50.0, _today_et(), True, "loader failed: SEC rate limit")
    with pytest.raises(ValueError, match="loader failed: SEC rate limit"):
        _run_with_row(row)


def test_data_unavailable_with_empty_reason_raises_governance_error() -> None:
    row = (50.0, _today_et(), True, "")
    with pytest.raises(ValueError, match="reason field"):
        _run_with_row(row)


def test_data_unavailable_with_none_reason_raises_governance_error() -> None:
    row = (50.0, _today_et(), True, None)
    with pytest.raises(ValueError, match="reason field"):
        _run_with_row(row)


def test_stale_data_beyond_one_trading_day_raises() -> None:
    stale_date = _today_et() - timedelta(days=10)
    row = (50.0, stale_date, False, None)
    with pytest.raises(ValueError, match="too stale"):
        _run_with_row(row)


def test_schema_mismatch_too_few_columns_raises() -> None:
    sizer = _sizer()
    cur = MagicMock()
    cur.fetchone.return_value = (50.0, _today_et())  # only 2 columns instead of 4
    with patch.object(sizer, "_with_cursor", side_effect=lambda op: op(cur)):
        with pytest.raises(ValueError, match="Schema mismatch"):
            sizer.get_market_exposure_multiplier()


def test_zero_exposure_returns_zero_multiplier() -> None:
    row = (0.0, _today_et(), False, None)
    result = _run_with_row(row)
    assert result == Decimal("0")


def test_full_exposure_returns_one_multiplier() -> None:
    row = (100.0, _today_et(), False, None)
    result = _run_with_row(row)
    assert result == Decimal("1")


class TestRunDateBoundLookup:
    """Regression tests for the 2026-09-10 orchestration re-audit finding: without a run_date,
    this method always queried "latest row"/real wall-clock "now" regardless of what date the
    sizer was actually running for - a historical/backfill run (--date mode) would then be
    sized using TODAY's real regime while Phase 5/7 qualified candidates under the historical
    date's regime, a genuine cross-phase regime mismatch within the same run."""

    def test_default_run_date_none_preserves_live_wall_clock_behavior(self) -> None:
        sizer = PositionSizer(config=dict(CONFIG))
        assert sizer.run_date is None
        cur = MagicMock()
        cur.fetchone.return_value = (65.0, _today_et(), False, None)
        with patch.object(sizer, "_with_cursor", side_effect=lambda op: op(cur)):
            sizer.get_market_exposure_multiplier()
        query = cur.execute.call_args.args[0]
        assert "WHERE date <= %s" not in query, "live (run_date=None) must not add a date bound"

    def test_run_date_bounds_the_query_to_that_date(self) -> None:
        as_of = _date(2026, 6, 1)
        sizer = PositionSizer(config=dict(CONFIG), run_date=as_of)
        cur = MagicMock()
        cur.fetchone.return_value = (40.0, as_of, False, None)
        with patch.object(sizer, "_with_cursor", side_effect=lambda op: op(cur)):
            result = sizer.get_market_exposure_multiplier()
        query, params = cur.execute.call_args.args
        assert "WHERE date <= %s" in query
        assert params == (as_of,)
        assert result == Decimal("40") / Decimal(100)

    def test_staleness_is_judged_against_run_date_not_real_today(self) -> None:
        """A historical run_date far in the past must not spuriously fail staleness just
        because real wall-clock 'today' is much later - the same-vintage market_exposure_daily
        row for that historical date must be treated as fresh."""
        as_of = _date(2026, 6, 1)
        sizer = PositionSizer(config=dict(CONFIG), run_date=as_of)
        cur = MagicMock()
        # Row is dated exactly as_of - "fresh" relative to run_date, wildly stale relative to
        # real today.
        cur.fetchone.return_value = (50.0, as_of, False, None)
        with patch.object(sizer, "_with_cursor", side_effect=lambda op: op(cur)):
            result = sizer.get_market_exposure_multiplier()
        assert result == Decimal("50") / Decimal(100)

    def test_run_date_far_past_still_raises_if_row_itself_is_stale_relative_to_run_date(
        self,
    ) -> None:
        as_of = _date(2026, 6, 10)
        stale_row_date = as_of - timedelta(days=10)
        sizer = PositionSizer(config=dict(CONFIG), run_date=as_of)
        cur = MagicMock()
        cur.fetchone.return_value = (50.0, stale_row_date, False, None)
        with patch.object(sizer, "_with_cursor", side_effect=lambda op: op(cur)):
            with pytest.raises(ValueError, match="too stale"):
                sizer.get_market_exposure_multiplier()
