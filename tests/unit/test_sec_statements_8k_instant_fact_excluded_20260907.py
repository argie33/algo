"""Regression test widening the 8-K exclusion in
_aggregate_concepts_resolve_entry_period() (utils/external/sec_statements_entry_resolution.py)
to instant (point-in-time) facts, not just duration facts.

Live-verified 2026-09-07 via WTRG (Essential Utilities): algo/monitoring/data_patrol/checks/
tie_out.py's short_term_debt_le_current_liabilities check flagged short_term_debt exceeding
current_liabilities. Real SEC companyfacts JSON shows "ShortTermBorrowings" tagged under
exactly two 8-K filings ("current report" exhibits/disclosures) and nowhere else in WTRG's
entire filing history - no 10-K or 10-Q ever carries this concept for WTRG at all.

The 2026-08-31 fix (test_sec_statements_8k_duration_fact_excluded_20260831.py) already
excludes 8-K-sourced DURATION facts (has "start") for exactly this reason - an 8-K is a
"current report" for events/exhibits, never subject to the same XBRL-tagging rigor as a
periodic 10-K/10-Q filing - but only gated on `start_date and form in (8-K, 8-K/A)`, so an
8-K-sourced INSTANT fact (no "start", e.g. a balance-sheet snapshot) slipped through
untouched. The rationale is identical for both fact shapes; this widens the same exclusion
to cover instant facts too.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000078128"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestEightKInstantFactExcluded:
    def test_8k_sourced_instant_fact_not_used_as_balance_sheet_value(self):
        facts = {
            "us-gaap": {
                "LiabilitiesCurrent": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 764_483_000,
                            "filed": "2026-02-15",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                    ]
                ),
                "ShortTermBorrowings": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 1_588_000_000,
                            "filed": "2026-03-01",
                            "fp": None,
                            "fy": None,
                            "form": "8-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "WTRG", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        row_2025 = by_year[2025]
        assert row_2025["liabilities_current"] == 764_483_000
        # The 8-K-sourced instant fact must never be used, regardless of how plausible its
        # end date looks.
        assert row_2025.get("short_term_borrowings") is None
