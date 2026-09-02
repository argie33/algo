"""Regression test (2026-09-01, /goal factor-score review): the pe_ratio_unavailable_reason
query in load_value_quality_growth_metrics.py's `_build_value_metrics` must only consider
annual_income_statement rows that are actually usable (data_unavailable IS NOT TRUE) - the same
filter load_sec_valuations.py's real anchor-row selection already applies when computing
ttm_eps (and therefore whether pe_ratio itself comes back null).

Bug found live via direct user pushback ("you did it because you think a company with no P/E
value is missing the data when in reality just no earnings"): live-scanned the 216-symbol
"missing_sec_data" pe_ratio bucket and found BMBL/WK/BAND/PSKY/AIAI/RKT (and others) each have a
most-recent fiscal year row flagged `data_unavailable=True, reason='incomplete_sec_filing_income'`
that still carries a stray non-null (often positive) earnings_per_share value. The real valuation
engine (load_sec_valuations.py) correctly skips that incomplete row and falls back to the prior,
COMPLETE fiscal year - a genuine loss year (e.g. BMBL FY2025: EPS=-5.95, net_income=-$693M) - to
compute ttm_eps, correctly landing on <=0 and nulling pe_ratio. But this query, lacking the
`data_unavailable` filter, picked up the incomplete row's stray positive EPS instead and
concluded "not unprofitable, must be missing data" - excluding these genuinely unprofitable
companies from Value's P/E scoring entirely instead of correctly flooring them at 0.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    """Minimal stand-in for a psycopg2 DictRow (mapping protocol only)."""

    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _EpsQueryCursor:
    """Routes only the specific pe_ratio_reason EPS lookup (SELECT earnings_per_share ...) to
    a canned row - _build_value_metrics issues several other queries (forward_eps, a revenue-
    completeness check) that also touch annual_income_statement, so routing must key on this
    query's own distinctive SELECT clause, not just the table name. All queries are recorded
    so the fix's SQL text can be asserted on specifically."""

    def __init__(self, eps_row):
        self._eps_row = eps_row
        self.last_query = None
        self.pe_reason_query = None
        self.queries = []

    def execute(self, query, params=None):
        self.last_query = query
        self.queries.append(query)
        if "SELECT earnings_per_share" in query:
            self.pe_reason_query = query

    def fetchone(self):
        if self.last_query and "SELECT earnings_per_share" in self.last_query:
            return self._eps_row
        return None

    def fetchall(self):
        return []


class TestPeRatioUnavailableReasonExcludesIncompleteFilingRow:
    def test_query_filters_on_data_unavailable(self):
        """The fix itself: the SQL must filter out incomplete rows, not just rely on a mock
        returning the "right" row - guards against the filter being silently removed later."""
        loader = _make_loader()
        cursor = _EpsQueryCursor(eps_row=(-5.95,))
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cursor
            loader._build_value_metrics(
                "BMBL",
                _FakeSecValRow(
                    {"pe_ratio": None, "pb_ratio": 0.58, "current_price": 2.74, "market_cap": 301_760_186.70}
                ),
            )

        assert cursor.pe_reason_query is not None
        assert "data_unavailable IS NOT TRUE" in cursor.pe_reason_query

    def test_incomplete_recent_row_with_stray_positive_eps_still_reports_unprofitable(self):
        """Simulates the BMBL-shaped bug: the query (correctly filtered in real SQL) skips the
        incomplete FY2026 row and returns FY2025's real, complete loss-year EPS instead."""
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # A correctly-filtered query would never see FY2026's stray 0.35 - simulate what
            # the DB returns AFTER applying the new filter: the complete loss-year row.
            mock_db_ctx.return_value.__enter__.return_value = _EpsQueryCursor(eps_row=(-5.95,))
            metrics = loader._build_value_metrics(
                "BMBL",
                _FakeSecValRow(
                    {"pe_ratio": None, "pb_ratio": 0.58, "current_price": 2.74, "market_cap": 301_760_186.70}
                ),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "unprofitable_stock"

    def test_genuinely_missing_eps_reports_eps_never_tagged(self):
        """A symbol with NO usable EPS row anywhere in its full filing history (query has no
        fiscal-year window) gets the specific "eps_never_tagged_in_filings" reason - see
        test_pe_ratio_never_tagged_eps_reason_20260902.py for the dedicated regression test
        this label was added by. Not be swept into "unprofitable_stock", and no longer the
        generic "missing_sec_data" either."""
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _EpsQueryCursor(eps_row=None)
            metrics = loader._build_value_metrics(
                "NODATACO",
                _FakeSecValRow(
                    {"pe_ratio": None, "pb_ratio": 2.0, "current_price": 10.0, "market_cap": 1_000_000_000.0}
                ),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "eps_never_tagged_in_filings"

    def test_profitable_company_with_real_pe_is_unaffected(self):
        """Control: a symbol with a real, computed pe_ratio never triggers this query path at
        all - the fix must not touch the common case."""
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            cursor = _EpsQueryCursor(eps_row=(3.0,))
            mock_db_ctx.return_value.__enter__.return_value = cursor
            metrics = loader._build_value_metrics(
                "PROFITCO",
                _FakeSecValRow({"pe_ratio": 18.5, "current_price": 55.5, "market_cap": 2_000_000_000.0}),
            )

        assert metrics["pe_ratio"] == 18.5
        assert cursor.pe_reason_query is None  # EPS-reason query only runs when pe_ratio is None
