"""Regression: dividends_paid must not be silently discarded when annual_cash_flow's row for
that fiscal year is flagged data_unavailable=TRUE for an unrelated reason.

Root cause (live-confirmed 2026-08-18, DD/DuPont): the shared anchor-row query in
load_value_quality_growth_metrics.py joins `annual_cash_flow acf ON ... AND
acf.data_unavailable = FALSE`. load_financial_statements.py marks a cashflow row
data_unavailable=TRUE ("incomplete_sec_filing_cashflow") whenever operating_cash_flow (the
one REQUIRED cashflow field) is missing that year - even when dividends_paid was
successfully extracted and is sitting right there in the same row. DD's FY2025 has real
dividends_paid=$597M but operating_cash_flow untagged that year, so the JOIN filter silently
discarded dividends_paid too, killing sustainable_growth_rate/payout_ratio even though
nothing about dividends was actually missing. Universe-wide: 671 symbols have a real
dividends_paid value trapped behind this exact flag.

Fix: when the anchor row's dividends_paid comes back None, do a same-fiscal-year (never
mixes years) lookup directly against annual_cash_flow without the data_unavailable filter.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=None, fiscal_year=2025):
    """34-element quality_row matching _compute_quality_metrics' index layout.
    current_assets/current_liabilities are always populated so current_ratio computes and the
    function doesn't take its "every core metric is None -> whole row unavailable" early exit."""
    row = [None] * 34
    row[0] = stockholders_equity
    row[3] = net_income
    row[6] = 500.0  # current_assets
    row[7] = 100.0  # current_liabilities
    row[8] = fiscal_year
    row[15] = dividends_paid
    return row


class _RoutingCursor:
    """Mock cursor whose fetchone() result depends on which table the last query touched -
    _compute_quality_metrics fires several unrelated fallback-year lookups that must all
    resolve to "no better data found" so only the annual_cash_flow lookup under test fires."""

    def __init__(self, cash_flow_dividends_paid=None, dividend_history_exists=False):
        self._cash_flow_dividends_paid = cash_flow_dividends_paid
        self._dividend_history_exists = dividend_history_exists
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        if "annual_cash_flow" in self._last_query and "dividends_paid" in self._last_query:
            return (self._cash_flow_dividends_paid,) if self._cash_flow_dividends_paid is not None else None
        if "dividend_data" in self._last_query:
            return (1,) if self._dividend_history_exists else None
        return None

    def fetchall(self):
        return []


class TestSustainableGrowthRateIncompleteCashflowRowFallback:
    def test_incomplete_cashflow_row_dividends_paid_is_recovered(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(cash_flow_dividends_paid=20.0)
            metrics = loader._compute_quality_metrics(
                "DD", _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=None)
            )
        # ROE = 100/1000 = 10%, retention_ratio = 1 - 20/100 = 0.8 -> SGR = 8.0, same math as
        # the "explicit dividends_paid" control case in the sibling non-payer test file.
        assert metrics["sustainable_growth_rate"] == 8.0
        assert metrics.get("sustainable_growth_rate_unavailable_reason") is None

    def test_no_cash_flow_row_at_all_still_falls_through_to_confirmed_non_payer_path(self):
        # Control: no annual_cash_flow fallback row AND no dividend_data history -> unchanged
        # behavior, confirmed non-payer, full retention (matches the sibling non-payer test).
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(
                cash_flow_dividends_paid=None, dividend_history_exists=False
            )
            metrics = loader._compute_quality_metrics(
                "NOPAY", _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=None)
            )
        assert metrics["sustainable_growth_rate"] == 10.0
        assert metrics.get("sustainable_growth_rate_unavailable_reason") is None

    def test_explicit_dividends_paid_skips_fallback_query_entirely(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # cash_flow_dividends_paid deliberately set to a DIFFERENT value (999.0) - if the
            # fallback query fired despite dividends_paid already being known, this would leak
            # in and change the result. It must not.
            cur = _RoutingCursor(cash_flow_dividends_paid=999.0)
            mock_db_ctx.return_value.__enter__.return_value = cur
            metrics = loader._compute_quality_metrics(
                "PAYER", _quality_row(stockholders_equity=1000.0, net_income=100.0, dividends_paid=20.0)
            )
        assert metrics["sustainable_growth_rate"] == 8.0
