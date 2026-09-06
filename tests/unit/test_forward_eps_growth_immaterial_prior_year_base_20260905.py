"""Regression test for the 2026-09-05 fix (goal session: "missing SEC/XBRL data"/
implausible-values sweep): forward_eps_growth_current_fy/next_fy's plausibility check
couldn't distinguish a mathematically-blown-up ratio (near-zero prior-year EPS base) from a
genuinely enormous real growth ratio, because only the already-computed ratio was ever
stored - both got the same "garbage_metric_value_implausible_ratio" ("Implausible / rejected
value") label.

Live-confirmed via PII's real yfinance data: Ticker.earnings_estimate's '0y' row has
yearAgoEps=-0.01 (near-zero), avg=3.13694, so growth=(3.13694-(-0.01))/abs(-0.01)=314.694 (a
mathematically correct but practically meaningless 31,469% ratio caused entirely by the
near-zero base) - the exact same numerical-instability class growth_metrics' own realized
eps_growth_1y already gives an honest "immaterial_prior_year_base" reason (Legitimate / not
applicable) via its own $0.10 floor (vqg_growth.py's min_abs_target=0.10).

Migration 1259 added forward_eps_growth_current_fy_prior_year_eps/next_fy_prior_year_eps to
analyst_earnings_estimates (populated from yfinance's own 'yearAgoEps' column) so this
distinction is now possible: an implausible ratio whose prior-year EPS is |value| < $0.10 now
gets "immaterial_prior_year_base" instead of the generic implausible-ratio label.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeCursor:
    def __init__(self, row: tuple) -> None:
        self._row = row

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


def _patched_db(row: tuple):
    return patch(
        "loaders.load_value_quality_growth_metrics.DatabaseContext",
        return_value=type(
            "Ctx", (), {"__enter__": lambda self: _FakeCursor(row), "__exit__": lambda self, *a: False}
        )(),
    )


class TestForwardEpsGrowthImmaterialPriorYearBase:
    def test_pii_style_near_zero_base_gets_immaterial_reason_not_implausible(self):
        loader = _make_loader()
        # (current_fy, next_fy, revenue_growth, revision_pct, current_fy_prior_eps, next_fy_prior_eps)
        row = (314.694, 0.0828, 0.0324, 72.28, -0.01, 3.13694)
        with _patched_db(row):
            result = loader._get_analyst_forward_growth_estimates("PII")

        assert result["forward_eps_growth_current_fy"] is None
        assert result["forward_eps_growth_current_fy_unavailable_reason"] == "immaterial_prior_year_base"
        # next_fy's own ratio is plausible (8.28%) and its own prior-year base is real ($3.14) -
        # must compute normally, unaffected by current_fy's rejection.
        assert result["forward_eps_growth_next_fy"] == 0.0828
        assert result["forward_eps_growth_next_fy_unavailable_reason"] is None

    def test_genuinely_implausible_ratio_with_real_base_keeps_generic_reason(self):
        """An implausible ratio whose prior-year base is NOT near-zero must keep the generic
        label - the fix must not reclassify every implausible ratio as "immaterial", only
        ones actually caused by a near-zero denominator."""
        loader = _make_loader()
        row = (25.0, 0.0828, 0.0324, 72.28, 5.0, 3.13694)
        with _patched_db(row):
            result = loader._get_analyst_forward_growth_estimates("SOMECORP")

        assert result["forward_eps_growth_current_fy"] is None
        assert result["forward_eps_growth_current_fy_unavailable_reason"] == "garbage_metric_value_implausible_ratio"

    def test_implausible_ratio_with_no_prior_eps_on_file_keeps_generic_reason(self):
        """A NULL prior_year_eps (e.g. from a run before migration 1259's backfill, or
        yfinance simply not returning yearAgoEps) must fail safe to the generic label, not
        silently claim "immaterial" without evidence."""
        loader = _make_loader()
        row = (25.0, 0.0828, 0.0324, 72.28, None, 3.13694)
        with _patched_db(row):
            result = loader._get_analyst_forward_growth_estimates("SOMECORP")

        assert result["forward_eps_growth_current_fy_unavailable_reason"] == "garbage_metric_value_implausible_ratio"
