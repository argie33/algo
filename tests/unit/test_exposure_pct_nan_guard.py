"""Regression tests for 2 more NaN-comparison-guard gaps found 2026-08-10 continuing the
systematic sweep (`value < 0`/`> 100` never catch NaN - always False in Python):

- market.py's _normalize_exposure(): `exposure_pct < 0 or exposure_pct > 100` didn't catch
  NaN - this function's own docstring says "AWS position sizing depends on this".
- risk_dashboard.py's _fetch_exposure_tier_info(): `exposure_pct_raw < 0` didn't catch NaN -
  "Cannot compute position sizing without valid exposure_pct" per its own error message.

'lambda' is a Python keyword, so modules under test are loaded via importlib.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

market_module = importlib.import_module("lambda.api.routes.algo_handlers.market")
risk_dashboard_module = importlib.import_module("lambda.api.routes.risk_dashboard")


class TestNormalizeExposureRejectsNaN:
    def test_nan_exposure_pct_raises(self):
        with pytest.raises(ValueError, match="outside valid range"):
            market_module._normalize_exposure({"exposure_pct": float("nan"), "regime": "confirmed_uptrend"})

    def test_infinite_exposure_pct_raises(self):
        with pytest.raises(ValueError, match="outside valid range"):
            market_module._normalize_exposure({"exposure_pct": float("inf"), "regime": "confirmed_uptrend"})

    def test_valid_exposure_pct_still_passes(self):
        result = market_module._normalize_exposure({"exposure_pct": 50.0, "regime": "confirmed_uptrend"})
        assert result["exposure_pct"] == 50.0


class TestFetchExposureTierInfoRejectsNaN:
    def test_nan_exposure_pct_raises(self):
        cur = MagicMock()
        with patch.object(
            risk_dashboard_module, "execute_with_timeout",
            return_value=[{
                "exposure_pct": float("nan"), "regime": "confirmed_uptrend", "halt_reasons": None,
                "data_unavailable": False, "reason": None,
            }],
        ):
            with pytest.raises(ValueError, match="CRITICAL"):
                risk_dashboard_module._fetch_exposure_tier_info(cur)

    def test_valid_exposure_pct_still_computes(self):
        cur = MagicMock()
        with patch.object(
            risk_dashboard_module, "execute_with_timeout",
            return_value=[{
                "exposure_pct": 50.0, "regime": "confirmed_uptrend", "halt_reasons": None,
                "data_unavailable": False, "reason": None,
            }],
        ):
            result = risk_dashboard_module._fetch_exposure_tier_info(cur)
        assert result["exposure_pct"] == 50.0
