"""Regression test for the 2026-09-18 fix (goal session: xbrl_yfinance_line_item_report
short_term_debt remediation): WVVI (Willamette Valley Vineyards) live-confirmed via its own
filed SEC calculation linkbase (FY2023/2024/2025 10-Ks) - "LineOfCredit" is declared as a
direct child of the "LiabilitiesCurrent" calculation total in every one of these filings, not
"Liabilities" - meaning the filer itself classifies this facility as CURRENT debt on its own
balance sheet. The blanket "line_of_credit" -> long_term_debt mapping
(financial_statements_balance_config.py) understated WVVI's real short_term_debt by roughly the
size of its LineOfCredit balance every year (our stored value ~$0.9-1.2M vs yfinance's
~$1.9-5.0M).

See sec_zero_component_guards.py's redirect_line_of_credit_for_current_classification for the
narrow, symbol-scoped fix - most other filers checked in this same review pass have LineOfCredit
rolling up under total Liabilities (no current/noncurrent split at all, an unclassified balance
sheet) or under long-term financing, so this is deliberately NOT a blanket rule.
"""

from unittest.mock import patch

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestWvviLineOfCreditCurrentRedirect:
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
            "short_term_debt": "short_term_debt",
            "line_of_credit": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"line_of_credit"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_wvvi_line_of_credit_redirected_to_short_term_debt(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "WVVI", "fiscal_year": 2024, "line_of_credit": 995_968.0}

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 995_968.0
        assert transformed[0].get("long_term_debt") is None

    def test_other_filer_line_of_credit_still_maps_to_long_term_debt(self) -> None:
        """Confirms the redirect is scoped to WVVI only - most other filers checked in this
        same review pass have LineOfCredit rolling up under total Liabilities (no split) or
        real long-term financing, so the default mapping must stay unchanged for them."""
        loader = self._make_loader()
        row = {"symbol": "AAT", "fiscal_year": 2022, "line_of_credit": 34_057_000.0}

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 34_057_000.0
        assert transformed[0].get("short_term_debt") is None

    def test_sums_with_an_existing_real_short_term_debt_value_for_wvvi(self) -> None:
        """UPDATED 2026-09-18 (follow-up fix, see
        test_wvvi_current_debt_components_additive_20260918.py): the original version of this
        test asserted line_of_credit could never add onto an already-populated short_term_debt
        for WVVI - that was true only because is_wvvi_current_debt_component_additive didn't
        exist yet. Live SEC evidence (WVVI FY2025: NotesPayableCurrent + LongTermDebtCurrent +
        LineOfCredit sums to an EXACT match of yfinance's figure) shows these ARE genuinely
        distinct, simultaneously-outstanding components for this filer, so the intentional
        behavior for WVVI specifically is now to sum, not block."""
        loader = self._make_loader()
        row = {
            "symbol": "WVVI",
            "fiscal_year": 2024,
            "short_term_debt": 500_000.0,
            "line_of_credit": 1.0,
        }

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 500_001.0

    def test_still_blocks_overwrite_for_a_non_wvvi_symbol(self) -> None:
        """Confirms the new additive behavior above is scoped to WVVI only - an ordinary filer
        must keep the ordinary fallback-only "never overwrite an already-populated value"
        protection, using notes_payable_current (a sec_field that maps straight to
        short_term_debt for every filer, not just via the WVVI-only redirect) so this actually
        exercises the guard's symbol check rather than trivially no-op'ing via the redirect."""
        loader = self._make_loader()
        loader._field_mapping["notes_payable_current"] = "short_term_debt"
        loader._fallback_only_fields = frozenset({"line_of_credit", "notes_payable_current"})
        row = {
            "symbol": "AAT",
            "fiscal_year": 2022,
            "short_term_debt": 500_000.0,
            "notes_payable_current": 1.0,
        }

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 500_000.0
