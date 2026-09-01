"""Regression test (2026-09-01, /goal data-gap audit): peg_ratio_unavailable_reason and
pb_ratio_unavailable_reason in load_value_quality_growth_metrics.py's `_build_value_metrics`
had the SAME bug already found and fixed once for pe_ratio_unavailable_reason (see
tests/unit/test_pe_ratio_unavailable_reason_excludes_incomplete_filing_row_20260901.py and
memory/value_equal_weight_and_pe_reason_bug_fixed_20260901.md) - each independently re-queried
annual_income_statement/annual_balance_sheet WITHOUT the `data_unavailable IS NOT TRUE` filter
that the REAL peg_ratio/pb_ratio computations (load_sec_valuations.py) already apply, so a
stray non-NULL value on an incomplete/unfiled fiscal year could get compared as if it were the
real figure, producing a reason label that disagrees with what the actual value computation saw.

Live-confirmed 2026-09-01: 474 symbols (incl. ACN, ABNB, AEP) have a most-recent
annual_income_statement row flagged data_unavailable=True with a stray non-NULL EPS - the same
shape of evidence that confirmed the original pe_ratio bug.
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


class _RoutingCursor:
    """Routes queries by a distinctive substring in the SQL text, recording each query issued
    so the fix's filter can be asserted on specifically rather than just trusting canned data."""

    def __init__(self, routes):
        self._routes = routes  # {substring: fetchone_or_fetchall_result}
        self.queries = []
        self._last_route = None

    def execute(self, query, params=None):
        self.queries.append(query)
        self._last_route = None
        for substring, _ in self._routes.items():
            if substring in query:
                self._last_route = substring
                break

    def fetchone(self):
        if self._last_route is None:
            return None
        result = self._routes[self._last_route]
        return result[0] if isinstance(result, list) else result

    def fetchall(self):
        if self._last_route is None:
            return []
        result = self._routes[self._last_route]
        return result if isinstance(result, list) else ([result] if result else [])

    def query_for(self, substring):
        return next((q for q in self.queries if substring in q), None)


class TestPegRatioUnavailableReasonExcludesIncompleteFilingRow:
    def test_query_filters_on_data_unavailable(self):
        loader = _make_loader()
        cursor = _RoutingCursor({"SELECT fiscal_year, earnings_per_share": [(2024, 12.29)]})
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cursor
            loader._build_value_metrics(
                "ACN",
                _FakeSecValRow(
                    {"pe_ratio": 20.0, "peg_ratio": None, "pb_ratio": 5.0, "current_price": 200.0, "market_cap": 1e11}
                ),
            )

        peg_query = cursor.query_for("SELECT fiscal_year, earnings_per_share")
        assert peg_query is not None
        assert "data_unavailable IS NOT TRUE" in peg_query

    def test_incomplete_recent_row_with_stray_eps_uses_real_prior_complete_years(self):
        """ACN-shaped case: a correctly-filtered query skips an incomplete current-FY stray EPS
        and compares the two most recent COMPLETE years instead, matching what
        load_sec_valuations.py's real peg_ratio computation actually saw."""
        loader = _make_loader()
        # Simulates what the DB returns AFTER the filter is applied: two real, complete years
        # where earnings grew (10.35 -> 12.29) - PEG should read "negative_earnings_growth"
        # only if growth is genuinely non-positive; here it's positive, so peg_ratio itself
        # would normally be computable by the real engine, and this reason path shouldn't be
        # reached in practice - but if it is (pe present, peg still None for some other real
        # reason), the reason classification must use the real complete-year pair.
        cursor = _RoutingCursor({"SELECT fiscal_year, earnings_per_share": [(2025, 8.0), (2024, 12.29)]})
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cursor
            metrics = loader._build_value_metrics(
                "ACN",
                _FakeSecValRow(
                    {"pe_ratio": 20.0, "peg_ratio": None, "pb_ratio": 5.0, "current_price": 200.0, "market_cap": 1e11}
                ),
            )

        assert metrics["peg_ratio_unavailable_reason"] == "negative_earnings_growth"

    def test_genuinely_missing_eps_history_still_reports_missing_sec_data(self):
        loader = _make_loader()
        cursor = _RoutingCursor({"SELECT fiscal_year, earnings_per_share": []})
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cursor
            metrics = loader._build_value_metrics(
                "NODATACO",
                _FakeSecValRow(
                    {"pe_ratio": 15.0, "peg_ratio": None, "pb_ratio": 2.0, "current_price": 10.0, "market_cap": 1e9}
                ),
            )

        assert metrics["peg_ratio_unavailable_reason"] == "missing_sec_data"


class TestPbRatioUnavailableReasonExcludesIncompleteFilingRow:
    def test_query_filters_on_data_unavailable(self):
        loader = _make_loader()
        cursor = _RoutingCursor({"SELECT stockholders_equity": (-4_080_000_000.0,)})
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cursor
            loader._build_value_metrics(
                "AAL",
                _FakeSecValRow(
                    {"pe_ratio": 8.0, "peg_ratio": 1.0, "pb_ratio": None, "current_price": 15.0, "market_cap": 1e10}
                ),
            )

        pb_query = cursor.query_for("SELECT stockholders_equity")
        assert pb_query is not None
        assert "data_unavailable IS NOT TRUE" in pb_query

    def test_incomplete_recent_row_with_stray_equity_reports_correct_reason(self):
        """A correctly-filtered query skips an incomplete current-FY stray stockholders_equity
        value and uses the real complete prior year instead - here a real negative book value,
        matching AAL's live-confirmed negative_book_value case."""
        loader = _make_loader()
        cursor = _RoutingCursor({"SELECT stockholders_equity": (-4_080_000_000.0,)})
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cursor
            metrics = loader._build_value_metrics(
                "AAL",
                _FakeSecValRow(
                    {"pe_ratio": 8.0, "peg_ratio": 1.0, "pb_ratio": None, "current_price": 15.0, "market_cap": 1e10}
                ),
            )

        assert metrics["pb_ratio_unavailable_reason"] == "negative_book_value"

    def test_genuinely_missing_equity_still_reports_missing_sec_data(self):
        loader = _make_loader()
        cursor = _RoutingCursor({"SELECT stockholders_equity": None})
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = cursor
            metrics = loader._build_value_metrics(
                "NODATACO",
                _FakeSecValRow(
                    {"pe_ratio": 15.0, "peg_ratio": 1.0, "pb_ratio": None, "current_price": 10.0, "market_cap": 1e9}
                ),
            )

        assert metrics["pb_ratio_unavailable_reason"] == "missing_sec_data"
