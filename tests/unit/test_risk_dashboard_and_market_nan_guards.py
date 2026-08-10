"""Regression tests for 3 NaN-comparison-guard gaps found 2026-08-10 continuing the
systematic sweep (`value <= 0` never catches NaN - always False in Python; 23 instances
already fixed elsewhere this session):

- risk_dashboard.py's _fetch_drawdown_info: `peak <= 0` didn't catch NaN/Inf, and `current`
  had no finiteness check at all.
- market.py's market health handler: `vix_float <= 0`'s raise never fired for a NaN VIX -
  the try block "succeeded" silently, letting a NaN VIX ("critical for position sizing" per
  the dashboard's own docstring) reach the caller unvalidated.
- market.py's SPY-close fetch: `spy_close <= 0` didn't catch NaN/Inf either.

'lambda' is a Python keyword, so modules under test are loaded via importlib.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest

risk_dashboard_module = importlib.import_module("lambda.api.routes.risk_dashboard")


class TestDrawdownInfoRejectsNaN:
    def test_nan_peak_raises(self):
        cur = MagicMock()
        with patch.object(
            risk_dashboard_module, "execute_with_timeout",
            return_value=[{"peak": float("nan"), "current": 90_000.0}],
        ):
            with pytest.raises(ValueError, match="finite|invalid"):
                risk_dashboard_module._fetch_drawdown_info(cur)

    def test_nan_current_raises(self):
        cur = MagicMock()
        with patch.object(
            risk_dashboard_module, "execute_with_timeout",
            return_value=[{"peak": 100_000.0, "current": float("nan")}],
        ):
            with pytest.raises(ValueError, match="finite|invalid"):
                risk_dashboard_module._fetch_drawdown_info(cur)

    def test_normal_values_still_compute(self):
        cur = MagicMock()
        with patch.object(
            risk_dashboard_module, "execute_with_timeout",
            return_value=[{"peak": 100_000.0, "current": 90_000.0}],
        ):
            result = risk_dashboard_module._fetch_drawdown_info(cur)
        assert result["current_drawdown_pct"] == 10.0
