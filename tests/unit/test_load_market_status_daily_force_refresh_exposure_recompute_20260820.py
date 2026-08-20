"""Regression test: MarketStatusDailyLoader._compute_market_exposure() always called
MarketExposure.compute(eval_date, force_recompute=False), ignoring TECH_FULL_REFRESH -
the env var scripts/run_loader.py's established `--force-refresh` flag sets for every other
loader. Since MarketExposure.compute() caches one row per eval_date and never re-derives it
once written, this meant a same-day exposure-model code change (a new factor, a rebalanced
weight, a bugfix) could never be reflected until the date rolled over, even via
`--force-refresh` - the flag silently did nothing here specifically. Live-confirmed
2026-08-20: the morning run's pre-redesign row sat stale all day with no supported way to
refresh it short of calling MarketExposure.compute(force_recompute=True) directly, bypassing
this loader's status/lock tracking. Fixed to thread TECH_FULL_REFRESH through, reusing the
existing mechanism instead of adding a new one-off flag.
"""

import os
from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_market_status_daily import MarketStatusDailyLoader


def _make_loader():
    loader = MarketStatusDailyLoader()
    loader._persist_market_exposure = MagicMock()  # avoid a real DB write
    return loader


class TestForceRefreshThreadedIntoExposureRecompute:
    def test_tech_full_refresh_true_forces_recompute(self, monkeypatch):
        monkeypatch.setenv("TECH_FULL_REFRESH", "true")
        loader = _make_loader()
        mock_result = {"regime": "confirmed_uptrend", "exposure_pct": 70.0, "raw_score": 70.0}
        with patch("algo.risk.market_exposure.MarketExposure") as mock_cls:
            mock_cls.return_value.compute.return_value = mock_result
            loader._compute_market_exposure(date(2026, 8, 20), {})
            mock_cls.return_value.compute.assert_called_once_with(date(2026, 8, 20), force_recompute=True)

    def test_tech_full_refresh_unset_does_not_force(self, monkeypatch):
        monkeypatch.delenv("TECH_FULL_REFRESH", raising=False)
        loader = _make_loader()
        mock_result = {"regime": "confirmed_uptrend", "exposure_pct": 70.0, "raw_score": 70.0}
        with patch("algo.risk.market_exposure.MarketExposure") as mock_cls:
            mock_cls.return_value.compute.return_value = mock_result
            loader._compute_market_exposure(date(2026, 8, 20), {})
            mock_cls.return_value.compute.assert_called_once_with(date(2026, 8, 20), force_recompute=False)

    def test_tech_full_refresh_false_does_not_force(self, monkeypatch):
        monkeypatch.setenv("TECH_FULL_REFRESH", "false")
        loader = _make_loader()
        mock_result = {"regime": "confirmed_uptrend", "exposure_pct": 70.0, "raw_score": 70.0}
        with patch("algo.risk.market_exposure.MarketExposure") as mock_cls:
            mock_cls.return_value.compute.return_value = mock_result
            loader._compute_market_exposure(date(2026, 8, 20), {})
            mock_cls.return_value.compute.assert_called_once_with(date(2026, 8, 20), force_recompute=False)

    def test_tech_full_refresh_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("TECH_FULL_REFRESH", "TRUE")
        loader = _make_loader()
        mock_result = {"regime": "confirmed_uptrend", "exposure_pct": 70.0, "raw_score": 70.0}
        with patch("algo.risk.market_exposure.MarketExposure") as mock_cls:
            mock_cls.return_value.compute.return_value = mock_result
            loader._compute_market_exposure(date(2026, 8, 20), {})
            mock_cls.return_value.compute.assert_called_once_with(date(2026, 8, 20), force_recompute=True)
