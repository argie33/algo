"""Regression test: _unavailable_marker("quality_metrics", ...) must propagate the real reason
to quality_score_unavailable_reason, and must include the newer Phase-3+ fields.

Found live 2026-08-28 in the same audit pass that found the book_value_growth gap in the
growth_metrics branch of this function (see
tests/unit/test_growth_metrics_unavailable_marker_missing_book_value_growth_20260828.py). Two
distinct bugs in the quality_metrics branch:

1. "quality_score_unavailable_reason": None was hardcoded, ignoring `specific_reason` entirely -
   every sibling *_unavailable_reason in this same dict correctly used specific_reason. Live-
   confirmed 16 symbols (VAI, MYSZ, BOXL, MVIS, TV, QVC, KSPI, GGAL, SUPV, BCH, CNK, BSAC, OBX,
   FTW, BBAR, SMXT) had quality_score NULL with no reason at all despite each having a real
   top-level `reason` (missing_sec_data or stale_fiscal_data: ...) on the very same row.

2. 11 fields added to quality_metrics across later migrations (accruals_ratio,
   asset_turnover, estimate_momentum_60d/90d, estimate_revision_direction, fcf_margin,
   gross_profitability, operating_profitability, revision_activity_30d, revision_trend_score,
   roce_pct) were never added to this fallback dict, the same "new field added to the success
   path, fallback never updated" bug class as book_value_growth. Of these, the 7 that
   _insert_quality_metrics actually persists (accruals_ratio, asset_turnover, fcf_margin,
   gross_profitability, operating_profitability, roce_pct, and their reason columns) matched
   the same 16-symbol population as quality_score above (all scored via the same "hit the
   fallback branch" path). The other 4 (estimate_momentum_60d/90d, estimate_revision_direction,
   revision_activity_30d, revision_trend_score) are not part of _insert_quality_metrics's column
   list at all - they come from a different loader - so they're included here for dict
   completeness/documentation but this loader never persists them either way.

   (altman_z_score was originally in this list too - removed entirely 2026-08-29, computation/
   persistence/API/frontend, see loaders/load_value_quality_growth_metrics.py's Altman Z''-Score
   comment for the full history - so it's no longer asserted here.)
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestUnavailableMarkerQualityScoreReason:
    def test_quality_score_unavailable_reason_uses_specific_reason(self) -> None:
        marker = _loader()._unavailable_marker("quality_metrics", "TESTSYM", reason="missing_sec_data")
        assert marker["quality_score_unavailable_reason"] == "missing_sec_data"

    def test_quality_score_unavailable_reason_propagates_stale_fiscal_data(self) -> None:
        marker = _loader()._unavailable_marker(
            "quality_metrics",
            "TESTSYM",
            reason="stale_fiscal_data: latest balance-sheet fiscal_year=2021 is 5 years old (max allowed 3)",
        )
        assert marker["quality_score_unavailable_reason"].startswith("stale_fiscal_data")

    def test_quality_score_unavailable_reason_defaults_to_missing_sec_data(self) -> None:
        marker = _loader()._unavailable_marker("quality_metrics", "TESTSYM")
        assert marker["quality_score_unavailable_reason"] == "missing_sec_data"


class TestUnavailableMarkerIncludesNewerQualityFields:
    def test_persisted_phase3plus_fields_present_and_none(self) -> None:
        marker = _loader()._unavailable_marker("quality_metrics", "TESTSYM")
        for field in [
            "accruals_ratio",
            "asset_turnover",
            "fcf_margin",
            "gross_profitability",
            "operating_profitability",
            "roce_pct",
        ]:
            assert field in marker, f"{field} missing from unavailable marker dict"
            assert marker[field] is None

    def test_persisted_phase3plus_reason_columns_use_specific_reason(self) -> None:
        marker = _loader()._unavailable_marker("quality_metrics", "TESTSYM", reason="missing_sec_data")
        for field in [
            "accruals_ratio",
            "asset_turnover",
            "fcf_margin",
            "gross_profitability",
            "operating_profitability",
            "roce_pct",
        ]:
            assert marker[f"{field}_unavailable_reason"] == "missing_sec_data"
