"""Regression test for the FY-bucket form-rank bug in `_aggregate_concepts()`
(utils/external/sec_statements.py), found and fixed in the 2026-09-02 "missing SEC/XBRL data"
goal-session audit (see the "FIXED 2026-09-02" comment ~line 2050 of that file).

`_PRIMARY_STATEMENT_FORMS` ranked 10-K and 10-Q equally (both tier 1) - correct for a quarterly
bucket, but wrong for the annual ("FY") bucket: a 10-Q can carry a genuine "trailing twelve
months" duration fact (start/end ~365 days apart, passing the annual-shape span>=330 filter)
that is NOT the filer's real Jan-Dec fiscal year - it's a rolling window ending mid-year. Under
the old equal-rank-then-latest-filed tiebreak, a LATER-filed 10-Q's TTM fact could silently
clobber an EARLIER-filed 10-K's real annual figure for the same (fiscal_year, "FY") bucket.

Live-confirmed via real SEC EDGAR companyconcept JSON for AMZN: the real FY2025 10-K (filed
2026-02-06) reports NetIncomeLoss=$77,670,000,000 (start=2025-01-01, end=2025-12-31), but AMZN's
Q2 2026 10-Q (filed 2026-07-31) also tags NetIncomeLoss with a TTM duration
(start=2024-07-01, end=2025-06-30, val=$70,623,000,000) - end date buckets this into the SAME
(period_year=2025, "FY") key, and being filed later, it won the old tiebreak and overwrote the
correct 10-K value.

The fix: for the "FY" key specifically, a genuine annual-report-form entry (10-K/20-F/40-F, per
`_ANNUAL_REPORT_FORMS`) always outranks a same-tier 10-Q/6-K entry, regardless of filed date.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001018724"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestAnnualReportFormOutranksTtm10QForFyBucket:
    def test_10k_annual_figure_survives_later_filed_10q_ttm_fact_amzn(self):
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 77_670_000_000,
                            "filed": "2026-02-06",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                        {
                            # Later-filed 10-Q's TTM duration fact: end date buckets it into
                            # the same (2025, "FY") key as the 10-K above, and it was filed
                            # after the 10-K, so the old date-only tiebreak let it win.
                            "start": "2024-07-01",
                            "end": "2025-06-30",
                            "val": 70_623_000_000,
                            "filed": "2026-07-31",
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

        rows = get_income_statement(client, "AMZN", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["net_income_loss"] == 77_670_000_000

    def test_10q_ttm_fact_still_wins_when_no_10k_entry_exists_for_that_fy(self):
        """Sanity check: the fix must not reject a 10-Q's annual-shaped duration fact
        outright - it only loses to a genuine annual-report-form entry when one collides
        into the same FY bucket. A pure quarterly-only reporter still gets its 10-Q data."""
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        {
                            "start": "2024-07-01",
                            "end": "2025-06-30",
                            "val": 70_623_000_000,
                            "filed": "2026-07-31",
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

        rows = get_income_statement(client, "AMZN", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["net_income_loss"] == 70_623_000_000
