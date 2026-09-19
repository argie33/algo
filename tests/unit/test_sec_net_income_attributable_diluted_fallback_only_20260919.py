"""Regression test for the RKT/CTRM/HLLY/TEAD-class net_income_attributable_to_common bug
found live 2026-09-19 (/goal data-confidence audit).

Basic and diluted "net income available to common" (the NUMERATOR, not the per-share EPS) are
usually IDENTICAL for a plain capital structure - only the diluted SHARE COUNT differs. Live-
confirmed via real SEC companyfacts JSON across 4 unrelated filers (RKT, CTRM, HLLY, TEAD) that
when the two XBRL facts genuinely diverge, the Diluted fact reflects some NCI/if-converted
adjustment that's NOT representative of the real total attributable to common - the correct
figure (matching yfinance every time) is Basic. Before this fix, neither concept was
fallback-only, so ordinary last-listed-wins let Diluted (listed second in
_INCOME_FIELD_MAPPING) unconditionally overwrite Basic whenever a filer reported both -
live-confirmed wrong by up to ~14x (HLLY FY2022: Diluted $16,753,000 vs. real Basic
$73,774,000).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestNetIncomeAttributableDilutedFallbackOnly:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "net_income_attributable_to_common", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "net_income_loss_available_to_common_stockholders_basic": "net_income_attributable_to_common",
            "net_income_loss_available_to_common_stockholders_diluted": "net_income_attributable_to_common",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"net_income_loss_available_to_common_stockholders_diluted"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_diluted_does_not_overwrite_basic_when_both_present_and_diverge(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "HLLY",
            "fiscal_year": 2022,
            "net_income_loss_available_to_common_stockholders_basic": 73_774_000.0,
            "net_income_loss_available_to_common_stockholders_diluted": 16_753_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["net_income_attributable_to_common"] == 73_774_000.0

    def test_diluted_still_fills_when_basic_is_absent(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMECO",
            "fiscal_year": 2020,
            "net_income_loss_available_to_common_stockholders_diluted": 5_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["net_income_attributable_to_common"] == 5_000_000.0
