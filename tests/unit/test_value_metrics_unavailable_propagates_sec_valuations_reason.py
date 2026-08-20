"""Regression test: _build_value_metrics must propagate sec_valuations' own real, specific
`reason` column into every value_metrics *_unavailable_reason field when the whole
sec_valuations row is unavailable, instead of collapsing to the generic "missing_sec_data".

Found live 2026-08-19 ("no SEC data" audit): load_sec_valuations.py already computes and
stores a specific cause (e.g. "shares_outstanding_unavailable", after exhausting all 6 of its
own fallback tiers) whenever it can't produce a usable row for a symbol - but
_build_value_metrics's early-return path (sec_val_row missing or data_unavailable) discarded
that column entirely in favor of a hardcoded generic "missing_sec_data" for every one of
pe_ratio/pb_ratio/ps_ratio/peg_ratio/dividend_yield/fcf_yield/ev_ebitda/ev_revenue/market_cap/
intrinsic_value/margin_of_safety. Live-confirmed 771 of 817 universe "missing_sec_data"
market_cap rows are actually this specific, more actionable shares_outstanding_unavailable
cause - one join away from where it was already sitting.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    """Minimal stand-in for a psycopg2 DictRow: supports both sec_val_row[2] (legacy
    positional data_unavailable flag) and dict(sec_val_row) (mapping protocol, used by the
    fixed code path)."""

    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return self._mapping.get("data_unavailable", False)
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class TestValueMetricsUnavailablePropagatesSecValuationsReason:
    def test_specific_reason_propagates_to_every_field(self):
        loader = _make_loader()
        sec_val_row = _FakeSecValRow({"data_unavailable": True, "reason": "shares_outstanding_unavailable"})

        result = loader._build_value_metrics("NOSHARES", sec_val_row)

        assert result["market_cap_unavailable_reason"] == "shares_outstanding_unavailable"
        assert result["pe_ratio_unavailable_reason"] == "shares_outstanding_unavailable"
        assert result["pb_ratio_unavailable_reason"] == "shares_outstanding_unavailable"
        assert result["ev_ebitda_unavailable_reason"] == "shares_outstanding_unavailable"
        assert result["intrinsic_value_unavailable_reason"] == "shares_outstanding_unavailable"

    def test_no_sec_val_row_at_all_keeps_generic_reason(self):
        # Control: a symbol with no sec_valuations row whatsoever has no specific cause to
        # propagate - must fall back to the original generic label, not crash or emit None.
        loader = _make_loader()

        result = loader._build_value_metrics("NEVERLOADED", None)

        assert result["market_cap_unavailable_reason"] == "missing_sec_data"
        assert result["pe_ratio_unavailable_reason"] == "missing_sec_data"

    def test_forward_pe_reason_unaffected_by_sec_valuations_cause(self):
        # forward_pe's reason is about analyst-estimate availability, not SEC valuation data -
        # must stay a fixed, distinct label regardless of the underlying sec_valuations cause.
        loader = _make_loader()
        sec_val_row = _FakeSecValRow({"data_unavailable": True, "reason": "shares_outstanding_unavailable"})

        result = loader._build_value_metrics("NOSHARES", sec_val_row)

        assert result["forward_pe_unavailable_reason"] == "analyst_estimates_not_in_sec_filings"
