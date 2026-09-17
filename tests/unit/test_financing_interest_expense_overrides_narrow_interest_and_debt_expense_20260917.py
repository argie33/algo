"""Regression test for the 2026-09-17 fix (goal session: xbrl_yfinance_line_item_report
remediation follow-up): TITN (Titan Machinery) FY2025 (period 2024-02-01 to 2025-01-31) tags a
real, nonzero "InterestAndDebtExpense" fact ($9,650,000, a genuinely different, smaller line
item, not the filer's total) alongside a real, much larger "FinancingInterestExpense" fact
($34,710,000) for the SAME fiscal year. Both are fallback-only concepts mapped to
interest_expense, and financial_statements_income_config.py's concept-list order processes
interest_and_debt_expense first - the ordinary fallback-only "db_field in row" skip then
permanently blocked financing_interest_expense from ever writing, even though its own real
value is ~3.6x larger.

Before this fix: stored interest_expense = InterestAndDebtExpense ($9,650,000) +
InterestExpenseOther ($15,105,000) = $24,755,000, vs. yfinance-flagged $53,993,000 (ratio
0.458, divergent under xbrl_yfinance_crosscheck.py's 2x/0.5x threshold).

After this fix: FinancingInterestExpense ($34,710,000) overrides the narrow
InterestAndDebtExpense value, then InterestExpenseOther's existing additive-pair handling
sums on top: $34,710,000 + $15,105,000 = $49,815,000 (ratio to yfinance ~0.923, no longer
divergent).

EPAC (Enerpac) is the one other live-confirmed filer where both concepts co-occur with real
nonzero values for the same period (FY2012: InterestAndDebtExpense=$16,830,000 vs.
FinancingInterestExpense=$29,561,000, ratio ~1.76x) - deliberately NOT overridden, since that
ordering is EPAC's own documented-correct behavior (see
financial_statements_income_config.py's "financing_interest_expense" comment). The guard's
3x magnitude floor sits between TITN's ~3.60x and EPAC's ~1.76x so it fires for TITN without
disturbing EPAC.

See loaders/helpers/sec_zero_component_guards.py's
is_financing_interest_expense_overriding_narrow_interest_and_debt_expense docstring for the
guard this tests.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestFinancingInterestExpenseOverridesNarrowInterestAndDebtExpense:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "interest_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "interest_and_debt_expense": "interest_expense",
            "financing_interest_expense": "interest_expense",
            "interest_expense_other": "interest_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_and_debt_expense", "financing_interest_expense"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_titn_fy2025_financing_interest_expense_overrides_narrow_total_then_sums_other(
        self,
    ) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "TITN",
            "fiscal_year": 2025,
            "interest_and_debt_expense": 9_650_000.0,
            "financing_interest_expense": 34_710_000.0,
            "interest_expense_other": 15_105_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 34_710_000.0 + 15_105_000.0

    def test_epac_style_modest_gap_does_not_override(self) -> None:
        """A ~1.76x gap (EPAC's live-confirmed shape) is well under the 3x floor and must not
        trigger the override - interest_and_debt_expense's documented-correct value for this
        filer stays."""
        loader = self._make_loader()
        row = {
            "symbol": "EPAC",
            "fiscal_year": 2012,
            "interest_and_debt_expense": 16_830_000.0,
            "financing_interest_expense": 29_561_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 16_830_000.0

    def test_override_only_fires_when_existing_value_sourced_from_interest_and_debt_expense(
        self,
    ) -> None:
        """Must not re-litigate an ordinary fallback-vs-fallback contest that already resolved
        via a different, unrelated concept."""
        loader = self._make_loader()
        loader._field_mapping["some_other_fallback_interest_concept"] = "interest_expense"
        loader._fallback_only_fields = frozenset(
            {
                "interest_and_debt_expense",
                "financing_interest_expense",
                "some_other_fallback_interest_concept",
            }
        )
        row = {
            "symbol": "TESTCO",
            "fiscal_year": 2025,
            "some_other_fallback_interest_concept": 5_000_000.0,
            "financing_interest_expense": 50_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 5_000_000.0

    def test_titn_fy2026_unaffected_when_interest_and_debt_expense_is_zero(self) -> None:
        """FY2026 shape (already fixed by ZERO_FIRST_WRITE_GUARD_FIELDS): InterestAndDebtExpense
        is a real $0, so the zero-first-write guard - not this new magnitude guard - is what
        lets FinancingInterestExpense through. Confirms the two guards don't conflict."""
        loader = self._make_loader()
        row = {
            "symbol": "TITN",
            "fiscal_year": 2026,
            "interest_and_debt_expense": 0.0,
            "financing_interest_expense": 24_109_000.0,
            "interest_expense_other": 18_974_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 24_109_000.0 + 18_974_000.0
