"""Regression test for the 2026-09-17 fix (goal: xbrl_yfinance_line_item_report remediation
follow-up): AVA (Avista Corp, CIK 0000104918) - a regulated electric/gas utility, not a REIT -
stopped tagging "LongTermDebtNoncurrent" after FY2022 and "LongTermDebtCurrent" after FY2023;
its real, ongoing first-mortgage-bond debt is tagged exclusively under "SecuredDebt" from then
on ($2,619,000,000 FY2024, $2,759,000,000 FY2025 - live-confirmed via real SEC companyfacts
JSON, tracking total_assets growth $7.70B -> $8.36B the way a utility's real long-term
mortgage-bond book should).

secured_debt -> short_term_debt was added 2026-09-09 on DE's evidence (a smaller
short-term-debt-adjacent sibling of DebtCurrent for that filer) and redirected to
long_term_debt for REIT-classified symbols by redirect_secured_debt_for_reit (OLP's fix,
2026-09-16). AVA never gets that redirect since it isn't REIT-classified, so it needs its
own narrow, symbol-scoped redirect (see sec_zero_component_guards.py's
redirect_secured_debt_for_utility_long_term_financing).
"""

from unittest.mock import patch

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestAvaUtilitySecuredDebtLongTermRedirect:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "secured_debt": "short_term_debt",
            "line_of_credit": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"secured_debt", "line_of_credit"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_ava_secured_debt_redirected_to_long_term_debt(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "AVA", "fiscal_year": 2025, "secured_debt": 2_759_000_000.0}

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 2_759_000_000.0
        assert transformed[0].get("short_term_debt") is None

    def test_ava_secured_debt_wins_over_smaller_line_of_credit_fallback(self) -> None:
        """Confirms SecuredDebt claims the long_term_debt slot ahead of a smaller, later-
        processed fallback (LineOfCredit) - the live shape that left AVA's stored
        long_term_debt at $3,000,000 before this fix.
        """
        loader = self._make_loader()
        row = {
            "symbol": "AVA",
            "fiscal_year": 2025,
            "secured_debt": 2_759_000_000.0,
            "line_of_credit": 3_000_000.0,
        }

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 2_759_000_000.0

    def test_de_style_non_utility_secured_debt_still_maps_to_short_term_debt(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "DE", "fiscal_year": 2025, "secured_debt": 1_000_000.0}

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 1_000_000.0
        assert transformed[0].get("long_term_debt") is None

    def test_never_overwrites_a_real_long_term_debt_value_for_ava(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AVA",
            "fiscal_year": 2025,
            "long_term_debt": 500_000_000.0,
            "secured_debt": 1.0,
        }

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 500_000_000.0
