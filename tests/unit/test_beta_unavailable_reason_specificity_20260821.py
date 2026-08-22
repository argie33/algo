"""Regression test for the 2026-08-21 fix: RiskMetricsLoader.beta_unavailable_reason was
hardcoded to the single generic string "missing_price_data" regardless of which real cause
_get_beta_from_db actually reported, live-confirmed on 100% of 217 null-beta stability_metrics
rows. _get_beta_from_db already computes a specific reason for every failure mode
(spy_price_data_insufficient/insufficient_common_dates/insufficient_returns/
spy_variance_zero/extreme_beta/db_beta_error) - the bug was in the caller discarding it before
writing to the DB column the coverage report and dashboard actually read.
"""

from datetime import date, timedelta

from loaders.load_risk_metrics_daily import RiskMetricsLoader


def _dates(n: int) -> list[date]:
    return [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]


class TestGetBetaFromDbReasons:
    def test_insufficient_spy_history_reason(self):
        stock_prices = [(d, 100.0 + i) for i, d in enumerate(_dates(30))]
        spy_rows = [(d, 400.0 + i) for i, d in enumerate(_dates(3))]  # < min_spy_days=61
        result = RiskMetricsLoader._get_beta_from_db("TEST", stock_prices, spy_rows)
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True
        assert result["reason"].startswith("spy_price_data_insufficient")

    def test_60_days_still_insufficient(self):
        """Regression test for the 2026-08-22 fix: raised the beta sample-size floor from
        4-5 return observations (a divide-by-zero guard, not a real reliability check) to the
        same 60-return floor volatility_252d already enforces in this same file. Exactly 60
        overlapping days (59 returns after np.diff) must still be rejected - one below the
        real floor, not the old one.

        Uses the same deterministic exact-beta=1.2 construction as
        test_61_overlapping_days_computes_real_beta below (not a plain linear price series -
        that coincidentally computes an implausible beta>10 for a 60-day window regardless of
        the sample-size floor, via the unrelated extreme_beta path, which would make this test
        pass even against the pre-fix code without actually exercising the fix)."""
        import math

        dates = _dates(60)
        spy_returns = [0.004 if i % 2 == 0 else -0.003 for i in range(59)]
        stock_returns = [1.2 * r for r in spy_returns]
        spy_prices = [400.0]
        stock_prices_vals = [100.0]
        for r in spy_returns:
            spy_prices.append(spy_prices[-1] * math.exp(r))
        for r in stock_returns:
            stock_prices_vals.append(stock_prices_vals[-1] * math.exp(r))
        spy_rows = list(zip(dates, spy_prices, strict=True))
        stock_prices = list(zip(dates, stock_prices_vals, strict=True))

        result = RiskMetricsLoader._get_beta_from_db("TEST", stock_prices, spy_rows)
        assert isinstance(result, dict)
        assert result["data_unavailable"] is True

    def test_61_overlapping_days_computes_real_beta(self):
        """The other side of the same fix: 61 overlapping days (60 returns) is the real,
        intended floor - a symbol with exactly enough history must still get a real beta,
        not be over-rejected by the fix."""
        import math

        dates = _dates(61)
        # Deterministic log-returns (stock = exactly 1.2x SPY's return each day, alternating
        # sign so SPY has real variance) give an exact, stable beta=1.2 - avoids the log-return
        # curvature artifacts a plain linear price series produces over many days, which would
        # otherwise make this fixture flaky rather than a clean test of the sample-size floor.
        spy_returns = [0.004 if i % 2 == 0 else -0.003 for i in range(60)]
        stock_returns = [1.2 * r for r in spy_returns]
        spy_prices = [400.0]
        stock_prices_vals = [100.0]
        for r in spy_returns:
            spy_prices.append(spy_prices[-1] * math.exp(r))
        for r in stock_returns:
            stock_prices_vals.append(stock_prices_vals[-1] * math.exp(r))
        spy_rows = list(zip(dates, spy_prices, strict=True))
        stock_prices = list(zip(dates, stock_prices_vals, strict=True))

        result = RiskMetricsLoader._get_beta_from_db("TEST", stock_prices, spy_rows)
        assert isinstance(result, float)
        assert abs(result - 1.2) < 0.01

    def test_insufficient_common_dates_reason(self):
        # Both lists individually clear the (raised 2026-08-22) 61-row spy_price_data_insufficient
        # floor, but share zero overlapping dates - must fall through to the next, more specific
        # check instead of being caught by the first one.
        stock_prices = [(date(2026, 1, 1) + timedelta(days=i), 100.0 + i) for i in range(65)]
        spy_rows = [(date(2026, 6, 1) + timedelta(days=i), 400.0 + i) for i in range(65)]  # no date overlap
        result = RiskMetricsLoader._get_beta_from_db("TEST", stock_prices, spy_rows)
        assert isinstance(result, dict)
        assert result["reason"].startswith("insufficient_common_dates")

    def test_extreme_beta_reason(self):
        # 65 overlapping dates clears the 2026-08-22 61-return floor (a real, not merely
        # divide-by-zero-avoiding, sample size) while still producing a genuinely implausible
        # beta: SPY barely moves; stock swings wildly on the same dates -> |beta| > 10.
        dates = _dates(65)
        spy_rows = [(d, 400.0 + (0.0001 * i)) for i, d in enumerate(dates)]
        stock_prices = [(d, 100.0 * (1.5 if i % 2 == 0 else 0.7)) for i, d in enumerate(dates)]
        result = RiskMetricsLoader._get_beta_from_db("TEST", stock_prices, spy_rows)
        assert isinstance(result, dict)
        assert result["reason"].startswith("extreme_beta")
