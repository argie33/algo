"""Regression tests for 2 NaN-comparison-guard gaps in lambda/api/routes/algo_handlers/signals.py,
found 2026-08-10 continuing the systematic sweep (`value <= 0` never catches NaN - always
False in Python; 19 instances already fixed elsewhere this session).

- _validate_portfolio_snapshot: bare float() on total_portfolio_value bypassed this same
  module's already-imported safe_float() helper (utils/validation/framework.py), which
  explicitly rejects NaN/Infinity. `not portfolio_value or portfolio_value <= 0` never
  caught NaN - it would have silently produced a NaN pct_of_portfolio in the pre-trade
  impact response.
- _calculate_pre_trade_impact's entry_price DB fallback: same bug, would have reached
  `int(position_dollars / entry_price)` unguarded (`entry_price <= 0` doesn't catch NaN).

'lambda' is a Python keyword, so the module under test is loaded via importlib.
"""

import importlib
from unittest.mock import MagicMock, patch

signals_module = importlib.import_module("lambda.api.routes.algo_handlers.signals")


class TestValidatePortfolioSnapshotRejectsNaN:
    def test_nan_portfolio_value_returns_error_not_none_data(self):
        cur = MagicMock()
        cur.fetchone.return_value = {"total_portfolio_value": float("nan"), "position_count": 5}
        data, error = signals_module._validate_portfolio_snapshot(cur)
        assert data is None
        assert error is not None

    def test_infinite_portfolio_value_returns_error(self):
        cur = MagicMock()
        cur.fetchone.return_value = {"total_portfolio_value": float("inf"), "position_count": 5}
        data, error = signals_module._validate_portfolio_snapshot(cur)
        assert data is None
        assert error is not None

    def test_normal_portfolio_value_still_accepted(self):
        cur = MagicMock()
        cur.fetchone.return_value = {"total_portfolio_value": 100_000.0, "position_count": 5}
        data, error = signals_module._validate_portfolio_snapshot(cur)
        assert error is None
        assert data[1] == 100_000.0


class TestPreTradeImpactRejectsNaNEntryPriceFallback:
    def test_nan_price_daily_close_fallback_rejected(self):
        cur = MagicMock()
        cur.fetchone.return_value = (float("nan"),)
        body = {"symbol": "AAPL", "position_dollars": 1000.0}
        with patch.object(
            signals_module, "_validate_portfolio_snapshot",
            return_value=(({}, 100_000.0, 5), None),
        ):
            result = signals_module._calculate_pre_trade_impact(cur, body)
        # Must not crash with an unhandled exception (int(NaN) raises ValueError) and must
        # not silently succeed with a corrupted response - a clean error_response instead.
        assert result["statusCode"] != 200
