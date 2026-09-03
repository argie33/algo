"""Regression test for _aggregate_concepts() (utils/external/sec_statements.py) -
"missing SEC/XBRL data" goal session, 2026-09-02.

The 2026-08-18 GM/DIS fix (see
test_sec_annual_instant_fact_rejects_premature_fiscal_year_stub.py) blanket-rejects any
10-Q/6-K-sourced instant fact once a concept has ANY real 10-K/20-F/40-F history at all, to
stop a mid-year 10-Q snapshot from seeding a premature bucket for a fiscal year whose 10-K
hasn't been filed yet. That blanket rule also wrongly dropped a PAST fiscal year-end that a
filer's own 10-K genuinely never tagged this exact concept for, even though a later filing's
10-Q comparative column cites the real value for that year.

Live-verified via WEC (Wisconsin Energy, real SEC companyfacts JSON, CIK 0000783325):
StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest has 10-K-form entries
for FY2019-2025 but NONE for FY2018 - WEC's real FY2018 10-K apparently never tagged this
concept - while three FY2019 10-Qs (accn 0000107815-19-000181/-000240/-000304) each cite the
real FY2018-end comparative value ($9,842,700,000, end=2018-12-31). The old blanket rule
dropped this fact anyway (it's form=10-Q), leaving annual_balance_sheet.stockholders_equity
NULL for FY2018 despite total_assets/current_liabilities/etc. all being populated that year -
211 symbols / 1,144 rows share this "data_unavailable=FALSE but core field NULL" shape live.

Fix: only reject a non-10-K-form instant fact when its end date is genuinely AFTER this
concept's own latest confirmed 10-K/20-F/40-F end date (a real premature snapshot) - a fact
at or before that boundary is a past fiscal year-end recoverable from a later filing's
comparative column, not a premature current-year stub.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000783325"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestPastFiscalYearRecoveredFrom10QComparative:
    def test_10q_comparative_fills_a_year_the_10k_never_tagged(self):
        # WEC-shaped data: real 10-K coverage for FY2017 and FY2019 (this concept), but
        # FY2018 was never tagged by WEC's own FY2018 10-K - only later 10-Qs cite it as a
        # comparative prior-year-end figure. That FY2018 value must still be recovered,
        # since it is NOT beyond the concept's own latest confirmed 10-K end date.
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2018-12-31",
                            "val": 33_475_800_000,
                            "filed": "2019-02-26",
                            "fp": "FY",
                            "fy": 2018,
                            "form": "10-K",
                        },
                    ]
                ),
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": _concept(
                    [
                        {
                            "end": "2017-12-31",
                            "val": 9_491_800_000,
                            "filed": "2018-02-28",
                            "fp": "FY",
                            "fy": 2017,
                            "form": "10-K",
                        },
                        # FY2018 never tagged by WEC's own 10-K - only cited later as a
                        # comparative prior-year-end column in FY2019 10-Qs.
                        {
                            "end": "2018-12-31",
                            "val": 9_842_700_000,
                            "filed": "2019-05-03",
                            "fp": "Q1",
                            "fy": 2019,
                            "form": "10-Q",
                        },
                        {
                            "end": "2019-12-31",
                            "val": 10_186_400_000,
                            "filed": "2020-02-27",
                            "fp": "FY",
                            "fy": 2019,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "WEC", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert (
            by_year[2018]["stockholders_equity_including_portion_attributable_to_noncontrolling_interest"]
            == 9_842_700_000
        ), (
            "a 10-Q's comparative citation of a PAST fiscal year-end this concept's own 10-K never tagged must still be recovered"
        )
        assert (
            by_year[2017]["stockholders_equity_including_portion_attributable_to_noncontrolling_interest"]
            == 9_491_800_000
        )
        assert (
            by_year[2019]["stockholders_equity_including_portion_attributable_to_noncontrolling_interest"]
            == 10_186_400_000
        )

    def test_premature_current_year_snapshot_still_rejected(self):
        # Sanity check: the ORIGINAL GM/DIS protection must still hold - a 10-Q instant
        # fact BEYOND the concept's latest confirmed 10-K end date (a genuine premature
        # current-year snapshot) is still rejected, not just anything form=10-Q.
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 281_284_000_000,
                            "filed": "2026-02-04",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                    ]
                ),
                "StockholdersEquity": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 25_000_000_000,
                            "filed": "2026-02-04",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                        {
                            "end": "2026-06-30",
                            "val": 26_500_000_000,
                            "filed": "2026-07-21",
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

        rows = get_balance_sheet(client, "GM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert 2026 not in by_year, (
            "a 10-Q instant fact beyond the concept's latest confirmed 10-K end date must still "
            "be rejected as a premature current-year snapshot"
        )
        assert by_year[2025]["stockholders_equity"] == 25_000_000_000
