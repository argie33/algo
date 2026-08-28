"""Regression test: _unavailable_marker("growth_metrics", ...) must include book_value_growth.

Found live 2026-08-28 during a goal-mode data-loading audit, re-checking the 66-symbol
"unknown reason" population already flagged in memory as open-but-unexplained. Root cause: the
growth_metrics branch of ValueQualityGrowthMetricsLoader._unavailable_marker() predates
book_value_growth (added 2026-08-27, migration 1242) and was never updated for it - every
sibling field (revenue_growth_1y/3y/5y, eps_growth_1y/3y/5y) got both a None value and a real
per-field *_unavailable_reason, but book_value_growth and book_value_growth_unavailable_reason
were simply absent from the returned dict. Two real call sites hit this branch:
- _compute_growth_metrics's early return when a symbol has zero usable income_rows at all
  (no revenues, EPS, or BVPS data whatsoever) - live-confirmed 63 symbols (ADBT, APMC, GHXI,
  MVIS, etc.), each landing with book_value_growth=NULL, book_value_growth_unavailable_reason=
  NULL, and only a generic top-level reason="insufficient_history" - indistinguishable from a
  bug, same failure shape the ON CONFLICT fix in test_growth_metrics_book_value_growth_
  unavailable_reason_wired_20260827.py already fixed for a different root cause.
- fetch_incremental's stale_fiscal_data path (~line 839), which also calls this same fallback
  and then propagates the real "stale_fiscal_data: ..." reason onto every *_unavailable_reason
  key already present in the dict - live-confirmed 3 symbols, which without this fix silently
  skip book_value_growth_unavailable_reason entirely (key not present to overwrite).

Because growth_score is a single-input pillar scored 100% off book_value_growth (see
load_stock_scores.py::_score_growth), this population is exactly the segment of the Growth
pillar's ~27% coverage gap that had no explained reason at all.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestUnavailableMarkerIncludesBookValueGrowth:
    def test_book_value_growth_key_present_and_none(self) -> None:
        marker = _loader()._unavailable_marker("growth_metrics", "TESTSYM")
        assert "book_value_growth" in marker
        assert marker["book_value_growth"] is None

    def test_book_value_growth_unavailable_reason_defaults_to_insufficient_history(self) -> None:
        marker = _loader()._unavailable_marker("growth_metrics", "TESTSYM")
        assert marker["book_value_growth_unavailable_reason"] == "insufficient_history"

    def test_book_value_growth_unavailable_reason_uses_specific_reason_when_given(self) -> None:
        marker = _loader()._unavailable_marker("growth_metrics", "TESTSYM", reason="fetch_exception: KeyError: 'x'")
        assert marker["book_value_growth_unavailable_reason"] == "fetch_exception: KeyError: 'x'"

    def test_stale_fiscal_data_propagation_reaches_book_value_growth_reason(self) -> None:
        """Mirrors fetch_incremental's stale_fiscal_data path (~line 839-854): call the
        fallback marker bare, then overwrite every non-None *_unavailable_reason key the same
        way that code does. book_value_growth_unavailable_reason must be one of the keys that
        gets overwritten, not silently absent."""
        marker = _loader()._unavailable_marker("growth_metrics", "TESTSYM")
        marker["reason"] = "stale_fiscal_data: latest income-statement fiscal_year=2021 is 5 years old (max allowed 3)"
        for key in marker:
            if key.endswith("_unavailable_reason") and marker[key] is not None:
                marker[key] = "stale_fiscal_data"

        assert marker["book_value_growth_unavailable_reason"] == "stale_fiscal_data"

    def test_other_growth_metrics_branch_fields_unaffected(self) -> None:
        marker = _loader()._unavailable_marker("growth_metrics", "TESTSYM")
        assert marker["revenue_growth_1y"] is None
        assert marker["revenue_growth_1y_unavailable_reason"] == "insufficient_history"
        assert marker["data_unavailable"] is True
