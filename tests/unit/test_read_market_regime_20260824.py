"""Regression tests for algo/risk/market_exposure.py::read_market_regime() and its thin
wrapper algo/orchestrator/phase7_signal_generation.py::_check_market_regime() - found with
ZERO dedicated test coverage during the 2026-08-24 exposure-system audit despite being the
canonical read every orchestrator phase uses to gate new entries (Phase 5 and Phase 7 both
call it before allowing a single trade). See
[[exposure_system_full_audit_and_vol_managed_multiplier_activated_20260824]].

Uses a past, ordinary trading Wednesday (2026-08-19) as eval_date throughout so the
same-day/pre-4PM branch in read_market_regime() (which depends on real wall-clock "now")
never applies - expected_trading_day resolves deterministically to eval_date itself.
"""

from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from algo.risk.market_exposure import MarketDataUnavailableError, read_market_regime

EVAL_DATE = date(2026, 8, 19)  # ordinary trading Wednesday, not "today"


def _row(
    is_entry_allowed: bool = True,
    exposure_pct: float | None = 65.0,
    regime: str | None = "confirmed_uptrend",
    halt_reasons_str: str | None = None,
    raw_score: float | None = 70.0,
    exposure_tier: str | None = "confirmed_uptrend",
    cached_date: date = EVAL_DATE,
    data_unavailable: bool = False,
    reason: str | None = None,
) -> tuple[Any, ...]:
    return (
        is_entry_allowed,
        exposure_pct,
        regime,
        halt_reasons_str,
        raw_score,
        exposure_tier,
        cached_date,
        data_unavailable,
        reason,
    )


@contextmanager
def _fake_db_context(cur: MagicMock) -> Any:
    yield cur


def _read_with_row(row: tuple[Any, ...]) -> dict[str, Any]:
    cur = MagicMock()
    cur.fetchone.return_value = row
    with patch("algo.risk.market_exposure.DatabaseContext", return_value=_fake_db_context(cur)):
        return read_market_regime(EVAL_DATE)


class TestHappyPath:
    def test_returns_expected_shape_and_types(self) -> None:
        result = _read_with_row(_row())
        assert result == {
            "is_entry_allowed": True,
            "exposure_pct": 65.0,
            "regime": "confirmed_uptrend",
            "halt_reasons": [],
            "raw_score": 70.0,
            "exposure_tier": "confirmed_uptrend",
        }

    def test_raw_score_none_passes_through_as_none(self) -> None:
        result = _read_with_row(_row(raw_score=None))
        assert result["raw_score"] is None

    def test_valid_halt_reasons_json_deserialized(self) -> None:
        result = _read_with_row(_row(halt_reasons_str='["VIX>40 rising", "credit spread>8.5%"]'))
        assert result["halt_reasons"] == ["VIX>40 rising", "credit spread>8.5%"]


class TestFailClosedGuards:
    def test_no_row_raises(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = None
        with patch("algo.risk.market_exposure.DatabaseContext", return_value=_fake_db_context(cur)):
            with pytest.raises(MarketDataUnavailableError, match="No market_exposure_daily data"):
                read_market_regime(EVAL_DATE)

    def test_data_unavailable_raises_with_reason(self) -> None:
        with pytest.raises(MarketDataUnavailableError, match="loader crashed"):
            _read_with_row(_row(data_unavailable=True, reason="loader crashed"))

    def test_stale_snapshot_raises(self) -> None:
        with pytest.raises(MarketDataUnavailableError, match="too stale"):
            _read_with_row(_row(cached_date=EVAL_DATE - timedelta(days=5)))

    def test_null_exposure_pct_raises(self) -> None:
        with pytest.raises(MarketDataUnavailableError, match="NULL exposure_pct"):
            _read_with_row(_row(exposure_pct=None))

    def test_null_regime_raises(self) -> None:
        with pytest.raises(MarketDataUnavailableError, match="NULL/empty regime"):
            _read_with_row(_row(regime=None))

    def test_empty_regime_raises(self) -> None:
        with pytest.raises(MarketDataUnavailableError, match="NULL/empty regime"):
            _read_with_row(_row(regime=""))

    def test_null_exposure_tier_raises(self) -> None:
        with pytest.raises(MarketDataUnavailableError, match="NULL/empty exposure_tier"):
            _read_with_row(_row(exposure_tier=None))

    def test_db_error_wrapped_as_market_data_unavailable(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection reset")
        with patch("algo.risk.market_exposure.DatabaseContext", return_value=_fake_db_context(cur)):
            with pytest.raises(MarketDataUnavailableError, match="Could not read market regime"):
                read_market_regime(EVAL_DATE)


class TestMalformedHaltReasonsDegradesGracefully:
    def test_invalid_json_falls_back_to_empty_list_not_crash(self) -> None:
        result = _read_with_row(_row(halt_reasons_str="{not valid json"))
        assert result["halt_reasons"] == []

    def test_json_non_list_falls_back_to_empty_list(self) -> None:
        result = _read_with_row(_row(halt_reasons_str='{"not": "a list"}'))
        assert result["halt_reasons"] == []


class TestPhase7Wrapper:
    def test_check_market_regime_delegates_to_read_market_regime(self) -> None:
        from algo.orchestrator.phase7_signal_generation import _check_market_regime

        expected = {
            "is_entry_allowed": False,
            "exposure_pct": 10.0,
            "regime": "correction",
            "halt_reasons": ["SPY < 30wk MA"],
            "raw_score": 5.0,
            "exposure_tier": "correction",
        }
        with patch("algo.risk.read_market_regime", return_value=expected) as mock_fn:
            result = _check_market_regime(EVAL_DATE)
        mock_fn.assert_called_once_with(EVAL_DATE)
        assert result == expected

    def test_check_market_regime_propagates_unavailable_error(self) -> None:
        from algo.orchestrator.phase7_signal_generation import _check_market_regime

        with patch(
            "algo.risk.read_market_regime",
            side_effect=MarketDataUnavailableError("no data"),
        ):
            with pytest.raises(MarketDataUnavailableError, match="no data"):
                _check_market_regime(EVAL_DATE)
