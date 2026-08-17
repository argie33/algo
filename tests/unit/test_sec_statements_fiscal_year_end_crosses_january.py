"""Regression test for a fiscal-year-mislabeling bug in _aggregate_concepts()
(utils/external/sec_statements.py):

52/53-week fiscal calendars (common among retail/industrial filers) can end a few days
into January instead of Dec 31. Live-confirmed against SEC's real API for SWK (Stanley
Black & Decker): its FY2020 10-K reports fy=2020, start=2019-12-29, end=2021-01-02 (a
370-day/53-week year, majority of days in calendar 2020) - but bucketing purely by the
calendar year of the period-end date put this entry in bucket "2021", colliding with (and
being overwritten by) FY2021's own later-filed entry. This left FY2020 revenue/net_income
NULL in the real annual_income_statement table (data_unavailable='incomplete_sec_filing_income')
despite SEC having the data all along - live-confirmed via direct DB query 2026-08-16.

The fix narrowly relabels only entries whose end date falls in the first 10 days of January
with a start date the previous calendar year (already required to be a near-full-year span
by the existing span_days >= 330 check), using the entry's own SEC-tagged fy field - which is
trustworthy in this specific case because it's the filing's own current-period label, not a
comparative-year figure copied from the filing's context.

Non-calendar fiscal years that end well into January/February (e.g. Walmart's Jan 31) or other
months (e.g. Apple's Sep 30) must NOT be affected - only the narrow year-end-crosses-Jan-1 case.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000093556"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestFiscalYearEndCrossesJanuaryBoundary:
    def test_53_week_fiscal_year_ending_in_january_buckets_to_majority_year(self):
        # Real SWK-shaped data: FY2019 (end 2019-12-28), FY2020 (53-week, end 2021-01-02),
        # FY2021 (end 2021-12-31, filed later - the entry that previously clobbered FY2020's
        # bucket under the old end-date-only derivation).
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2018-12-30",
                            "end": "2019-12-28",
                            "val": 12_912_900_000.0,
                            "filed": "2020-02-20",
                            "fp": "FY",
                            "fy": 2019,
                            "form": "10-K",
                        },
                        {
                            "start": "2019-12-29",
                            "end": "2021-01-02",
                            "val": 14_534_600_000.0,
                            "filed": "2021-02-18",
                            "fp": "FY",
                            "fy": 2020,
                            "form": "10-K",
                        },
                        {
                            "start": "2021-01-03",
                            "end": "2021-12-31",
                            "val": 15_617_100_000.0,
                            "filed": "2022-02-17",
                            "fp": "FY",
                            "fy": 2021,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "SWK", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2019]["revenues"] == 12_912_900_000.0
        # This is the bug: previously NULL because this entry bucketed into "2021" (bare
        # calendar year of its end date) and got overwritten by the real FY2021 entry.
        assert by_year[2020]["revenues"] == 14_534_600_000.0
        assert by_year[2021]["revenues"] == 15_617_100_000.0

    def test_fiscal_year_ending_january_31_is_not_relabeled(self):
        # Walmart-shaped: FY "2024" (per the filer's own convention) covers Feb 2023 - Jan
        # 2024, end=2024-01-31 - well outside the first-10-days-of-January window, must stay
        # bucketed by end-date year (2024), not majority-of-days (which would be 2023).
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2023-02-01",
                            "end": "2024-01-31",
                            "val": 648_125_000_000.0,
                            "filed": "2024-03-20",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "WMT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert 2024 in by_year
        assert by_year[2024]["revenues"] == 648_125_000_000.0
        assert 2023 not in by_year

    def test_calendar_fiscal_year_is_unaffected(self):
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2022-01-01",
                            "end": "2022-12-31",
                            "val": 1_000_000.0,
                            "filed": "2023-02-15",
                            "fp": "FY",
                            "fy": 2022,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2022]["revenues"] == 1_000_000.0
