"""Regression test for the 2026-09-17 fix (goal: xbrl_yfinance_line_item_report remediation
follow-up): RYZ (Ryerson Holding, CIK 0001481582) FY2024 (period end 2024-12-31) live-confirmed
via real SEC companyfacts JSON - tags no plain "LongTermDebt"/"LongTermDebtNoncurrent" at all,
only "LongTermDebtCurrent"=$700,000 AND the real, much larger fallback-only combined concept
"DebtLongtermAndShorttermCombinedAmount"=$467,400,000 (yfinance-flagged $466,700,000, same order
of magnitude - the real total).

Before this fix, utils/external/sec_balance_sheet.py's
_fill_long_term_debt_from_noncurrent_current_split() "current-portion-only" convenience branch
(added for DCX, see test_dcx_current_only_debt_and_mwg_lease_split_20260910.py) fired BEFORE
sec_base.py's transform() ever processed the fallback-only combined concept, claiming the
"long_term_debt" raw key with just $700,000 - since that function runs at raw-concept-assembly
time, this premature claim meant transform()'s fallback-only "db_field in row" check saw
long_term_debt as already populated and permanently blocked the real
$467,400,000 combined total from ever winning.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001481582"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


def _entry(end: str, val: float, filed: str, fy: int = 2024) -> dict:
    return {"end": end, "val": val, "filed": filed, "fp": "FY", "fy": fy, "form": "10-K"}


class TestRyzCurrentPortionOnlyNotBlockingCombinedTotal:
    def test_ryz_shaped_current_portion_yields_to_real_combined_total(self):
        facts = {
            "us-gaap": {
                "LongTermDebtCurrent": _concept([_entry("2024-12-31", 700_000.0, "2025-02-20")]),
                "DebtLongtermAndShorttermCombinedAmount": _concept([_entry("2024-12-31", 467_400_000.0, "2025-02-20")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "RYZ", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # The raw-concept-assembly layer must not have claimed the slot with the tiny
        # current-portion figure - the real combined-total fallback concept must still be
        # present so transform() gets a chance to write it.
        assert by_year[2024].get("long_term_debt") is None
        assert by_year[2024]["debt_longterm_and_shortterm_combined_amount"] == 467_400_000.0

    def test_current_portion_only_still_recovered_when_no_combined_total_present(self):
        """DCX-shaped case (this function's own original fix) must be unaffected: a filer
        with only a current-portion tag and no combined-total sibling must still get that
        figure recovered rather than left NULL.
        """
        facts = {
            "us-gaap": {
                "LongTermDebtCurrent": _concept([_entry("2024-12-31", 96_962_000.0, "2025-02-20")]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "DCX", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2024]["long_term_debt"] == 96_962_000.0
