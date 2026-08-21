"""Regression test for the 2026-08-21 fix: RiskMetricsLoader.beta_unavailable_reason was
hardcoded to the single generic string "missing_price_data" regardless of which real cause
_get_beta_from_db actually reported, live-confirmed on 100% of 217 null-beta stability_metrics
rows. _get_beta_from_db already computes a specific reason for every failure mode
(spy_price_data_insufficient/insufficient_common_dates/insufficient_returns/
spy_variance_zero/extreme_beta/db_beta_error) - the bug was in the caller discarding it before
writing to the DB column the coverage report and dashboard actually read.
"""

from datetime import date

from loaders.load_risk_metrics_daily import RiskMetricsLoader


def _dates(n: int) -> list[date]:
    return [date(2026, 1, 1 + i) for i in range(n)]


class TestGetBetaFromDbReasons:
    def test_insufficient_spy_history_reason(self):
        stock_prices = [(d, 100.0 + i) for i, d in enumerate(_dates(30))]
        spy_rows = [(d, 400.0 + i) for i, d in enumerate(_dates(3))]  # < min_spy_days=5
        result = RiskMetricsLoader._get_beta_from_db("TEST", stock_prices, spy_rows)
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"].startswith("spy_price_data_insufficient")

    def test_insufficient_common_dates_reason(self):
        stock_prices = [(date(2026, 1, 1 + i), 100.0 + i) for i in range(10)]
        spy_rows = [(date(2026, 3, 1 + i), 400.0 + i) for i in range(10)]  # no date overlap
        result = RiskMetricsLoader._get_beta_from_db("TEST", stock_prices, spy_rows)
        assert isinstance(result, dict)
        assert result["reason"].startswith("insufficient_common_dates")

    def test_extreme_beta_reason(self):
        dates = _dates(10)
        # SPY barely moves; stock swings wildly on the same dates -> |beta| > 10
        spy_rows = [(d, 400.0 + (0.0001 * i)) for i, d in enumerate(dates)]
        stock_prices = [(d, 100.0 * (1.5 if i % 2 == 0 else 0.7)) for i, d in enumerate(dates)]
        result = RiskMetricsLoader._get_beta_from_db("TEST", stock_prices, spy_rows)
        assert isinstance(result, dict)
        assert result["reason"].startswith("extreme_beta")
