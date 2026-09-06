"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, value_metrics
sibling of the identical vqg_quality.py/vqg_growth.py ETF zero-row fixes): SPY has ZERO
sec_valuations rows at all (load_sec_valuations.py never even attempts a market-cap/EV
computation for it), so `_build_value_metrics`'s `not row_dict` branch had no `reason` to
propagate and fell back to the generic "missing_sec_data" default for its entire
value_metrics row, instead of the "etf_no_sec_filings" fact already used for the identical
case elsewhere.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestValueMetricsEtfNoSecValuationsRowReason:
    def test_etf_with_no_sec_valuations_row_reports_etf_no_sec_filings(self, monkeypatch):
        loader = _make_loader()
        monkeypatch.setattr(type(loader), "_get_etf_symbols", lambda self: frozenset({"SPY"}))

        result = loader._build_value_metrics("SPY", None)

        assert result["reason"] == "etf_no_sec_filings"
        assert result["pe_ratio_unavailable_reason"] == "etf_no_sec_filings"

    def test_non_etf_with_no_sec_valuations_row_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader()
        monkeypatch.setattr(type(loader), "_get_etf_symbols", lambda self: frozenset({"SPY"}))

        result = loader._build_value_metrics("ACTU", None)

        assert result["reason"] == "missing_sec_data"
