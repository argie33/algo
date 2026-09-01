"""Regression test for a fiscal-year revenue mis-selection bug in _aggregate_concepts()
(utils/external/sec_statements.py):

Live-verified 2026-08-31 via LADR (Ladder Capital, mortgage REIT, CIK 0001577670) real SEC
companyfacts JSON: annual_income_statement.revenue for fiscal_year=2019 stored $3,900,000, but
the real total (OperatingLeaseLeaseIncome, from LADR's own FY2019 10-K, accn
0001577670-20-000004) is $106,366,000. The stored $3,900,000 traces to a SECOND fact under the
same concept from the SAME accn/filed date: an INSTANT (point-in-time) fact - no "start" field,
just {"end": "2019-05-01", "val": 3900000} - almost certainly a future-minimum-lease-payments
footnote/schedule row, not a period total at all.

Before this fix, an instant fact and a genuine annual duration fact colliding into the same
(fiscal_year, "FY") bucket for the same concept had no explicit priority rule between them - the
existing tiebreaks (form rank, then instant-vs-instant end-date, then duration-vs-duration
filed-date) never actually compared an instant fact against a duration one, so whichever was
iterated first in SEC's JSON silently won. This is the same underlying "two colliding facts,
whichever iterates first wins" failure mode as the already-fixed RIGL case
(test_sec_statements_instant_fact_prefers_latest_end_date.py) and PMT case, just instant-vs-
duration instead of instant-vs-instant.

Fix: an entry's is_instant status is now tracked per column (_is_instant_{col}), and a genuine
annual duration fact always outranks an instant fact for the same bucket, regardless of
iteration order or filed date. Safe for balance-sheet concepts (the RIGL/PMT cases): they
structurally never emit a genuine annual-duration-shaped fact under their own concept name, so
this new priority rule never fires for them - confirmed by the full existing regression suite
(111 tests across every documented sec_statements.py fix) passing unchanged.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001577670"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestDurationFactBeatsInstantFact:
    def test_ladr_real_annual_lease_income_not_overwritten_by_instant_schedule_row(self):
        # Real LADR-shaped data: the genuine FY2019 annual total (duration fact, has
        # "start") and the spurious instant footnote-schedule fact (no "start"), both
        # from the same accn/filed date - exactly the ordering that triggered the live
        # bug (instant fact listed AFTER the real duration fact in list order).
        facts = {
            "us-gaap": {
                "OperatingLeaseLeaseIncome": _concept(
                    [
                        {
                            "start": "2019-01-01",
                            "end": "2019-12-31",
                            "val": 106_366_000,
                            "filed": "2020-02-27",
                            "fp": "FY",
                            "fy": 2019,
                            "form": "10-K",
                            "accn": "0001577670-20-000004",
                        },
                        {
                            "end": "2019-05-01",
                            "val": 3_900_000,
                            "filed": "2020-02-27",
                            "fp": "FY",
                            "fy": 2019,
                            "form": "10-K",
                            "accn": "0001577670-20-000004",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "LADR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2019]["operating_lease_lease_income"] == 106_366_000

    def test_instant_fact_processed_first_still_loses_to_duration_fact(self):
        """The fix must not depend on iteration order - the instant fact listed FIRST
        must still lose to the real annual duration fact processed after it."""
        facts = {
            "us-gaap": {
                "OperatingLeaseLeaseIncome": _concept(
                    [
                        {
                            "end": "2019-05-01",
                            "val": 3_900_000,
                            "filed": "2020-02-27",
                            "fp": "FY",
                            "fy": 2019,
                            "form": "10-K",
                            "accn": "0001577670-20-000004",
                        },
                        {
                            "start": "2019-01-01",
                            "end": "2019-12-31",
                            "val": 106_366_000,
                            "filed": "2020-02-27",
                            "fp": "FY",
                            "fy": 2019,
                            "form": "10-K",
                            "accn": "0001577670-20-000004",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "LADR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2019]["operating_lease_lease_income"] == 106_366_000

    def test_two_instant_facts_still_use_existing_end_date_tiebreak(self):
        """Sanity check: this fix must not disturb the existing instant-vs-instant
        tiebreak (RIGL fix) when both competing facts are instant."""
        facts = {
            "us-gaap": {
                "StockholdersEquity": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 391_480_000,
                            "filed": "2026-08-04",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                        },
                        {
                            "end": "2025-03-31",
                            "val": 18_567_000,
                            "filed": "2026-08-04",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        from utils.external.sec_statements import get_balance_sheet

        rows = get_balance_sheet(client, "RIGL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["stockholders_equity"] == 391_480_000
