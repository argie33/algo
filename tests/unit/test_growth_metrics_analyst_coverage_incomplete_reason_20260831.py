"""Regression test (2026-08-31, reason-code accuracy sweep): the 4 fields
_get_analyst_forward_growth_estimates computes (forward_eps_growth_current_fy/next_fy,
forward_revenue_growth_next_fy, eps_estimate_revision_90d_pct) must distinguish "a real
analyst_earnings_estimates row exists but this one specific field is null" from
"genuinely no analyst coverage at all" - the same bug class already fixed once for
forward_pe (see test_forward_pe_negative_analyst_estimate_reason_20260822.py).

Bug: every field defaulted to "no_analyst_estimates" and only cleared that default when
ITS OWN value came back non-null from the query - so a symbol with a real, current
`data_unavailable = FALSE` analyst_earnings_estimates row that simply lacked ONE of these
4 derived figures still got "no_analyst_estimates" on that field. Live-confirmed on
AFRM/DB/VOD/NWG/WELL/L (real, heavily-covered large/mega-caps, $22B-$1.1T market cap):
each has a real forward_eps/forward_eps_growth_next_fy on file, yet
forward_eps_growth_current_fy_unavailable_reason said "no_analyst_estimates" - yfinance's
earnings_estimate DataFrame simply lacked a "growth" value for the "0y" period for these
symbols specifically, a real but distinct gap from "nobody covers this stock". Fixed by
adding a distinct "analyst_coverage_incomplete_for_field" reason for the row-exists-but-
field-is-null case, categorized under the same "No analyst coverage" bucket in
lambda/api/routes/scores.py.
"""

import importlib
from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader

scores_mod = importlib.import_module("lambda.api.routes.scores")


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _RowExistsPartialCursor:
    """A real analyst_earnings_estimates row exists, but forward_eps_growth_current_fy is
    NULL while the other 3 fields are real values - mirrors the live AFRM/DB/VOD/etc shape.

    Row shape (2026-09-05): 4 value fields + 2 prior_year_eps columns (see migration 1259)."""

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return (None, 0.0521, 0.0813, -1.2, None, 1.5)

    def fetchall(self):
        return []


class _NoRowCursor:
    """No data_unavailable = FALSE row at all - genuinely zero analyst coverage."""

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class TestAnalystForwardGrowthCoverageIncompleteReason:
    def test_partial_coverage_gets_incomplete_reason_not_no_analyst_estimates(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _RowExistsPartialCursor()
            result = loader._get_analyst_forward_growth_estimates("AFRM")

        assert result["forward_eps_growth_current_fy"] is None
        assert result["forward_eps_growth_current_fy_unavailable_reason"] == "analyst_coverage_incomplete_for_field"
        # The 3 fields that DID come back non-null must be populated normally, reason cleared.
        assert result["forward_eps_growth_next_fy"] == 0.0521
        assert result["forward_eps_growth_next_fy_unavailable_reason"] is None
        assert result["forward_revenue_growth_next_fy"] == 0.0813
        assert result["forward_revenue_growth_next_fy_unavailable_reason"] is None
        assert result["eps_estimate_revision_90d_pct"] == -1.2
        assert result["eps_estimate_revision_90d_pct_unavailable_reason"] is None

    def test_genuinely_no_coverage_still_says_no_analyst_estimates(self):
        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = _NoRowCursor()
            result = loader._get_analyst_forward_growth_estimates("ENVA")

        for field in (
            "forward_eps_growth_current_fy",
            "forward_eps_growth_next_fy",
            "forward_revenue_growth_next_fy",
            "eps_estimate_revision_90d_pct",
        ):
            assert result[field] is None
            assert result[f"{field}_unavailable_reason"] == "no_analyst_estimates"

    def test_incomplete_field_reason_categorizes_as_no_analyst_coverage(self):
        assert scores_mod._categorize_reason("analyst_coverage_incomplete_for_field") == "No analyst coverage"
        assert scores_mod._categorize_reason("no_analyst_estimates") == "No analyst coverage"
