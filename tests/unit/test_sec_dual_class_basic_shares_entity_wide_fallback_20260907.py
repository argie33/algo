"""Regression test: dual-class filers' shares_outstanding_basic must not fall back to an
entity-wide (all-classes-combined) share count when the filer's real diluted count is
class-scoped.

Live-confirmed via Clearway Energy (CWEN, Class C common): real, undimensioned
WeightedAverageNumberOfDilutedSharesOutstanding = 35,000,000 (Class C only, matches
CWEN's own reported diluted EPS denominator exactly), but CommonStockSharesOutstanding =
203,773,674 (Class A+B+C combined balance-sheet total, since CWEN never tags
WeightedAverageNumberOfSharesOutstandingBasic at all). Before this fix,
shares_outstanding_basic silently took the entity-wide 203M value - an apples-to-oranges
comparison against the class-scoped 35M diluted figure, producing a nonsensical
shares_outstanding_basic > shares_outstanding_diluted result caught by tie_out.py's
check_diluted_ge_basic_shares (`60de22f75`).

Fixed: transform() now skips common_stock_shares_issued/common_stock_shares_outstanding's
contribution to shares_outstanding_basic entirely for any symbol with an active dual-class
sibling (see _get_dual_class_sibling_symbols), leaving the field NULL rather than storing a
mismatched entity-wide total.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestDualClassBasicSharesEntityWideFallback:
    def _make_loader(self, dual_class_siblings: frozenset[str]) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {
                "symbol",
                "fiscal_year",
                "shares_outstanding_basic",
                "shares_outstanding_diluted",
                "data_unavailable",
                "reason",
            }
        )
        loader._field_mapping = {
            "common_stock_shares_issued": "shares_outstanding_basic",
            "common_stock_shares_outstanding": "shares_outstanding_basic",
            "weighted_average_number_of_diluted_shares_outstanding": "shares_outstanding_diluted",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        loader._dual_class_sibling_symbols = dual_class_siblings
        return loader

    def test_dual_class_symbol_entity_wide_fallback_skipped(self) -> None:
        loader = self._make_loader(frozenset({"CWEN", "CWEN.A"}))
        row = {
            "symbol": "CWEN",
            "fiscal_year": 2025,
            "weighted_average_number_of_diluted_shares_outstanding": 35_000_000.0,
            "common_stock_shares_outstanding": 203_773_674.0,
        }
        (result,) = loader.transform([row])
        assert result["shares_outstanding_diluted"] == 35_000_000.0
        assert result.get("shares_outstanding_basic") is None

    def test_single_class_symbol_entity_wide_fallback_still_applies(self) -> None:
        loader = self._make_loader(frozenset())
        row = {
            "symbol": "WHD",
            "fiscal_year": 2018,
            "weighted_average_number_of_diluted_shares_outstanding": 26_648_000.0,
            "common_stock_shares_outstanding": 74_889_772.0,
        }
        (result,) = loader.transform([row])
        assert result["shares_outstanding_diluted"] == 26_648_000.0
        assert result["shares_outstanding_basic"] == 74_889_772.0
