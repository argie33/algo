"""Regression test: watermark_from_rows() must not advance past a fiscal year whose
row was marked data_unavailable=True by transform().

Found live 2026-08-10 while investigating scores-page "SEC data not available" gaps.
watermark_from_rows() only looked at fiscal_year, never at data_unavailable, so a real
fiscal_year row that transform() flagged incomplete (e.g. a recent spinoff still
mid-filing, reason='incomplete_sec_filing_income') still advanced the watermark to
that year. fetch_incremental()'s `fiscal_year > since_year` filter then permanently
excluded that year from every future incremental fetch, even after SEC EDGAR had real
data for it - the exact HONA spinoff case this marker logic was originally built for
(see SecEdgarStatementLoader.watermark_from_rows docstring) got stuck this way once
its real financials landed, because the watermark had already advanced past FY2026
while it was still unavailable. 112 rows (101 income, 11 cashflow) were found stuck
this way system-wide and one-time-backfilled; this fix stops the backlog from
re-accumulating.
"""

from datetime import date

from loaders.helpers.sec_base import SecEdgarStatementLoader


def _make_loader() -> SecEdgarStatementLoader:
    return SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)


class TestWatermarkExcludesUnavailableRows:
    def test_unavailable_row_does_not_advance_watermark(self) -> None:
        loader = _make_loader()
        rows = [
            {"fiscal_year": 2026, "data_unavailable": True, "reason": "incomplete_sec_filing_income"},
        ]

        watermark = loader.watermark_from_rows(rows)

        assert watermark == date(2000, 12, 31), (
            "an unavailable row must not advance the watermark - doing so permanently "
            "excludes that fiscal year from future incremental refetches"
        )

    def test_available_row_still_advances_watermark(self) -> None:
        loader = _make_loader()
        rows = [
            {"fiscal_year": 2025, "data_unavailable": False, "reason": None},
        ]

        watermark = loader.watermark_from_rows(rows)

        assert watermark == date(2025, 12, 31)

    def test_available_row_wins_over_unavailable_row_same_batch(self) -> None:
        loader = _make_loader()
        rows = [
            {"fiscal_year": 2026, "data_unavailable": True, "reason": "incomplete_sec_filing_income"},
            {"fiscal_year": 2025, "data_unavailable": False, "reason": None},
        ]

        watermark = loader.watermark_from_rows(rows)

        assert watermark == date(2025, 12, 31), (
            "the real 2025 row should set the watermark even though a newer but "
            "unavailable 2026 row is also present in the batch"
        )
