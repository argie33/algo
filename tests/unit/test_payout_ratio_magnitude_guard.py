"""Regression test for the 2026-08-17 fix: payout_ratio (dividends_paid / net_income * 100)
had no magnitude guard, unlike every other ratio field in
ValueQualityGrowthMetricsLoader._compute_quality_metrics(). A near-zero (but still positive)
net_income denominator lets the ratio explode arbitrarily.

Live-reproduced on GLPI: payout_ratio computed to 105,668,646.22%, which then crashed the
quality_metrics INSERT with psycopg2.errors.NumericValueOutOfRange (the column is
NUMERIC(10,2), max ~1e8) - a live "loud" failure in tonight's scheduler_invocations.log.

Fixed by applying the same |ratio| <= 1000% sanity bound already used for margin fields
elsewhere in this function, treating an implausible ratio as unavailable
(reason="implausible_ratio") instead of attempting to persist it.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(net_income, dividends_paid):
    """31+-element quality_row matching _compute_quality_metrics' index layout - see
    test_sustainable_growth_rate_dividend_reason.py's identical helper for the index map."""
    row = [None] * 34
    row[0] = 1000.0  # stockholders_equity
    row[3] = net_income
    row[6] = 500.0  # current_assets
    row[7] = 100.0  # current_liabilities
    row[15] = dividends_paid
    return row


class _RoutingCursor:
    """Mock cursor that returns "no better data found" for every fallback-year lookup
    _compute_quality_metrics fires (interest_expense, ROIC tax triple, ROIC balance sheet
    pair, dividend_data history) - matches
    test_sustainable_growth_rate_dividend_reason.py's identical helper."""

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class TestPayoutRatioMagnitudeGuard:
    def test_extreme_ratio_from_near_zero_net_income_is_rejected_not_inserted(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor()
            # Mirrors GLPI: tiny positive net_income against real dividends explodes the ratio.
            metrics = loader._compute_quality_metrics("GLPI", _quality_row(net_income=0.001, dividends_paid=1000.0))

        assert metrics.get("payout_ratio") is None
        assert metrics.get("payout_ratio_unavailable_reason") == "implausible_ratio"

    def test_normal_ratio_still_computes(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor()
            metrics = loader._compute_quality_metrics("NORMAL", _quality_row(net_income=100.0, dividends_paid=40.0))

        assert metrics["payout_ratio"] == 40.0
        assert metrics.get("payout_ratio_unavailable_reason") is None

    def test_ratio_exactly_at_boundary_is_accepted(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor()
            # dividends_paid / net_income * 100 == 1000.0 exactly (the inclusive bound).
            metrics = loader._compute_quality_metrics("EDGE", _quality_row(net_income=1.0, dividends_paid=10.0))

        assert metrics["payout_ratio"] == 1000.0
        assert metrics.get("payout_ratio_unavailable_reason") is None
