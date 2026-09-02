"""Regression test: pe_ratio_unavailable_reason must distinguish a symbol that has never once
tagged a real earnings_per_share value in its entire filing history from the genuinely
ambiguous "found an EPS value somewhere but pe_ratio still came out null" remainder that
correctly stays "missing_sec_data".

Found live 2026-09-02 (goal: "keep the missing-data number going down" SEC/XBRL audit): the
existing EPS lookup in pe_ratio_reason (SELECT earnings_per_share ... ORDER BY fiscal_year DESC
LIMIT 1, no fiscal-year window - already searches the symbol's full history) already
distinguishes "found a row" from "found nothing" via `eps_row`, but both cases fell into the
same "missing_sec_data" label. Live-verified 39 of the universe's 128 pe_ratio "missing_sec_data"
rows are the "found nothing" case - real filers (BP, FMX, AMTD, JG, CRGY, HESM spot-checked
directly) with real net_income every year but zero earnings_per_share concept ever tagged
(foreign 20-F/IFRS filers and an MLP unit-structure filer among the sample).
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


class _EpsQueryCursor:
    def __init__(self, eps_row):
        self._eps_row = eps_row
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "SELECT earnings_per_share" in self.last_query:
            return self._eps_row
        return None

    def fetchall(self):
        return []


class TestPeRatioNeverTaggedEpsReason:
    def test_no_eps_row_anywhere_reports_eps_never_tagged(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _EpsQueryCursor(eps_row=None)
            metrics = loader._build_value_metrics(
                "BP",
                _FakeSecValRow(
                    {"pe_ratio": None, "pb_ratio": 1.2, "current_price": 30.0, "market_cap": 90_000_000_000.0}
                ),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "eps_never_tagged_in_filings"

    def test_real_negative_eps_still_reports_unprofitable(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _EpsQueryCursor(eps_row=(-1.5,))
            metrics = loader._build_value_metrics(
                "LOSSCO",
                _FakeSecValRow({"pe_ratio": None, "pb_ratio": 0.8, "current_price": 5.0, "market_cap": 500_000_000.0}),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "unprofitable_stock"

    def test_real_positive_eps_with_pe_still_null_keeps_generic_reason(self):
        """A real, positive EPS was found (pe should have been computable) but pe_ratio is
        still None for some other reason (e.g. a bound/price anomaly) - stays the genuinely
        ambiguous generic label, not swept into the new specific one."""
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _EpsQueryCursor(eps_row=(2.5,))
            metrics = loader._build_value_metrics(
                "AMBIGCO",
                _FakeSecValRow(
                    {"pe_ratio": None, "pb_ratio": 1.0, "current_price": 10.0, "market_cap": 1_000_000_000.0}
                ),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "missing_sec_data"
