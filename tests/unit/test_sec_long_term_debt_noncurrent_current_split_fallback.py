"""Regression test for a real fallback gap in get_balance_sheet()
(utils/external/sec_statements.py) - "no SEC data"/loader-audit goal, 2026-08-18
continuation.

Live-confirmed via real SEC companyfacts JSON: PFE stopped tagging plain "LongTermDebt"
after FY2020 (last fact end=2020-12-31) - every 10-K since splits it into
"LongTermDebtNoncurrent" ($61,641,000,000 for FY2025) and "LongTermDebtCurrent"
($2,997,000,000 for FY2025) instead, same real ~$64.6B total debt load under different
concepts. F (Ford Motor Co.) never tags plain "LongTermDebt" at all, only the Noncurrent
variant. Neither concept was covered by any existing fallback
(NotesPayableRelatedPartiesNoncurrent / LongTermNotesPayable / ConvertibleNotesPayable /
ConvertibleLongTermNotesPayable / LongTermDebtAndCapitalLeaseObligationsIncludingCurrent
Maturities), so both filers - not obscure micro-caps, two of the most widely held stocks in
the market - were silently treated as debt-free (long_term_debt NULL every fiscal year),
degrading debt_to_equity/debt_to_assets/interest_coverage/total_debt/roic_pct.

Fix: LongTermDebtNoncurrent and LongTermDebtCurrent are now fetched and summed into
long_term_debt as a post-processing fallback step (only when the primary concept is
absent) - genuinely different aggregation than the plain "last value wins" merge
_aggregate_concepts already does for every other concept in this file, per the existing
"Deliberately NOT also fetching the Current/Noncurrent variants" comment on the
OperatingLeaseLiability/FinanceLeaseLiability concepts just above these two.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000078003"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


def _entry(end: str, val: float, filed: str, fy: int = 2025) -> dict:
    return {"end": end, "val": val, "filed": filed, "fp": "FY", "fy": fy, "form": "10-K"}


class TestLongTermDebtNoncurrentCurrentSplitFallback:
    def test_pfe_shaped_split_concepts_summed_into_long_term_debt(self):
        facts = {
            "us-gaap": {
                "LongTermDebtNoncurrent": _concept([_entry("2025-12-31", 61_641_000_000.0, "2026-02-25")]),
                "LongTermDebtCurrent": _concept([_entry("2025-12-31", 2_997_000_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "PFE", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["long_term_debt"] == 64_638_000_000.0
        assert "long_term_debt_noncurrent" not in by_year[2025]
        assert "long_term_debt_current" not in by_year[2025]

    def test_ford_shaped_noncurrent_only_no_current_tag(self):
        # F never tags a current-portion concept at all for some years - must still use
        # the noncurrent figure alone rather than staying NULL.
        facts = {
            "us-gaap": {
                "LongTermDebtNoncurrent": _concept([_entry("2025-12-31", 92_000_000_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "F", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["long_term_debt"] == 92_000_000_000.0

    def test_real_long_term_debt_concept_not_overwritten_by_split_fallback(self):
        # A filer reporting the standard combined "LongTermDebt" concept must keep that
        # value even if a stray Noncurrent/Current split fact also exists for the same
        # year (e.g. a dimensional/segment breakdown) - fallback-only, never overwrites.
        facts = {
            "us-gaap": {
                "LongTermDebt": _concept([_entry("2025-12-31", 100_000_000.0, "2026-02-25")]),
                "LongTermDebtNoncurrent": _concept([_entry("2025-12-31", 999_000_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["long_term_debt"] == 100_000_000.0
