"""Regression: after test_position_sizer_no_regime_double_count_20260824.py's fix deleted
get_position_size_multiplier_from_regime() (position_sizer.py's only real caller of
RegimeManager's position-size path), two things it left behind became genuinely dead code
with zero remaining callers/readers anywhere in the repo (confirmed by grep, not assumption):
RegimeManager.get_position_size_multiplier() itself, and get_adjusted_config()'s write-only
config["_regime_position_size_mult"] entry.

NOTE: REGIME_PARAMS[<regime>]["position_size_mult"] itself and the REGIME_POSITION_SIZE_*
constants are NOT dead - algo/reporting/daily_report.py's _fetch_regime() reads the dict key
directly via get_regime_params() for report display, so those stay. This test locks in that
distinction: the dead wrapper/write-only-copy are gone, but the underlying data is not.
"""

import inspect

from algo.orchestration.regime_manager import RegimeManager


class TestDeadPositionSizeMultiplierPathsRemoved:
    def test_get_position_size_multiplier_method_removed(self):
        assert not hasattr(RegimeManager, "get_position_size_multiplier"), (
            "get_position_size_multiplier() must be deleted - its only caller was the "
            "__main__ demo block; the real production path was already removed from "
            "position_sizer.py for double-counting exposure_pct."
        )

    def test_get_adjusted_config_no_longer_writes_dead_regime_position_size_mult_key(self):
        source = inspect.getsource(RegimeManager.get_adjusted_config)
        assert "_regime_position_size_mult" not in source, (
            "get_adjusted_config() must not write config['_regime_position_size_mult'] - "
            "nothing in the repo ever read it back (grep-verified); it was a write-only "
            "leftover from before get_position_size_multiplier_from_regime() was deleted "
            "from position_sizer.py."
        )


class TestRegimeParamsPositionSizeMultStillPresentForReporting:
    """daily_report.py's _fetch_regime() depends on this - must NOT be removed."""

    def test_every_regime_has_position_size_mult(self):
        for regime in RegimeManager.REGIMES:
            params = RegimeManager.REGIME_PARAMS[regime]
            assert "position_size_mult" in params, (
                f"{regime} missing position_size_mult - algo/reporting/daily_report.py's "
                f"_fetch_regime() reads this key directly and will raise RuntimeError without it."
            )
