"""Regression test for the 2026-09-09 fix (goal session: "SEC/XBRL missing data under 500"
sweep, operating_income_not_itemized investigation): BNY (Bank of New York Mellon, CIK
0001390777) reports real "InterestIncomeExpenseNet", "NoninterestIncome", and
"NoninterestExpense" every fiscal year but tags NO OperatingIncomeLoss/CostsAndExpenses/
OperatingExpenses concept anywhere in its filing history - live-confirmed via real
companyfacts JSON. FY2025: $4,944,000,000 + $15,136,000,000 - $13,054,000,000 =
$7,026,000,000, consistent with BNY's real FY2025 NetIncomeLoss of $5,549,000,000 at a
plausible implied effective tax rate.
"""

from utils.external.sec_income_statement_fallbacks import (
    _fill_operating_income_from_bank_net_interest_and_noninterest,
)


class TestBnyOperatingIncomeFromBankNetInterest:
    def test_bny_style_operating_income_recovered(self) -> None:
        rows = [
            {
                "interest_income_expense_net": 4_944_000_000.0,
                "noninterest_income": 15_136_000_000.0,
                "noninterest_expense": 13_054_000_000.0,
            }
        ]

        _fill_operating_income_from_bank_net_interest_and_noninterest(rows)

        assert rows[0]["operating_income_loss"] == 7_026_000_000.0
        # Temp keys unique to this derivation must not leak downstream as unmapped fields.
        assert "interest_income_expense_net" not in rows[0]
        assert "noninterest_income" not in rows[0]
        assert "noninterest_expense" not in rows[0]

    def test_never_overwrites_a_real_operating_income_value(self) -> None:
        rows = [
            {
                "operating_income_loss": 999.0,
                "interest_income_expense_net": 4_944_000_000.0,
                "noninterest_income": 15_136_000_000.0,
                "noninterest_expense": 13_054_000_000.0,
            }
        ]

        _fill_operating_income_from_bank_net_interest_and_noninterest(rows)

        assert rows[0]["operating_income_loss"] == 999.0

    def test_does_not_fire_when_any_required_term_missing(self) -> None:
        rows = [
            {
                "interest_income_expense_net": 4_944_000_000.0,
                "noninterest_income": 15_136_000_000.0,
                # noninterest_expense missing
            }
        ]

        _fill_operating_income_from_bank_net_interest_and_noninterest(rows)

        assert "operating_income_loss" not in rows[0]
        # The two present keys are still popped even when the fallback doesn't fire, so
        # they never leak as an unmapped-field warning for a filer this doesn't apply to.
        assert "interest_income_expense_net" not in rows[0]
        assert "noninterest_income" not in rows[0]
