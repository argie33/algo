"""Regression test for the 2026-09-17 fix (goal: xbrl_yfinance_line_item_report remediation
follow-up, accounts_receivable cluster): HGTY (Hagerty, Inc., CIK 0001840776, an insurance MGA)
live-confirmed via real SEC companyfacts JSON, every fiscal year present in
xbrl_yfinance_line_item_report - tags a real, distinct "PremiumsReceivableAtCarryingValue" fact
ADDITIVE to plain "AccountsReceivableNetCurrent": FY2022 $58,255,000 + $100,700,000 =
$158,955,000, an EXACT match to yfinance's flagged value. Insurance-specific premiums
receivable is a genuinely separate balance-sheet component, not an alternate concept for
ordinary trade AR - this loader previously only extracted the plain trade-AR concept.
"""

from decimal import Decimal

from loaders.helpers.financial_statements_balance_config import get_balance_sheet_config
from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.helpers.sec_zero_component_guards import ADDITIVE_CONCEPT_PAIRS, is_additive_concept_pair


def _make_loader() -> SecEdgarStatementLoader:
    cfg = get_balance_sheet_config("annual")
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_balance_sheet"
    loader.period = "annual"
    loader.statement_type = "balance"
    loader._schema_cols = frozenset({"symbol", "fiscal_year", "accounts_receivable", "data_unavailable", "reason"})
    loader._field_mapping = cfg["field_mapping"]
    loader._fallback_only_fields = cfg.get("fallback_only_fields", frozenset())
    loader._reit_only_fallback_fields = frozenset()
    loader._reit_exclusive_fields = frozenset()
    loader._reit_symbols = frozenset()
    return loader


class TestAdditiveConceptPairRegistered:
    def test_pair_is_registered(self) -> None:
        assert ("accounts_receivable", "premiums_receivable_at_carrying_value") in ADDITIVE_CONCEPT_PAIRS

    def test_is_additive_concept_pair_fires(self) -> None:
        assert (
            is_additive_concept_pair(
                "accounts_receivable", "premiums_receivable_at_carrying_value", 58_255_000.0, 100_700_000.0
            )
            is True
        )


class TestTransformHgtyIntegration:
    def test_hgty_fy2022_sums_correctly(self) -> None:
        loader = _make_loader()
        row = {
            "symbol": "HGTY",
            "fiscal_year": 2022,
            "accounts_receivable_net_current": 58_255_000,
            "premiums_receivable_at_carrying_value": 100_700_000,
        }
        transformed = loader.transform([row])
        assert transformed[0]["accounts_receivable"] == 158_955_000

    def test_ordinary_filer_without_premiums_receivable_unaffected(self) -> None:
        loader = _make_loader()
        row = {
            "symbol": "ORDINARY",
            "fiscal_year": 2024,
            "accounts_receivable_net_current": 5_000_000,
        }
        transformed = loader.transform([row])
        assert transformed[0]["accounts_receivable"] == 5_000_000

    def test_decimal_inputs(self) -> None:
        loader = _make_loader()
        row = {
            "symbol": "HGTY",
            "fiscal_year": 2023,
            "accounts_receivable_net_current": Decimal("71530000"),
            "premiums_receivable_at_carrying_value": Decimal("137525000"),
        }
        transformed = loader.transform([row])
        assert transformed[0]["accounts_receivable"] == Decimal("209055000")
