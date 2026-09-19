"""Regression test for the 2026-09-18 fix (goal session, WVVI short_term_debt investigation
follow-up): WVVI (Willamette Valley Vineyards) live-confirmed via its own real SEC companyfacts
JSON (CIK 0000838875) that its FY2025 short_term_debt is the SUM of three genuinely distinct,
simultaneously-outstanding current-debt components - NotesPayableCurrent ($884,221),
LongTermDebtCurrent ($1,008,215), and LineOfCredit ($3,140,140, redirected to short_term_debt by
redirect_line_of_credit_for_current_classification) - totaling $5,032,576, an EXACT match to
yfinance's own FY2025 figure for the same row.

Before this fix, "long_term_debt_current" had no field_mapping entry at all (fetched nowhere),
and even after adding it, the ordinary fallback-only mechanism only fills a single NULL slot -
it doesn't stack multiple fallback concepts together. See
is_wvvi_current_debt_component_additive's own docstring (sec_zero_component_guards.py) for the
narrow, symbol-scoped summing this test exercises.
"""

from unittest.mock import patch

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestWvviCurrentDebtComponentsAdditive:
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
            "notes_payable_current": "short_term_debt",
            "long_term_debt_current": "short_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"line_of_credit", "notes_payable_current", "long_term_debt_current"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_wvvi_fy2025_three_components_sum_to_exact_yfinance_match(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "WVVI",
            "fiscal_year": 2025,
            "notes_payable_current": 884_221.0,
            "long_term_debt_current": 1_008_215.0,
            "line_of_credit": 3_140_140.0,
        }

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 5_032_576.0
        assert transformed[0].get("long_term_debt") is None

    def test_order_independent_still_sums_to_the_same_total(self) -> None:
        """The three components are fetched in whatever order sec_balance_sheet.py's concept
        list processes them - the sum must not depend on which one happens to write first."""
        loader = self._make_loader()
        row = {
            "symbol": "WVVI",
            "fiscal_year": 2025,
            "line_of_credit": 3_140_140.0,
            "long_term_debt_current": 1_008_215.0,
            "notes_payable_current": 884_221.0,
        }

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 5_032_576.0

    def test_other_filer_components_do_not_sum(self) -> None:
        """Confirms the additive behavior is scoped to WVVI only - an ordinary filer reporting
        both notes_payable_current and long_term_debt_current must keep the ordinary
        fallback-only "first one wins, don't overwrite" behavior, not silently start summing."""
        loader = self._make_loader()
        row = {
            "symbol": "AAT",
            "fiscal_year": 2022,
            "notes_payable_current": 100_000.0,
            "long_term_debt_current": 250_000.0,
        }

        with patch.object(SecEdgarStatementLoader, "_get_reit_symbols", return_value=frozenset()):
            transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 100_000.0
