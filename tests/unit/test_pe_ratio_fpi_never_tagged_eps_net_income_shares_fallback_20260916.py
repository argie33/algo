"""Regression test: pe_ratio_unavailable_reason must fall back to an EPS derived from
net_income / shares_outstanding for a foreign private issuer that never tags ANY EPS
concept - annual OR quarterly - before concluding "eps_never_tagged_in_filings".

Live-confirmed 2026-09-16 via AZI: a real 20-F filer with real, non-null net_income every
fiscal year and a real, live yfinance-resolved shares_outstanding, but zero
EarningsPerShareBasic/Diluted facts anywhere in its SEC filing history (neither
_fetch_ttm_eps_from_quarterly's 4-real-quarters path nor the plain annual lookup finds
anything). load_sec_valuations.py already has an equivalent fallback
(_derive_fpi_eps_from_resolved_shares) for its own separate pe_ratio computation, but this
loader's independent reason-cascade never called into it, so a symbol with everything needed
to compute a real answer was mislabeled with the generic "eps_never_tagged_in_filings" gap
label instead of routing through the same unprofitable_stock/real-pe branches every other
latest_eps-having symbol gets.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _FpiEpsQueryCursor:
    """Routes by which query string is executed - same convention as the sibling
    test file's _EpsQueryCursor, extended with the FPI/net_income lookups this new
    fallback adds."""

    def __init__(self, is_fpi: bool, net_income, shares_out_available: bool = True):
        self._is_fpi = is_fpi
        self._net_income = net_income
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "is_foreign_private_issuer" in self.last_query:
            return (self._is_fpi,)
        if self.last_query and "annual_income_statement" in self.last_query and "net_income" in self.last_query:
            return (self._net_income,) if self._net_income is not None else None
        return None

    def fetchall(self):
        return []


class TestPeRatioFpiNeverTaggedEpsFallback:
    def test_profitable_fpi_never_tagging_eps_gets_a_real_pe_ratio_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _FpiEpsQueryCursor(is_fpi=True, net_income=10_000_000.0)
            metrics = loader._build_value_metrics(
                "PROFITFPI",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "pb_ratio": 1.2,
                        "current_price": 5.0,
                        "market_cap": 100_000_000.0,
                        "shares_outstanding": 10_000_000.0,
                    }
                ),
            )

        # derived EPS = 10,000,000 / 10,000,000 = 1.0, a real positive figure - must not stay
        # on the generic "never tagged" gap label.
        assert metrics["pe_ratio_unavailable_reason"] != "eps_never_tagged_in_filings"

    def test_loss_making_fpi_never_tagging_eps_reports_unprofitable_not_never_tagged(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _FpiEpsQueryCursor(is_fpi=True, net_income=-16_573_000.0)
            metrics = loader._build_value_metrics(
                "AZI",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "pb_ratio": 1.2,
                        "current_price": 5.0,
                        "market_cap": 100_000_000.0,
                        "shares_outstanding": 56_288_753.0,
                    }
                ),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "unprofitable_stock"

    def test_domestic_filer_never_tagging_eps_keeps_never_tagged_reason(self):
        """The FPI-only guard must not fire for a domestic filer - a real domestic
        10-K/10-Q filer genuinely missing EPS everywhere stays on the honest gap label."""
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _FpiEpsQueryCursor(is_fpi=False, net_income=10_000_000.0)
            metrics = loader._build_value_metrics(
                "DOMESTIC",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "pb_ratio": 1.2,
                        "current_price": 5.0,
                        "market_cap": 100_000_000.0,
                        "shares_outstanding": 10_000_000.0,
                    }
                ),
            )

        assert metrics["pe_ratio_unavailable_reason"] == "eps_never_tagged_in_filings"
