"""Regression test: ev_revenue_unavailable_reason must reuse ps_ratio_reason's own
implausible-ratio check (both divide by the identical ttm_revenue) instead of falling through
to the generic "missing_sec_data" whenever load_sec_valuations.py's own ev_revenue computation
rejects a real revenue-per-share below MIN_PLAUSIBLE_PS_RATIO's $0.10 floor.

Found 2026-09-05 (goal session: "implausible values" sweep). load_sec_valuations.py's ev_revenue
computation used to only bound the ratio itself (0..10000), the same bare ceiling ps_ratio had
before its own 2026-09-05 fix - a real, positive revenue combined with an out-of-bounds
per-share denominator (a real but near-zero revenue-per-share, e.g. a huge share count against
tiny revenue) produces a real but economically meaningless EV/Revenue multiple that's
nonetheless technically under 10000. Live-confirmed ABSI (Absci Corp): real FY2025 revenue
$2.8M against 136.8M shares = $0.0205/share (below the $0.10 floor) - ev_revenue=425.28 was
being silently accepted despite ps_ratio being correctly rejected on the exact same row for the
identical reason.
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
    def __init__(self, revenue_row):
        self._revenue_row = revenue_row
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "SELECT revenue" in self.last_query:
            return self._revenue_row
        return None

    def fetchall(self):
        return []


class TestEvRevenueImplausibleRatioReason:
    def test_real_tiny_revenue_per_share_reports_implausible_ratio(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # ABSI-shaped: real $2.8M revenue against 136.8M shares -> rps~=$0.0205 (< $0.10
            # floor), ev_revenue=425.28 (technically < 10000, but the same implausible cause
            # ps_ratio was rejected for).
            mock_db_ctx.return_value.__enter__.return_value = _RevenueQueryCursor(revenue_row=(2_800_000.0,))
            metrics = loader._build_value_metrics(
                "ABSI",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "peg_ratio": None,
                        "pb_ratio": 6.37,
                        "ps_ratio": None,
                        "ev_revenue": None,
                        "enterprise_value": 1_190_776_125.70,
                        "current_price": 8.82,
                        "market_cap": 1_206_372_125.70,
                        "shares_outstanding": 136_776_885.0,
                    }
                ),
            )

        assert metrics["ev_revenue"] is None
        assert metrics["ev_revenue_unavailable_reason"] == "implausible_ratio"
        assert metrics["ps_ratio_unavailable_reason"] == "implausible_ratio"

    def test_real_revenue_with_plausible_ratio_keeps_generic_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RevenueQueryCursor(revenue_row=(1_000_000_000.0,))
            metrics = loader._build_value_metrics(
                "PLAUSIBLECO",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "peg_ratio": None,
                        "pb_ratio": 3.0,
                        "ps_ratio": None,
                        "ev_revenue": None,
                        "enterprise_value": 1_000_000_000.0,
                        "current_price": 10.0,
                        "market_cap": 1e9,
                        "shares_outstanding": 100_000_000.0,
                    }
                ),
            )

        assert metrics["ev_revenue"] is None
        assert metrics["ev_revenue_unavailable_reason"] == "missing_sec_data"
