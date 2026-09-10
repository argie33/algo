"""Regression test for the 2026-09-09 fix in utils/external/sec_statements_entry_resolution.py's
`_aggregate_concepts_resolve_entry_period` (goal session: XBRL scan/tie-out exhaustiveness
audit, AMZN live-confirmed via check_pretax_to_net_income).

A ~365-day duration fact isn't automatically a genuine fiscal-year-aligned annual total - a
rolling/trailing-twelve-month supplemental disclosure (common in MD&A liquidity sections) can
also span ~365 days and pass the existing span>=330-day check. Real SEC companyfacts JSON for
AMZN (CIK 0001018724): a us-gaap:NetIncomeLoss fact spanning 2024-07-01 to 2025-06-30 (364 days,
fp=None) silently overwrote the real FY2025 calendar-year NetIncomeLoss ($77,670,000,000,
confirmed via AMZN's own real 10-K) with $70,623,000,000 - understating net income by $7.05B and
corrupting every downstream EPS/quality/value ratio for a mega-cap.

Fix: for a filer whose fiscal year end is confirmed December (has_december_fiscal_year_end), a
genuine annual total's END must also fall in December - any other end month is definitionally a
rolling window, not this filer's fiscal year.

Note this is a distinct guard from the earlier 2026-09-02 `_aggregate_concepts_should_replace_entry`
fix (10-K/20-F/40-F always outranks a same-tier 10-Q for the "FY" bucket) - that rank tiebreak only
helps when a REAL competing 10-K entry for the same concept also exists to rank against. Here there
is no such competing entry at all (this concept's only "annual-shaped" duration fact IS the rolling
window), so the rolling fact becomes the sole occupant of the (2025, "FY") bucket unless rejected
outright at resolution time - reproduced below by omitting any competing 10-K NetIncomeLoss entry.
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


class TestRollingTtmDurationFactRejected:
    def test_amzn_style_rolling_ttm_does_not_populate_fy_bucket_with_no_competing_10k(self) -> None:
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        # Real Q1 2025 quarterly fact (self-consistent fp/end-month match,
                        # 90-day span) - establishes has_december_fiscal_year_end=True via
                        # the self-consistency fallback (NetIncomeLoss never has instant
                        # facts, so the annual-report-instant-fact signal isn't available).
                        {
                            "start": "2025-01-01",
                            "end": "2025-03-31",
                            "val": 17127000000.0,
                            "filed": "2025-05-01",
                            "fp": "Q1",
                            "fy": 2025,
                            "form": "10-Q",
                            "accn": "0001018724-25-000001",
                        },
                        # Rolling trailing-twelve-month MD&A supplemental disclosure (364
                        # days, ends in June - NOT this filer's December fiscal year end).
                        # Deliberately no competing real FY2025 10-K entry for this concept
                        # at all (matching AMZN's real shape live-confirmed for this bug) -
                        # the earlier 2026-09-02 rank-based fix in
                        # _aggregate_concepts_should_replace_entry only helps when a real
                        # 10-K entry exists to outrank this one; here it doesn't, so without
                        # this fix the rolling fact becomes the sole (and wrong) occupant of
                        # the (2025, "FY") bucket.
                        {
                            "start": "2024-07-01",
                            "end": "2025-06-30",
                            "val": 70623000000.0,
                            "filed": "2026-08-01",
                            "fp": None,
                            "fy": None,
                            "form": "10-Q",
                            "accn": "0001018724-26-000002",
                        },
                    ]
                ),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "AMZN", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert "net_income_loss" not in by_year.get(2025, {})
