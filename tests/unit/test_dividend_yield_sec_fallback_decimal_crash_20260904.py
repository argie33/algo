"""Regression test (2026-09-04, same Decimal/float class as the fcf_margin fallback fix in
_compute_quality_metrics): the TIER 2 SEC dividend_data fallback did `sec_div_row[0] / 100.0`
on a raw psycopg2 Decimal (dividend_yield_pct is NUMERIC) - `Decimal / float` raises TypeError,
silently caught by this fallback's own narrow try/except and logged at debug level, so this
tier never actually populated dividend_yield for any symbol that reached it.
"""

from decimal import Decimal
from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return False
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _RoutingCursor:
    """Returns a real Decimal dividend_yield_pct for the dividend_data TIER 2 query, "no data"
    for everything else."""

    def __init__(self, dividend_yield_pct):
        self._dividend_yield_pct = dividend_yield_pct
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "FROM dividend_data" in self.last_query:
            return (self._dividend_yield_pct,)
        return None

    def fetchall(self):
        return []


class TestDividendYieldSecFallbackDecimalCrash:
    def test_decimal_dividend_yield_pct_does_not_crash_and_computes_real_value(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RoutingCursor(dividend_yield_pct=Decimal("3.25"))
            metrics = loader._build_value_metrics(
                "SYM",
                _FakeSecValRow({"pe_ratio": 12.0, "dividend_yield": None, "market_cap": None}),
            )

        assert metrics["dividend_yield"] == 0.0325
        assert metrics["dividend_yield_unavailable_reason"] is None
