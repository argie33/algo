"""Regression test for the 2026-09-07 fix (goal: XBRL concept-coverage backlog sweep):
"LongTermDebtAndCapitalLeaseObligations" is fetched as a fallback-only single-figure concept
for long_term_debt (XOM/CAT-style filers that never tag plain "LongTermDebt"), but for
filers that tag it alongside a separate "LongTermDebtAndCapitalLeaseObligationsCurrent"
current-maturities fact, the noncurrent-alone concept understates real total debt by
omitting the current portion - the same failure shape the pre-existing
LongTermDebtNoncurrent/LongTermDebtCurrent split fallback already fixed for the PLAIN
concept pair, just never mirrored for this one.

Live-confirmed via real SEC EDGAR companyfacts: 258 distinct filers / 1,263 filer-years
(Adobe, AT&T, AbbVie, Best Buy, Amphenol, American Water Works among them) tag both concepts
for a fiscal year with no plain LongTermDebt/LongTermDebtNoncurrent/
"...IncludingCurrentMaturities" fact present that year. AMD FY2015: noncurrent-shaped
concept=$2,032,000,000, current concept=$230,000,000, real total=$2,262,000,000 - the
current portion was silently dropped every such year.

Fix: "LongTermDebtAndCapitalLeaseObligationsCurrent" is fetched as an additional raw concept
and _fill_long_term_debt_from_noncurrent_current_split() sums it with the noncurrent concept
as a second, lower-priority pass (only firing when both halves are present, and when neither
the primary LongTermDebtNoncurrent/Current pair nor a real "...IncludingCurrentMaturities"
fact already resolved that fiscal year) - same "fallback-only, sum two real parts, never
overwrite a real combined value" pattern as the pre-existing pass in the same function.
"""

from typing import Any

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000002488"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestLongTermDebtAndCapitalLeaseObligationsCurrentSplitFallback:
    def test_amd_shaped_split_summed_when_no_other_source(self) -> None:
        facts = {
            "us-gaap": {
                "LongTermDebtAndCapitalLeaseObligations": {
                    "units": {"USD": [_entry(2015, 2_032_000_000.0, "2016-02-01")]}
                },
                "LongTermDebtAndCapitalLeaseObligationsCurrent": {
                    "units": {"USD": [_entry(2015, 230_000_000.0, "2016-02-01")]}
                },
            }
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "AMD", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2015]["long_term_debt"] == 2_262_000_000.0
        assert "long_term_debt_and_capital_lease_obligations" not in by_year[2015]
        assert "long_term_debt_and_capital_lease_obligations_current" not in by_year[2015]

    def test_noncurrent_only_no_current_tag_still_uses_existing_single_figure_fallback(self) -> None:
        # Most filers with this concept never tag a current-maturities sibling at all - must
        # still recover the existing (understood-as-a-limitation) single-figure fallback
        # rather than the new split logic blocking it.
        facts = {
            "us-gaap": {
                "LongTermDebtAndCapitalLeaseObligations": {
                    "units": {"USD": [_entry(2022, 6_433_800_000.0, "2023-02-01")]}
                },
            }
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # The fill function itself does not resolve this (no current tag) - the raw key
        # survives to the loader's own field_mapping fallback-only stage, not exercised here.
        assert by_year[2022].get("long_term_debt") is None
        assert by_year[2022]["long_term_debt_and_capital_lease_obligations"] == 6_433_800_000.0

    def test_real_combined_including_current_maturities_concept_not_overwritten(self) -> None:
        # A filer reporting the standard combined "...IncludingCurrentMaturities" total for
        # the same year must keep winning - this is the real, complete figure the new
        # lower-priority pass must not race ahead of.
        facts = {
            "us-gaap": {
                "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities": {
                    "units": {"USD": [_entry(2023, 10_046_300_000.0, "2024-02-01")]}
                },
                "LongTermDebtAndCapitalLeaseObligations": {
                    "units": {"USD": [_entry(2023, 999_000_000.0, "2024-02-01")]}
                },
                "LongTermDebtAndCapitalLeaseObligationsCurrent": {
                    "units": {"USD": [_entry(2023, 615_000_000.0, "2024-02-01")]}
                },
            }
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "APD", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # The fill function itself must not resolve long_term_debt here (it would be wrong,
        # 999M+615M=1.614B vs the real 10.046B) - it leaves the raw keys for the loader's own
        # field_mapping fallback-only stage, where
        # "...including_current_maturities" is fetched/mapped separately and wins.
        assert by_year[2023].get("long_term_debt") is None

    def test_plain_long_term_debt_concept_not_overwritten(self) -> None:
        facts = {
            "us-gaap": {
                "LongTermDebt": {"units": {"USD": [_entry(2025, 5_000_000_000.0, "2026-02-01")]}},
                "LongTermDebtAndCapitalLeaseObligations": {
                    "units": {"USD": [_entry(2025, 111_000_000.0, "2026-02-01")]}
                },
                "LongTermDebtAndCapitalLeaseObligationsCurrent": {
                    "units": {"USD": [_entry(2025, 22_000_000.0, "2026-02-01")]}
                },
            }
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TEST3", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["long_term_debt"] == 5_000_000_000.0
