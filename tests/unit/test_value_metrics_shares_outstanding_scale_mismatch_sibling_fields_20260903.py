"""Regression test: every shares_outstanding-dependent value_metrics field must surface
sec_valuations.reason == "shares_outstanding_scale_mismatch" verbatim instead of falling
through to the generic "missing_sec_data" label, when the field's own more specific gates
don't already have a genuinely different, real cause.

Found live 2026-09-03 (SEC/XBRL missing-data sweep, sibling of the eps_scale_mismatch fix for
pe_ratio/peg_ratio): load_sec_valuations.py's _sanity_check_market_cap deliberately nulls
market_cap/pb_ratio/ps_ratio/fcf_yield/ev_ebitda/ev_revenue/intrinsic_value_per_share/
margin_of_safety_pct together on a >10x SEC-vs-yfinance market_cap disagreement and records
"shares_outstanding_scale_mismatch" on the sec_valuations row - but whenever the row still
resolves overall (data_unavailable stays False, e.g. pe_ratio survived independently since it
doesn't depend on shares_outstanding), only the whole-row-unavailable early return in
_build_value_metrics ever consulted that reason; each field's own per-field derivation logic
never did, so all of them fell through to "missing_sec_data" instead.

Live-confirmed UHAL/GV/FTW (3 of 16 universe shares_outstanding_scale_mismatch rows with
data_unavailable=False) hit exactly this across market_cap/pb_ratio/ps_ratio/fcf_yield/
ev_revenue (GV's ev_ebitda correctly stayed "unprofitable_stock" - a real, independent cause
that must keep taking priority, verified by the priority-order test below).
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


class _GenericCursor:
    """No symbol-membership gate should fire for a made-up test symbol - every query resolves
    to "nothing found", letting each field's derivation fall through to its final else-branch."""

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []


_BASE_ROW = {
    "pe_ratio": 12.0,
    "peg_ratio": 1.0,
    "pb_ratio": 1.2,
    "ps_ratio": 2.0,
    "current_price": 10.0,
    "reason": "shares_outstanding_scale_mismatch",
}


class TestSharesOutstandingScaleMismatchSiblingFields:
    def test_market_cap_reports_specific_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _GenericCursor()
            metrics = loader._build_value_metrics("TESTCO", _FakeSecValRow({**_BASE_ROW, "market_cap": None}))
        assert metrics["market_cap"] is None
        assert metrics["market_cap_unavailable_reason"] == "shares_outstanding_scale_mismatch"

    def test_ps_ratio_reports_specific_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _GenericCursor()
            metrics = loader._build_value_metrics(
                "TESTCO", _FakeSecValRow({**_BASE_ROW, "ps_ratio": None, "market_cap": 1e9})
            )
        assert metrics["ps_ratio"] is None
        assert metrics["ps_ratio_unavailable_reason"] == "shares_outstanding_scale_mismatch"

    def test_fcf_yield_and_dcf_siblings_report_specific_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _GenericCursor()
            metrics = loader._build_value_metrics(
                "TESTCO",
                _FakeSecValRow(
                    {
                        **_BASE_ROW,
                        "market_cap": 1e9,
                        "fcf_yield": None,
                        "intrinsic_value_per_share": None,
                        "margin_of_safety_pct": None,
                    }
                ),
            )
        assert metrics["fcf_yield"] is None
        assert metrics["fcf_yield_unavailable_reason"] == "shares_outstanding_scale_mismatch"
        # Both cascade from the same fcf_yield_reason_str - see intrinsic_value_reason_from_
        # fcf_yield()'s docstring.
        assert metrics["intrinsic_value_unavailable_reason"] == "shares_outstanding_scale_mismatch"
        assert metrics["margin_of_safety_unavailable_reason"] == "shares_outstanding_scale_mismatch"

    def test_ev_revenue_reports_specific_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _GenericCursor()
            metrics = loader._build_value_metrics(
                "TESTCO", _FakeSecValRow({**_BASE_ROW, "market_cap": 1e9, "ev_revenue": None})
            )
        assert metrics["ev_revenue"] is None
        assert metrics["ev_revenue_unavailable_reason"] == "shares_outstanding_scale_mismatch"

    def test_ev_ebitda_reports_specific_reason_when_no_more_specific_cause(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _GenericCursor()
            metrics = loader._build_value_metrics(
                "TESTCO",
                _FakeSecValRow({**_BASE_ROW, "market_cap": 1e9, "ev_ebitda": None, "ebitda": 5e7}),
            )
        assert metrics["ev_ebitda"] is None
        assert metrics["ev_ebitda_unavailable_reason"] == "shares_outstanding_scale_mismatch"

    def test_ev_ebitda_unprofitable_stock_still_wins_over_scale_mismatch(self):
        """Priority-order regression (GV, live-confirmed): a genuinely negative/zero ebitda is
        an independent, more specific, real cause that must NOT be overwritten by the
        shares_outstanding_scale_mismatch fallback just because that reason also happens to be
        on the row - the fallback only fills the true "no other explanation" gap."""
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _GenericCursor()
            metrics = loader._build_value_metrics(
                "GV", _FakeSecValRow({**_BASE_ROW, "market_cap": 1e9, "ev_ebitda": None, "ebitda": -5e6})
            )
        assert metrics["ev_ebitda"] is None
        assert metrics["ev_ebitda_unavailable_reason"] == "unprofitable_stock"

    def test_pb_ratio_reports_specific_reason_when_equity_history_is_ambiguous(self):
        """pb_ratio's own DB-backed equity-history check must still run and win when it finds a
        genuine negative_book_value/never-tagged cause (see test_pb_ratio_never_tagged_equity_
        reason_20260902.py); this only covers the remaining ambiguous case (a real, positive
        equity value on file, pb still null) that used to fall to generic "missing_sec_data"."""
        loader = _make_loader()

        class _PositiveEquityCursor(_GenericCursor):
            def fetchone(self):
                return (200_000_000.0,)

        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _PositiveEquityCursor()
            metrics = loader._build_value_metrics(
                "TESTCO", _FakeSecValRow({**_BASE_ROW, "market_cap": 1e9, "pb_ratio": None})
            )
        assert metrics["pb_ratio"] is None
        assert metrics["pb_ratio_unavailable_reason"] == "shares_outstanding_scale_mismatch"

    def test_unrelated_reason_does_not_trip_any_new_shortcut(self):
        """A sec_valuations.reason unrelated to shares_outstanding scaling must leave every
        field's normal derivation untouched."""
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _GenericCursor()
            metrics = loader._build_value_metrics(
                "TESTCO",
                _FakeSecValRow(
                    {
                        **_BASE_ROW,
                        "market_cap": None,
                        "ps_ratio": None,
                        "ev_revenue": None,
                        "reason": None,
                    }
                ),
            )
        assert metrics["market_cap_unavailable_reason"] == "missing_sec_data"
        assert metrics["ps_ratio_unavailable_reason"] == "missing_sec_data"
        assert metrics["ev_revenue_unavailable_reason"] == "missing_sec_data"
