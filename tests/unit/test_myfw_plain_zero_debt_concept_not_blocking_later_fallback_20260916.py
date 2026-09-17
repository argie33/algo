"""Regression test for the 2026-09-16 follow-up fix (same sweep as
test_cbnk_fhlb_advances_long_term_sibling_concept_20260916.py): MYFW (Mid-Southern Savings,
CIK 0001327607) tags a real "$0 of LongTermDebt" fact (a plain, non-fallback concept)
alongside a real, nonzero "FederalHomeLoanBankAdvancesLongTerm" fact ($10,000,000) for the
SAME fiscal year (2024) and filing.

Before this fix, whichever of the two concepts sec_balance_sheet.py's concept list processed
first won unconditionally: if the plain LongTermDebt=0 fact was processed first, it set
long_term_debt=0 in `row`, and the fallback-only gate's `db_field in row` check then
permanently blocked the later, real $10,000,000 fallback value from ever being considered -
treating an already-stored exact 0 as "a real total already resolved," which is wrong for a
multi-instrument field where a filer can report one instrument at $0 and another real one
nonzero simultaneously (same ambiguity as _DEBT_FALLBACK_ONLY_FIELDS' existing comments).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestMyfwPlainZeroDebtConceptNotBlockingLaterFallback:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "long_term_debt", "data_unavailable", "reason"})
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "federal_home_loan_bank_advances_long_term": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"federal_home_loan_bank_advances_long_term"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_real_nonzero_fallback_value_recovered_despite_earlier_plain_zero(self) -> None:
        loader = self._make_loader()
        # Dict-insertion order matters here: the plain "long_term_debt" (real $0) fact is
        # processed before the fallback-only FHLB concept, matching MYFW's real concept-list
        # order in sec_balance_sheet.py.
        row = {
            "symbol": "MYFW",
            "fiscal_year": 2024,
            "long_term_debt": 0.0,
            "federal_home_loan_bank_advances_long_term": 10_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 10_000_000.0

    def test_genuine_zero_total_debt_still_preserved_when_no_fallback_value_exists(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "DEBTFREECORP", "fiscal_year": 2024, "long_term_debt": 0.0}

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 0.0
