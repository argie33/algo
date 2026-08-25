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
