"""Real-behavior regression tests for algo/orchestration/regime_manager.py::RegimeManager -
found with ZERO dedicated test coverage (beyond the dead-code-removal regression in
test_regime_manager_dead_position_size_multiplier_removed_20260824.py) during the 2026-08-24
exposure-system audit, despite gating position sizing (max_hold_days, T1/T2/T3 targets) for
every single trade via get_adjusted_config(). See
[[exposure_system_full_audit_and_vol_managed_multiplier_activated_20260824]].

Uses a past, ordinary trading Wednesday (2026-08-19) as as_of_date throughout so
_expected_regime_date()'s same-day/pre-4PM branch (which depends on real wall-clock "now")
never applies - candidate resolves deterministically to as_of_date itself, same convention as
test_read_market_regime_20260824.py.
"""

from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from algo.orchestration.regime_manager import RegimeManager

EVAL_DATE = date(2026, 8, 19)  # ordinary trading Wednesday, not "today"

DB_PATCH_TARGET = "algo.orchestration.regime_manager.DatabaseContext"


@contextmanager
def _fake_db_context(cur: MagicMock) -> Any:
    yield cur


def _regime_row(
    regime: str | None = "confirmed_uptrend",
    data_date: date = EVAL_DATE,
    data_unavailable: bool = False,
    reason: str | None = None,
) -> tuple[Any, ...]:
    return (regime, data_date, data_unavailable, reason)


def _get_regime_with_row(row: tuple[Any, ...] | None) -> str:
    cur = MagicMock()
    cur.fetchone.return_value = row
    rm = RegimeManager()
    with patch(DB_PATCH_TARGET, return_value=_fake_db_context(cur)):
        return rm.get_current_regime(EVAL_DATE)


class TestGetCurrentRegimeHappyPath:
    def test_returns_regime_string_from_row(self) -> None:
        assert _get_regime_with_row(_regime_row(regime="caution")) == "caution"

    def test_all_four_known_regimes_accepted(self) -> None:
        for regime in RegimeManager.REGIMES:
            assert _get_regime_with_row(_regime_row(regime=regime)) == regime


class TestGetCurrentRegimeFailClosedGuards:
    def test_no_row_raises(self) -> None:
        with pytest.raises(RuntimeError, match="data unavailable"):
            _get_regime_with_row(None)

    def test_null_regime_in_row_raises(self) -> None:
        with pytest.raises(RuntimeError, match="data unavailable"):
            _get_regime_with_row(_regime_row(regime=None))

    def test_data_unavailable_flag_raises_with_reason(self) -> None:
        with pytest.raises(RuntimeError, match="loader crashed"):
            _get_regime_with_row(_regime_row(data_unavailable=True, reason="loader crashed"))

    def test_stale_snapshot_raises(self) -> None:
        with pytest.raises(RuntimeError, match="too stale"):
            _get_regime_with_row(_regime_row(data_date=EVAL_DATE - timedelta(days=5)))

    def test_unknown_regime_string_raises(self) -> None:
        with pytest.raises(RuntimeError, match="is invalid"):
            _get_regime_with_row(_regime_row(regime="not_a_real_regime"))

    def test_db_error_wrapped_as_runtime_error(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection reset")
        rm = RegimeManager()
        with patch(DB_PATCH_TARGET, return_value=_fake_db_context(cur)):
            with pytest.raises(RuntimeError, match="Failed to determine market regime"):
                rm.get_current_regime(EVAL_DATE)


class TestGetRegimeParams:
    def test_returns_matching_params_dict_for_each_regime(self) -> None:
        rm = RegimeManager()
        for regime in RegimeManager.REGIMES:
            with patch.object(RegimeManager, "get_current_regime", return_value=regime):
                assert rm.get_regime_params(EVAL_DATE) is RegimeManager.REGIME_PARAMS[regime]


class TestGetAdjustedConfig:
    def _base_config(self) -> dict[str, Any]:
        return {
            "max_hold_days": 20,
            "t1_target_r_multiple": 1.0,
            "t2_target_r_multiple": 2.0,
            "t3_target_r_multiple": 3.0,
        }

    @pytest.mark.parametrize(
        "missing_key",
        ["max_hold_days", "t1_target_r_multiple", "t2_target_r_multiple", "t3_target_r_multiple"],
    )
    def test_missing_required_base_config_key_raises(self, missing_key: str) -> None:
        rm = RegimeManager()
        base = self._base_config()
        del base[missing_key]
        with pytest.raises(ValueError, match="CRITICAL"):
            rm.get_adjusted_config(base, EVAL_DATE)

    def test_none_value_for_required_key_raises(self) -> None:
        rm = RegimeManager()
        base = self._base_config()
        base["max_hold_days"] = None
        with pytest.raises(ValueError, match="CRITICAL"):
            rm.get_adjusted_config(base, EVAL_DATE)

    def test_applies_real_regime_multipliers_and_metadata(self) -> None:
        rm = RegimeManager()
        base = self._base_config()
        with patch.object(RegimeManager, "get_current_regime", return_value="confirmed_uptrend"):
            adjusted = rm.get_adjusted_config(base, EVAL_DATE)

        params = RegimeManager.REGIME_PARAMS["confirmed_uptrend"]
        assert adjusted["max_hold_days"] == int(base["max_hold_days"] * params["max_hold_days_mult"])
        assert adjusted["t1_target_r_multiple"] == base["t1_target_r_multiple"] * params["target_1_mult"]
        assert adjusted["t2_target_r_multiple"] == base["t2_target_r_multiple"] * params["target_2_mult"]
        assert adjusted["t3_target_r_multiple"] == base["t3_target_r_multiple"] * params["target_3_mult"]
        assert adjusted["_regime_adjusted"] is True
        assert adjusted["_regime"] == "confirmed_uptrend"
        assert adjusted["_regime_weight_update_alpha"] == params["weight_update_alpha"]
        # Original base_config must not be mutated (adjusted is a copy).
        assert base["max_hold_days"] == 20

    def test_different_regimes_produce_different_adjusted_values(self) -> None:
        rm = RegimeManager()
        base = self._base_config()
        with patch.object(RegimeManager, "get_current_regime", return_value="confirmed_uptrend"):
            bull = rm.get_adjusted_config(base, EVAL_DATE)
        with patch.object(RegimeManager, "get_current_regime", return_value="correction"):
            bear = rm.get_adjusted_config(base, EVAL_DATE)

        # Confirmed uptrend and correction must not silently collapse to the same adjustment -
        # that would mean regime is being ignored, not applied.
        assert bull["max_hold_days"] != bear["max_hold_days"]
        assert bull["t1_target_r_multiple"] != bear["t1_target_r_multiple"]


class TestRegimeHistory:
    def test_transition_and_days_in_regime_tracked_correctly(self) -> None:
        day1, day2, day3 = date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 19)
        # SQL returns DESC (newest first); the method reverses internally to walk chronologically.
        rows = [
            (day3, "correction", False),
            (day2, "correction", False),
            (day1, "confirmed_uptrend", False),
        ]
        cur = MagicMock()
        cur.fetchall.return_value = rows
        rm = RegimeManager()
        with patch(DB_PATCH_TARGET, return_value=_fake_db_context(cur)):
            history = rm.regime_history(days=30)

        assert [h["date"] for h in history] == [day1, day2, day3]
        assert history[0] == {"date": day1, "regime": "confirmed_uptrend", "days_in_regime": 1, "transition": False}
        assert history[1] == {"date": day2, "regime": "correction", "days_in_regime": 1, "transition": True}
        assert history[2] == {"date": day3, "regime": "correction", "days_in_regime": 2, "transition": False}

    def test_data_unavailable_rows_are_skipped_and_do_not_break_the_regime_chain(self) -> None:
        day1, day2, day3 = date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 19)
        rows = [
            (day3, "confirmed_uptrend", False),
            (day2, "confirmed_uptrend", True),  # marked unavailable - must be excluded entirely
            (day1, "confirmed_uptrend", False),
        ]
        cur = MagicMock()
        cur.fetchall.return_value = rows
        rm = RegimeManager()
        with patch(DB_PATCH_TARGET, return_value=_fake_db_context(cur)):
            history = rm.regime_history(days=30)

        assert [h["date"] for h in history] == [day1, day3]
        # day3 compares against day1 (the last real row), not the skipped day2, and stays
        # in the same regime with no false transition and continuous days_in_regime.
        assert history[1] == {"date": day3, "regime": "confirmed_uptrend", "days_in_regime": 2, "transition": False}

    def test_empty_history_returns_empty_list(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = []
        rm = RegimeManager()
        with patch(DB_PATCH_TARGET, return_value=_fake_db_context(cur)):
            assert rm.regime_history(days=30) == []

    def test_db_error_raises_runtime_error(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection reset")
        rm = RegimeManager()
        with patch(DB_PATCH_TARGET, return_value=_fake_db_context(cur)):
            with pytest.raises(RuntimeError, match="Failed to fetch regime history"):
                rm.regime_history(days=30)


def _get_strength_with_row(row: tuple[Any, ...] | None) -> float:
    cur = MagicMock()
    cur.fetchone.return_value = row
    rm = RegimeManager()
    with patch(DB_PATCH_TARGET, return_value=_fake_db_context(cur)):
        return rm.get_regime_strength(EVAL_DATE)


class TestGetRegimeStrength:
    def test_mid_range_score_scaled_to_0_1(self) -> None:
        assert _get_strength_with_row((70.0, False, None)) == pytest.approx(0.7)

    def test_score_above_100_clamped_to_1(self) -> None:
        assert _get_strength_with_row((150.0, False, None)) == 1.0

    def test_negative_score_clamped_to_0(self) -> None:
        assert _get_strength_with_row((-10.0, False, None)) == 0.0

    def test_no_row_raises(self) -> None:
        with pytest.raises(RuntimeError, match="unavailable"):
            _get_strength_with_row(None)

    def test_data_unavailable_flag_raises_with_reason(self) -> None:
        with pytest.raises(RuntimeError, match="stale price snapshot"):
            _get_strength_with_row((70.0, True, "stale price snapshot"))

    def test_db_error_wrapped_as_runtime_error(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection reset")
        rm = RegimeManager()
        with patch(DB_PATCH_TARGET, return_value=_fake_db_context(cur)):
            with pytest.raises(RuntimeError, match="Failed to fetch market exposure confidence"):
                rm.get_regime_strength(EVAL_DATE)
