"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep,
our_value=0-vs-real-yfinance-value audit): OLP (One Liberty Properties, an equity REIT)
tags its real, primary mortgage debt under "SecuredDebt" - live-confirmed via real SEC
companyfacts JSON growing steadily $396M (FY2021) -> $517M (FY2025), tracking
total_assets ($753M -> $858M) the way a REIT's real estate financing should.

"secured_debt" -> "short_term_debt" was added 2026-09-09 on DE's evidence (a smaller
short-term-debt-adjacent sibling of DebtCurrent for that filer). That's wrong for equity
REITs, whose SecuredDebt is their PRIMARY long-term mortgage financing - $517M is
implausible as "short-term debt" for an $858M-asset company. Redirected to
long_term_debt for REIT-classified symbols only; DE and every other non-REIT filer keep
the original short_term_debt mapping.
"""

from unittest.mock import patch

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestOlpSecuredDebtReitRedirectToLongTermDebt:
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
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"secured_debt"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_olp_style_reit_secured_debt_redirected_to_long_term_debt(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "OLP", "fiscal_year": 2025, "secured_debt": 517_342_000.0}

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset({"OLP"})):
            transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 517_342_000.0
        assert transformed[0].get("short_term_debt") is None

    def test_de_style_non_reit_secured_debt_still_maps_to_short_term_debt(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "DE", "fiscal_year": 2025, "secured_debt": 1_000_000.0}

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset({"OLP"})):
            transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 1_000_000.0
        assert transformed[0].get("long_term_debt") is None

    def test_never_overwrites_a_real_long_term_debt_value_for_reit(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "OLP",
            "fiscal_year": 2025,
            "long_term_debt": 500_000_000.0,
            "secured_debt": 1.0,
        }

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset({"OLP"})):
            transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 500_000_000.0
