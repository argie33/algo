"""Regression: sustainable_growth_rate must treat confirmed non-dividend-payers as
retention_ratio=1.0 instead of unconditionally failing, and must never label a failure
"insufficient_prior_year_data" - it uses no prior-year data at all.

Bug (confirmed live 2026-08-04): SEC XBRL simply omits the PaymentsOfDividends concept
when a company pays no dividends, so dividends_paid reads NULL (not 0) for genuine
non-payers - same "confirmed non-payer vs missing data" ambiguity already resolved for
dividend_yield/payout_ratio via the dividend_data has_real_dividend_history marker, but
never applied to sustainable_growth_rate. Live query: 3212 of 3423 universe-wide
dividends_paid-blocked sustainable_growth_rate NULLs are confirmed non-payers via that
same marker. Separately, every SGR failure was labeled "insufficient_prior_year_data" -
factually wrong, since the SGR formula (stockholders_equity, net_income, dividends_paid)
uses only current-year data, unlike every other field sharing that reason bucket.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=None):
    """31-element quality_row matching _compute_quality_metrics' index layout. current_assets/
    current_liabilities are always populated so current_ratio computes and the function
    doesn't take its "every core metric is None -> whole row unavailable" early exit
    (index 6/7) - everything else is left None so only the SGR computation under test has
    real inputs."""
    row = [None] * 34
    row[0] = stockholders_equity
    row[3] = net_income
    row[6] = 500.0  # current_assets
    row[7] = 100.0  # current_liabilities
    row[15] = dividends_paid
    return row


class _RoutingCursor:
    """Mock cursor whose fetchone() result depends on which table the last query touched -
    _compute_quality_metrics fires several unrelated fallback-year lookups (interest_expense,
    ROIC tax triple, ROIC balance sheet pair) that must all resolve to "no better data
    found" so only the dividend_data lookup under test is exercised."""

    def __init__(self, dividend_history_exists):
        self._dividend_history_exists = dividend_history_exists
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        if "dividend_data" in self._last_query:
            return (1,) if self._dividend_history_exists else None
        return None

    def fetchall(self):
        return []


class TestSustainableGrowthRateNonPayer:
    def test_confirmed_non_payer_computes_sgr_via_full_retention(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(dividend_history_exists=False)
            metrics = loader._compute_quality_metrics(
                "NOPAY", _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=None)
            )
        # ROE = 100/1000 = 10%, retention_ratio = 1.0 (no dividends) -> SGR = 10.0
        assert metrics["sustainable_growth_rate"] == 10.0
        assert metrics.get("sustainable_growth_rate_unavailable_reason") is None

    def test_real_payer_missing_this_year_gets_missing_sec_data_not_prior_year_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(dividend_history_exists=True)
            metrics = loader._compute_quality_metrics(
                "REALPAY", _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=None)
            )
        assert metrics["sustainable_growth_rate"] is None
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "missing_sec_data"

    def test_explicit_dividends_paid_still_used_directly_no_db_lookup(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # dividend_data lookup would raise if hit - dividends_paid is already known (20.0),
            # so no fallback lookup should fire at all.
            cur = _RoutingCursor(dividend_history_exists=False)
            mock_db_ctx.return_value.__enter__.return_value = cur
            metrics = loader._compute_quality_metrics(
                "PAYER", _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=20.0)
            )
        # retention_ratio = 1 - 20/100 = 0.8 -> SGR = 10% * 0.8 * 100 = 8.0
        assert metrics["sustainable_growth_rate"] == 8.0

    def test_missing_stockholders_equity_still_gets_missing_sec_data_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(dividend_history_exists=False)
            metrics = loader._compute_quality_metrics(
                "NOEQ", _quality_row(stockholders_equity=None, net_income=100.0, dividends_paid=None)
            )
        assert metrics["sustainable_growth_rate"] is None
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "missing_sec_data"
