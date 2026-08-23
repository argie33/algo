"""Regression test for a priority-inversion bug found live 2026-08-22 (goal session:
real-money-readiness audit), a second follow-up to the same-day AROW community-bank
revenue-gap fix.

interest_income_operating and interest_and_dividend_income_operating both map to
"revenue" and were both made fallback-only (skip if "revenue" already populated) by a
2026-08-09 fix - but a 2026-08-03 comment on interest_income_operating's concept entry
in sec_statements.py still claimed "MUST be listed BEFORE
InterestAndDividendIncomeOperating: ... the '+dividend' variant is the more complete
figure for them - it must win the last-listed-wins overwrite". That comment was true
under the OLD (pre-2026-08-09) normal-overwrite semantics, but became backwards once
both concepts turned fallback-only: under "skip if already populated", whichever concept
is PROCESSED FIRST wins (not last), so listing the narrower interest_income_operating
first let it silently win over the real, complete total whenever both were present.

Live-confirmed via AMTB (a bank holding company, SIC 6022): FY2022
InterestIncomeOperating=$200,000 (a minor, incidental line) vs.
InterestAndDividendIncomeOperating=$338,776,000 (the real, complete total, consistent
with AMTB's real net_income that year) - the $200,000 figure was winning and being
stored as "revenue", a ~1,694x understatement.

Fixed by reordering the two concepts in sec_statements.py's get_income_statement() so
InterestAndDividendIncomeOperating is processed first, restoring the intended priority.
"""

import inspect

from loaders.helpers.sec_base import SecEdgarStatementLoader
from utils.external.sec_statements import get_income_statement


class TestInterestAndDividendIncomeWinsOverNarrowerInterestIncome:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "interest_income_operating": "revenue",
            "interest_and_dividend_income_operating": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset(
            {"interest_income_operating", "interest_and_dividend_income_operating"}
        )
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        loader._depository_institution_symbols = frozenset()
        return loader

    def test_concepts_list_orders_dividend_variant_before_narrower_variant(self) -> None:
        source = inspect.getsource(get_income_statement)
        dividend_idx = source.index('"InterestAndDividendIncomeOperating"')
        narrower_idx = source.index('"InterestIncomeOperating"')
        assert dividend_idx < narrower_idx, (
            "InterestAndDividendIncomeOperating must be listed (and therefore processed) "
            "before InterestIncomeOperating so it wins fallback-only 'first written wins'"
        )

    def test_complete_dividend_variant_wins_over_narrower_incidental_line(self) -> None:
        """Dict key order mirrors sec_statements.py's concepts-list order (the real
        production insertion order, driven by _aggregate_concepts iterating that list)."""
        loader = self._make_loader()
        row = {
            "symbol": "AMTB",
            "fiscal_year": 2022,
            "interest_and_dividend_income_operating": 338_776_000.0,
            "interest_income_operating": 200_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 338_776_000.0

    def test_narrower_variant_still_wins_when_dividend_variant_absent(self) -> None:
        """Mortgage REITs (AGNC, NLY) report only InterestIncomeOperating - it must still
        populate revenue when it's the only one of the pair present."""
        loader = self._make_loader()
        row = {
            "symbol": "AGNC",
            "fiscal_year": 2023,
            "interest_income_operating": 1_500_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_500_000_000.0
