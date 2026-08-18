"""Regression test for the 2026-08-18 dividend_yield cash-flow fallback fix.

dividend_data (per-share/ex-dividend-date XBRL concepts) and annual_cash_flow (the
financing-activities "dividends paid" cash-flow-statement line, sourced independently by
load_financial_statements.py) are two separate extractions. Live-confirmed 153 universe
symbols (incl. HSBC, SHEL, BHP, VOD - all real, well-known dividend payers) had a real,
recent, positive annual_cash_flow.dividends_paid figure while dividend_data had no usable
row, so the classification logic fell through to "non_dividend_paying_stock" - a factually
wrong label for a company that demonstrably paid a real dividend. Fixed with a TIER 3
fallback: aggregate yield = dividends_paid / market_cap when dividend_data has nothing.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    """Minimal stand-in for a psycopg2 DictRow: supports sec_val_row[2] (data_unavailable flag,
    positional) and dict(sec_val_row) (mapping protocol) simultaneously."""

    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return False
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _RoutingCursor:
    """Returns a real dividends_paid row for the annual_cash_flow query, "no data" for
    everything else (dividend_data TIER 2, forward_pe, etc.)."""

    def __init__(self, dividends_paid):
        self._dividends_paid = dividends_paid
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "annual_cash_flow" in self.last_query:
            return (self._dividends_paid,)
        return None

    def fetchall(self):
        return []


class TestDividendYieldCashFlowFallback:
    def test_computes_aggregate_yield_from_cash_flow_when_dividend_data_missing(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(dividends_paid=500_000_000.0)
            metrics = loader._build_value_metrics(
                "SHEL",
                _FakeSecValRow({"pe_ratio": 12.0, "dividend_yield": None, "market_cap": 10_000_000_000.0}),
            )

        assert metrics["dividend_yield"] == 0.05
        assert metrics["dividend_yield_unavailable_reason"] is None

    def test_no_fallback_without_market_cap(self):
        # Without market_cap the aggregate-yield formula has no denominator - must fall
        # through to the existing non-payer/missing-data classification, not crash.
        loader = _make_loader()

        class _NoDataCursor:
            def execute(self, query, params=None):
                pass

            def fetchone(self):
                return None

            def fetchall(self):
                return []

        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _NoDataCursor()
            metrics = loader._build_value_metrics("ENVA", _FakeSecValRow({"pe_ratio": 15.0, "dividend_yield": None}))

        assert metrics["dividend_yield"] == 0.0
        assert metrics["dividend_yield_unavailable_reason"] == "non_dividend_paying_stock"
