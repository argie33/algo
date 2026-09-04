"""Regression test: ps_ratio_unavailable_reason must recognize when a real, positive revenue
combined with the row's own shares_outstanding/current_price pushes the recomputed ratio outside
load_sec_valuations.py's own MIN_PLAUSIBLE_PS_RATIO(0.05)..10000 bound - the same
"implausible_ratio" treatment just added to pb_ratio_reason
(test_pb_ratio_never_tagged_tuple_null_and_implausible_bound_20260904.py), never applied here.

Found 2026-09-04 (goal: "Missing SEC/XBRL data" reduction to zero). load_sec_valuations.py
silently logs and leaves ps_ratio/reason both NULL when the computed ratio falls outside that
bound - no way for this reason chain to distinguish it from a genuine extraction gap. Live-
confirmed ACHR (FY2025 revenue=$300K against 624M shares outstanding - a real pre-revenue
aerospace filer, ps~11895, above the 10000 upper bound) and CWH (real $6.37B revenue but a
Class-A-only shares_outstanding figure, ps~0.043, below the 0.05 lower bound - a share-class
mismatch producing the same symptom) fell to generic "missing_sec_data".
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


class _RevenueQueryCursor:
    def __init__(self, revenue_row, no_recent_revenue_symbols=frozenset()):
        self._revenue_row = revenue_row
        self._no_recent_revenue = no_recent_revenue_symbols
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "SELECT revenue" in self.last_query:
            return self._revenue_row
        return None

    def fetchall(self):
        if self.last_query and "annual_income_statement" in self.last_query and "revenue" in self.last_query:
            return [(s,) for s in self._no_recent_revenue]
        return []


class TestPsRatioImplausibleBound:
    def test_real_tiny_revenue_reports_implausible_ratio(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # ACHR-shaped: real $300K revenue against 624.3M shares -> rps~=$0.00048,
            # ps = 5.71 / 0.00048 ~= 11895 (> 10000 upper bound).
            mock_db_ctx.return_value.__enter__.return_value = _RevenueQueryCursor(revenue_row=(300_000.0,))
            metrics = loader._build_value_metrics(
                "ACHR",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "peg_ratio": None,
                        "pb_ratio": 3.0,
                        "ps_ratio": None,
                        "current_price": 5.71,
                        "market_cap": 3.5e9,
                        "shares_outstanding": 624_307_768.0,
                    }
                ),
            )

        assert metrics["ps_ratio"] is None
        assert metrics["ps_ratio_unavailable_reason"] == "implausible_ratio"

    def test_real_revenue_below_lower_bound_reports_implausible_ratio(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # CWH-shaped: real $6.37B revenue but a tiny Class-A-only share count ->
            # rps~=$161.7, ps = 6.96 / 161.7 ~= 0.043 (< 0.05 lower bound).
            mock_db_ctx.return_value.__enter__.return_value = _RevenueQueryCursor(revenue_row=(6_369_149_000.0,))
            metrics = loader._build_value_metrics(
                "CWH",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "peg_ratio": None,
                        "pb_ratio": 3.0,
                        "ps_ratio": None,
                        "current_price": 6.96,
                        "market_cap": 2.7e8,
                        "shares_outstanding": 39_383_000.0,
                    }
                ),
            )

        assert metrics["ps_ratio"] is None
        assert metrics["ps_ratio_unavailable_reason"] == "implausible_ratio"

    def test_real_revenue_with_plausible_ratio_keeps_generic_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # rps = 1e9 / 100e6 shares = $10, price $10 -> ps = 1.0, well within bounds - this
            # symbol's ps still came out null for some other, genuinely ambiguous reason.
            mock_db_ctx.return_value.__enter__.return_value = _RevenueQueryCursor(revenue_row=(1_000_000_000.0,))
            metrics = loader._build_value_metrics(
                "PLAUSIBLECO",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "peg_ratio": None,
                        "pb_ratio": 3.0,
                        "ps_ratio": None,
                        "current_price": 10.0,
                        "market_cap": 1e9,
                        "shares_outstanding": 100_000_000.0,
                    }
                ),
            )

        assert metrics["ps_ratio"] is None
        assert metrics["ps_ratio_unavailable_reason"] == "missing_sec_data"

    def test_no_shares_outstanding_keeps_generic_reason(self):
        # No shares_outstanding on the sec_valuations row means the implausible-ratio recompute
        # can't run, so this must still fall through to the generic reason, unchanged.
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RevenueQueryCursor(revenue_row=(1_000_000_000.0,))
            metrics = loader._build_value_metrics(
                "AMBIGCO",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "peg_ratio": None,
                        "pb_ratio": 3.0,
                        "ps_ratio": None,
                        "current_price": 10.0,
                        "market_cap": 1e9,
                    }
                ),
            )

        assert metrics["ps_ratio"] is None
        assert metrics["ps_ratio_unavailable_reason"] == "missing_sec_data"
