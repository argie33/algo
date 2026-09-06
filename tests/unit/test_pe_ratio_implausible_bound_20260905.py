"""Regression test: pe_ratio_unavailable_reason must recognize when a real, positive EPS
combined with the row's own current_price pushes the recomputed ratio outside
load_sec_valuations.py's own MIN_PLAUSIBLE_PE_RATIO(0.05)..10000 bound, OR when the EPS itself
falls below load_sec_valuations.py's separate $0.10 revenue/earnings-per-share floor - the same
"implausible_ratio" treatment already added to pb_ratio_reason/ps_ratio_reason.

Found 2026-09-05 (goal: "SEC/XBRL missing data to zero" audit). The implied-pe bounds check
(added same day, KLIC-driven) never re-derived the OTHER real rejection criterion
load_sec_valuations.py applies (ttm_eps < 0.10) - a tiny EPS combined with an equally tiny price
can produce an implied_pe that lands comfortably inside 0.05..10000 even though the real
computation rejected it via the EPS floor, so this fell through to "missing_sec_data" instead of
"implausible_ratio".
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


class TestPeRatioImplausibleBound:
    def test_real_tiny_eps_reports_implausible_ratio(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # KLIC-shaped: real, positive EPS ($0.0040) against price $81.62 -> implied
            # pe~20,405 (> 10000 upper bound).
            mock_db_ctx.return_value.__enter__.return_value = _EpsQueryCursor(eps_row=(0.0040,))
            metrics = loader._build_value_metrics(
                "KLIC",
                _FakeSecValRow(
                    {"pe_ratio": None, "peg_ratio": None, "pb_ratio": 1.5, "current_price": 81.62, "market_cap": 1e9}
                ),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "implausible_ratio"

    def test_real_eps_below_floor_reports_implausible_ratio(self):
        """A real, positive EPS below load_sec_valuations.py's $0.10 floor can still imply a pe
        comfortably inside 0.05..10000 when the price is also small - the bare implied-pe bounds
        check alone misses this."""
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # eps=$0.08 (< $0.10 floor), price=$0.50 -> implied pe = 6.25, well within bounds.
            mock_db_ctx.return_value.__enter__.return_value = _EpsQueryCursor(eps_row=(0.08,))
            metrics = loader._build_value_metrics(
                "THINEPSCO",
                _FakeSecValRow(
                    {"pe_ratio": None, "peg_ratio": None, "pb_ratio": 1.0, "current_price": 0.50, "market_cap": 5e7}
                ),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "implausible_ratio"

    def test_real_eps_with_plausible_ratio_keeps_generic_reason(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            # eps=$2.50, price=$10 -> implied pe = 4.0, well within bounds and above the eps
            # floor - this symbol's pe still came out null for some other, genuinely ambiguous
            # reason.
            mock_db_ctx.return_value.__enter__.return_value = _EpsQueryCursor(eps_row=(2.5,))
            metrics = loader._build_value_metrics(
                "PLAUSIBLECO",
                _FakeSecValRow(
                    {"pe_ratio": None, "peg_ratio": None, "pb_ratio": 1.0, "current_price": 10.0, "market_cap": 1e9}
                ),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "missing_sec_data"
