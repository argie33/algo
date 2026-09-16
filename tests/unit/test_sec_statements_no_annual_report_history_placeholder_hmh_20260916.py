"""Regression test for another annual-row period_end mis-anchoring shape in
_aggregate_concepts() (utils/external/sec_statements_aggregate.py), distinct from CHKP's
(see test_sec_statements_fpi_interim_period_end_anchor_chkp_20260916.py):

Live-verified 2026-09-16 via HMH ("HMH Holding Inc.", CIK 0002021880) and YSWY ("Yesway, Inc.",
CIK 0001859836) - both brand-new post-business-combination registrants that have filed ONLY
10-Qs so far (no 10-K/20-F/40-F exists anywhere in their history yet). Both filers' earliest
10-Q tags Assets/StockholdersEquity/AccountsReceivable with a placeholder val=10/val=1 across
multiple unrelated concepts - a real filer-side XBRL template error, not a units/scale issue:
their very next 10-Q corrects the exact same concepts to real, consistent 9-10-figure values
for a LATER quarter-end. annual_balance_sheet FY2026 held total_assets=$10 (should be the real,
later $1,362,565,000) because the CHKP fix only lets an ANNUAL-report-form entry re-anchor an
already-set period_end - correct when a real 10-K/20-F exists somewhere to protect, but this
filer has none, so the "annual" bucket is really just "whichever 10-Q's instant fact got
processed first", forever stuck on the placeholder.

Fix: when there is no annual-report-form history at all for this concept
(`has_annual_report_form=False`), a later-filed primary-statement-form entry (10-Q/6-K, not an
8-K/DEF14A/S-1) whose own end date is chronologically AFTER the existing anchor may also
correct it - the anchor legitimately advances quarter to quarter until a real 10-K/20-F
eventually establishes a genuine fiscal-year-end.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0002021880"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestNoAnnualReportHistoryPlaceholderAnchor:
    def test_later_10q_current_balance_corrects_an_earlier_10q_placeholder_anchor(self) -> None:
        # Real HMH-shaped data: the Q1 10-Q's own placeholder "Assets"/"StockholdersEquity"
        # facts (val=10, no 10-K/20-F exists anywhere for this filer) appear BEFORE the Q2
        # 10-Q's real, later-quarter-end facts in SEC's companyfacts array order.
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2026-03-31",
                            "val": 10,
                            "filed": "2026-05-06",
                            "fp": "Q1",
                            "fy": 2026,
                            "form": "10-Q",
                        },
                        {
                            "end": "2026-06-30",
                            "val": 1_362_565_000,
                            "filed": "2026-08-05",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                        },
                    ]
                ),
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": _concept(
                    [
                        {
                            "end": "2026-03-31",
                            "val": 10,
                            "filed": "2026-05-06",
                            "fp": "Q1",
                            "fy": 2026,
                            "form": "10-Q",
                        },
                        {
                            "end": "2026-06-30",
                            "val": 846_399_000,
                            "filed": "2026-08-05",
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

        rows = get_balance_sheet(client, "HMH", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2026]["assets"] == 1_362_565_000, (
            f"expected the later 10-Q's real current-quarter Assets value, not the earlier "
            f"10-Q's placeholder val=10, got {by_year[2026].get('assets')!r}"
        )
        assert (
            by_year[2026]["stockholders_equity_including_portion_attributable_to_noncontrolling_interest"]
            == 846_399_000
        )

    def test_annual_report_form_history_still_protected_from_a_later_but_earlier_period_10q(
        self,
    ) -> None:
        """Once a real 10-K/20-F exists (has_annual_report_form=True), this new branch must
        never fire - a later-filed 10-Q for an EARLIER (comparative) period must still be
        rejected exactly as before, unaffected by this fix."""
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 7_806_400_000,
                            "filed": "2026-03-31",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                        # A later-filed 10-Q whose end date is BEFORE the established anchor -
                        # must never advance the anchor (this fix only accepts a LATER end
                        # date), and it's also not the annual bucket's own fiscal year anyway.
                        {
                            "end": "2025-06-30",
                            "val": 999_000_000,
                            "filed": "2026-04-01",
                            "fp": "Q2",
                            "fy": 2025,
                            "form": "10-Q",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "HMH", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["assets"] == 7_806_400_000
