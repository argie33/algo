"""Regression tests for two real fallback gaps in get_balance_sheet()
(utils/external/sec_balance_sheet.py) - goal: "under 500" push, total_debt_not_itemized
investigation, 2026-09-10.

1. DCX (Digital Currency X Technology, a 20-F filer) tags a real, continuous
   "LongTermDebtCurrent" ($95.16M FY2024/$96.96M FY2025) with NO "LongTermDebtNoncurrent"
   sibling ever - live-confirmed via real SEC companyfacts JSON. Before this fix,
   _fill_long_term_debt_from_noncurrent_current_split only ever used `current` when
   `noncurrent` was also present (`noncurrent is not None` gated both of its branches), so
   a Current-only filer's real debt figure was popped and silently discarded, leaving
   long_term_debt NULL despite total_liabilities/stockholders_equity both being populated.

2. MWG (a different 20-F filer) tags real, continuous us-gaap
   "FinanceLeaseLiabilityCurrent"/"FinanceLeaseLiabilityNoncurrent" (summing to ~$5.1M
   FY2025) and "OperatingLeaseLiabilityCurrent"/"OperatingLeaseLiabilityNoncurrent", but
   never the combined "FinanceLeaseLiability"/"OperatingLeaseLiability" concepts that were
   the only ones fetched before this fix - live-confirmed via real SEC companyfacts JSON.
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
    return {"end": end, "val": val, "filed": filed, "fp": "FY", "fy": fy, "form": "20-F"}


class TestLongTermDebtCurrentOnlyFallback:
    def test_dcx_shaped_current_only_no_noncurrent_sibling(self):
        facts = {
            "us-gaap": {
                "LongTermDebtCurrent": _concept([_entry("2025-12-31", 96_962_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "DCX", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["long_term_debt"] == 96_962_000.0
        assert "long_term_debt_current" not in by_year[2025]
        assert "long_term_debt_noncurrent" not in by_year[2025]

    def test_real_long_term_debt_concept_not_overwritten_by_current_only_fallback(self):
        facts = {
            "us-gaap": {
                "LongTermDebt": _concept([_entry("2025-12-31", 100_000_000.0, "2026-02-25")]),
                "LongTermDebtCurrent": _concept([_entry("2025-12-31", 5_000_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["long_term_debt"] == 100_000_000.0


class TestUsGaapLeaseLiabilityCurrentNoncurrentSplitFallback:
    def test_mwg_shaped_finance_and_operating_lease_split(self):
        facts = {
            "us-gaap": {
                "FinanceLeaseLiabilityCurrent": _concept([_entry("2025-12-31", 2_529_000.0, "2026-02-25")]),
                "FinanceLeaseLiabilityNoncurrent": _concept([_entry("2025-12-31", 2_582_000.0, "2026-02-25")]),
                "OperatingLeaseLiabilityCurrent": _concept([_entry("2025-12-31", 1_000_000.0, "2026-02-25")]),
                "OperatingLeaseLiabilityNoncurrent": _concept([_entry("2025-12-31", 4_000_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "MWG", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["finance_lease_liability"] == 5_111_000.0
        assert by_year[2025]["operating_lease_liability"] == 5_000_000.0
        assert "finance_lease_liability_current" not in by_year[2025]
        assert "finance_lease_liability_noncurrent" not in by_year[2025]
        assert "operating_lease_liability_current" not in by_year[2025]
        assert "operating_lease_liability_noncurrent" not in by_year[2025]

    def test_only_one_half_tagged_stays_null_not_partial_sum(self):
        facts = {
            "us-gaap": {
                "FinanceLeaseLiabilityCurrent": _concept([_entry("2025-12-31", 2_529_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST2", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025].get("finance_lease_liability") is None

    def test_real_combined_concept_not_overwritten_by_split_fallback(self):
        facts = {
            "us-gaap": {
                "FinanceLeaseLiability": _concept([_entry("2025-12-31", 1_230_000_000.0, "2026-02-25")]),
                "FinanceLeaseLiabilityCurrent": _concept([_entry("2025-12-31", 999_000_000.0, "2026-02-25")]),
                "FinanceLeaseLiabilityNoncurrent": _concept([_entry("2025-12-31", 999_000_000.0, "2026-02-25")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST3", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["finance_lease_liability"] == 1_230_000_000.0
