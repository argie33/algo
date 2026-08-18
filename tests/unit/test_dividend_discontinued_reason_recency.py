"""Regression test: dividend_yield/payout_ratio/sustainable_growth_rate "confirmed non-payer vs
missing data" classification must use a recency window on dividend_data, not "ever paid, at any
point in history".

Found live 2026-08-18 (ENVA dashboard screenshot, goal: "no SEC data" audit): ENVA has real
dividend payments on file for 2014-2016 but none since (10 straight years). All three call
sites shared the same `SELECT 1 FROM dividend_data WHERE symbol = %s AND data_unavailable =
FALSE LIMIT 1` query with no date filter, so "has paid at some point" was treated as proof the
metric's current NULL must be a genuine SEC extraction gap ("missing_sec_data") - reading as a
loader bug even though ENVA simply stopped paying a dividend a decade ago, the same "stock
characteristic, not a data gap" class as a company that never paid at all. Fixed by requiring
the matched dividend_data row's ex_dividend_date to fall within the last 2 years.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(net_income=100.0, dividends_paid=None):
    """34-element quality_row (index 33 = prior_year_gross_profit, added after this fixture was
    written) - see test_sustainable_growth_rate_dividend_reason.py's identical helper for the
    index map."""
    row = [None] * 34
    row[0] = 1000.0  # stockholders_equity
    row[3] = net_income
    row[6] = 500.0  # current_assets
    row[7] = 100.0  # current_liabilities
    row[15] = dividends_paid
    return row


class _RecordingCursor:
    """Records every executed query and always reports "no data found" downstream, so the
    dividend_data classification query is reached with dividend_yield/dividends_paid still None
    - matches test_sustainable_growth_rate_dividend_reason.py's _RoutingCursor pattern, but
    records the full query list instead of routing a canned answer."""

    def __init__(self, queries):
        self._queries = queries

    def execute(self, query, params=None):
        self._queries.append(query)

    def fetchone(self):
        return None

    def fetchall(self):
        return []


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


class TestDividendReasonRecencyWindow:
    def test_dividend_yield_reason_query_windows_to_recent_years(self):
        loader = _make_loader()
        queries: list = []
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RecordingCursor(queries)
            loader._build_value_metrics("ENVA", _FakeSecValRow({"pe_ratio": 15.0, "dividend_yield": None}))

        dividend_queries = [q for q in queries if "dividend_data" in q and "dividend_yield_pct" not in q]
        assert dividend_queries, "expected a dividend_data classification query"
        assert all("INTERVAL '2 years'" in q for q in dividend_queries)

    def test_payout_ratio_reason_query_windows_to_recent_years(self):
        loader = _make_loader()
        queries: list = []
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RecordingCursor(queries)
            loader._compute_quality_metrics("ENVA", _quality_row(net_income=100.0, dividends_paid=None))

        dividend_queries = [q for q in queries if "dividend_data" in q]
        assert dividend_queries, "expected a dividend_data classification query"
        assert any("INTERVAL '2 years'" in q for q in dividend_queries)

    def test_sgr_reason_query_windows_to_recent_years(self):
        loader = _make_loader()
        queries: list = []
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RecordingCursor(queries)
            loader._compute_quality_metrics("ENVA", _quality_row(net_income=100.0, dividends_paid=None))

        dividend_queries = [q for q in queries if "dividend_data" in q]
        assert dividend_queries, "expected a dividend_data classification query"
        assert any("INTERVAL '2 years'" in q for q in dividend_queries)

    def test_discontinued_payer_treated_same_as_never_paid(self):
        # A symbol with dividend_data rows that are all older than 2 years must be treated
        # identically to a symbol with zero dividend_data rows at all: dividend_yield=0.0,
        # reason="non_dividend_paying_stock" - never "missing_sec_data".
        loader = _make_loader()

        class _NoRecentDividendCursor:
            def execute(self, query, params=None):
                pass

            def fetchone(self):
                return None  # the recency-windowed query finds nothing

            def fetchall(self):
                return []

        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _NoRecentDividendCursor()
            metrics = loader._build_value_metrics("ENVA", _FakeSecValRow({"pe_ratio": 15.0, "dividend_yield": None}))

        assert metrics["dividend_yield"] == 0.0
        assert metrics["dividend_yield_unavailable_reason"] == "non_dividend_paying_stock"
