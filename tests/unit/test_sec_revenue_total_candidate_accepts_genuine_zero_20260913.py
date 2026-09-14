"""Regression test for a zero-filter bug in resolve_revenue_total_candidate
(loaders/helpers/sec_revenue_total_resolution.py): the function used to reject ANY value
<= 0, including a genuinely correct revenue of exactly $0.

Live-confirmed via FENC (a pre-revenue biotech): real reported revenue for FY2020 Q1-Q3 is
$0. Because 0 never reached `row[db_field]`, a stale, wrong, non-zero value already sitting
in the DB from an earlier bad extraction could never be corrected by ANY later reload - the
correct value was filtered out before it ever had a chance to overwrite anything.

Fix: accept 0 (a real, valid revenue total) while still rejecting negative values.
"""

from loaders.helpers.sec_revenue_total_resolution import resolve_revenue_total_candidate


class TestRevenueTotalCandidateAcceptsGenuineZero:
    def test_genuine_zero_revenue_is_actually_written_not_silently_dropped(self):
        """The real FENC bug: when the ONLY candidate for a fiscal year is a genuine $0
        (a pre-revenue biotech), the old `value > 0` filter rejected it outright, so
        `row["revenue"]` was never set at all - the extraction's own output row had no
        opinion on "revenue" for that year, so a stale non-zero value already in the DB
        from an earlier bad extraction survived every subsequent reload untouched (the
        loader's own upsert never had a reason to overwrite it). This must now actually
        write 0, not leave the field unset."""
        row: dict[str, object] = {}
        best: dict[str, float] = {}
        source: dict[str, str] = {}

        resolve_revenue_total_candidate("revenues", 0.0, "revenue", row, best, source)

        assert row["revenue"] == 0.0
        assert best["revenue"] == 0.0
        assert source["revenue"] == "revenues"

    def test_genuine_zero_does_not_overwrite_a_real_larger_positive_candidate(self):
        row: dict[str, object] = {}
        best: dict[str, float] = {}
        source: dict[str, str] = {}

        resolve_revenue_total_candidate("sales_revenue_net", 5_000_000.0, "revenue", row, best, source)
        resolve_revenue_total_candidate("revenues", 0.0, "revenue", row, best, source)

        assert row["revenue"] == 5_000_000.0

    def test_negative_value_still_rejected(self):
        row: dict[str, object] = {}
        best: dict[str, float] = {}
        source: dict[str, str] = {}

        resolve_revenue_total_candidate("revenues", -1000.0, "revenue", row, best, source)

        assert "revenue" not in row

    def test_zero_seed_from_existing_row_value_unaffected(self):
        """The seed step (already-populated non-magnitude field, e.g. a mortgage REIT's
        interest_income_operating) must still work normally when it happens to be exactly
        zero - it should seed the best-tracker, not crash or misbehave."""
        row = {"revenue": 0.0}
        best: dict[str, float] = {}
        source: dict[str, str] = {}

        resolve_revenue_total_candidate("sales_revenue_net", 3_000_000.0, "revenue", row, best, source)

        assert row["revenue"] == 3_000_000.0
