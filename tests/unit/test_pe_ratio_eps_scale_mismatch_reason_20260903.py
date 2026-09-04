"""Regression test: pe_ratio_unavailable_reason/peg_ratio_unavailable_reason must surface
sec_valuations.reason == "eps_scale_mismatch" verbatim instead of falling through to the
generic "missing_sec_data" label.

Found live 2026-09-03 (SEC/XBRL missing-data sweep): load_sec_valuations.py's
_sanity_check_pe_ratio already deliberately nulls pe_ratio/peg_ratio and records this specific
reason on the sec_valuations row (a >10x SEC-vs-yfinance PE disagreement - a mis-scaled ttm_eps,
not a missing one) whenever data_unavailable stays False (pb_ratio/ps_ratio/fcf_yield still
resolved). But `_build_value_metrics`'s pe_ratio_reason block never consulted that column - it
always re-derived from annual_income_statement, which finds a real, non-NULL EPS (the mis-scale
is in ttm_eps's own computation, not the raw tagged EPS value) and so always fell to the
"missing_sec_data" else-branch. Live-confirmed 50 of 51 universe
sec_valuations.reason='eps_scale_mismatch' rows (BKNG spot-checked) hit exactly this.
`eps_scale_mismatch` is already mapped in scores.py's `_categorize_reason` to "Implausible /
rejected value" (added 2026-08-20 for this same reason surfacing elsewhere in this function) -
this fix just lets pe_ratio/peg_ratio's own reason columns reach that same, already-correct
bucket instead of "Missing SEC/XBRL data".
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


class _NoOpCursor:
    """EPS-history queries must not even run once row_dict already carries a specific reason -
    asserts that by returning data that WOULD wrongly resolve to a different reason if consulted."""

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return (2.5,)  # would wrongly resolve to "missing_sec_data" if this got queried

    def fetchall(self):
        return [(2026, 2.5), (2025, 1.0)]  # would wrongly resolve to a growth-based reason


class TestPeRatioEpsScaleMismatchReason:
    def test_eps_scale_mismatch_reason_propagates_to_pe_and_peg(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _NoOpCursor()
            metrics = loader._build_value_metrics(
                "BKNG",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "peg_ratio": None,
                        "pb_ratio": 8.5,
                        "current_price": 195.13,
                        "market_cap": 146_600_000_000.0,
                        "reason": "eps_scale_mismatch",
                    }
                ),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "eps_scale_mismatch"
        assert metrics["peg_ratio"] is None
        assert metrics["peg_ratio_unavailable_reason"] == "eps_scale_mismatch"

    def test_other_reasons_unaffected_still_re_derive_from_eps_history(self):
        """A different sec_valuations.reason (or none at all) must not trip the new shortcut -
        confirms the DB-backed re-derivation path still runs for every other case."""
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _NoOpCursor()
            metrics = loader._build_value_metrics(
                "AMBIGCO",
                _FakeSecValRow(
                    {
                        "pe_ratio": None,
                        "peg_ratio": None,
                        "pb_ratio": 1.0,
                        "current_price": 10.0,
                        "market_cap": 1_000_000_000.0,
                        "reason": None,
                    }
                ),
            )

        assert metrics["pe_ratio"] is None
        assert metrics["pe_ratio_unavailable_reason"] == "missing_sec_data"
