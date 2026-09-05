"""Regression test (2026-09-04): _compute_quality_metrics's own outer except block returned
`self._unavailable_marker("quality_metrics", symbol)` with no `reason` argument on ANY
exception, so every per-field *_unavailable_reason (roe, roa, fcf_margin, asset_turnover,
quality_score, ...) always defaulted to the generic "missing_sec_data" - discarding the real
exception message and routing genuine loader bugs (like the Decimal*float crash fixed
alongside this test) into scores.py's "Missing SEC/XBRL data" coverage bucket instead of
"Other (errors / excluded)". The outer fetch_incremental() except block already does this
correctly (passes reason=f"fetch_exception: ..."); this fix makes _compute_quality_metrics's
own except match that same pattern.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestQualityMetricsComputeExceptionReasonPropagated:
    def test_exception_reason_not_generic_missing_sec_data(self, monkeypatch):
        loader = _make_loader()

        def _boom(*args, **kwargs):
            raise TypeError("unsupported operand type(s) for *: 'decimal.Decimal' and 'float'")

        monkeypatch.setattr(loader, "_nan_to_none", _boom)

        # quality_row just needs to be truthy with >=28 columns to pass the early guards
        # and reach the body that raises.
        quality_row = tuple(range(28))
        result = loader._compute_quality_metrics("SYM", quality_row)

        assert result["data_unavailable"] is True
        assert result["roe_unavailable_reason"] != "missing_sec_data"
        assert "fetch_exception" in result["roe_unavailable_reason"]
        assert "TypeError" in result["roe_unavailable_reason"]
        assert result["fcf_margin_unavailable_reason"] == result["roe_unavailable_reason"]
