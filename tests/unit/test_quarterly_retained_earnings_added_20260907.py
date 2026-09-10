"""Regression test for the 2026-09-07 fix (goal session, migration 1266):
quarterly_balance_sheet had no retained_earnings column, so the real SEC-tagged
"RetainedEarningsAccumulatedDeficit" concept - already fetched every quarter, for every
symbol, via the same concept list annual_balance_sheet uses - was discarded post-fetch with
an "Unmapped SEC field" warning instead of being written.

annual_balance_sheet has had this column since migration 1234; this fix brings
quarterly_balance_sheet to parity via its own _QUARTERLY_BALANCE_EXTRA mapping (kept separate
from the shared _QUARTERLY_EXTRA, same pattern _QUARTERLY_INCOME_EXTRA already established for
period_end - merging into the shared dict would break quarterly_income_statement/
quarterly_cash_flow, whose schema_cols don't have this column).
"""

from typing import Any

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import (
    _QUARTERLY_BALANCE_EXTRA,
    get_balance_sheet_config,
)


class TestQuarterlyRetainedEarningsWired:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        config = get_balance_sheet_config("quarterly")
        loader.table_name = config["table_name"]
        loader.period = "quarterly"
        loader.statement_type = "balance"
        loader._schema_cols = config["schema_cols"]
        loader._field_mapping = config["field_mapping"]
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_quarterly_balance_extra_maps_retained_earnings(self) -> None:
        assert _QUARTERLY_BALANCE_EXTRA["retained_earnings_accumulated_deficit"] == "retained_earnings"

    def test_quarterly_balance_config_has_retained_earnings_column(self) -> None:
        config = get_balance_sheet_config("quarterly")
        assert "retained_earnings" in config["schema_cols"]
        assert config["field_mapping"]["retained_earnings_accumulated_deficit"] == "retained_earnings"

    def test_quarterly_row_retained_earnings_recovered(self) -> None:
        loader = self._make_loader()
        row: dict[str, Any] = {
            "symbol": "AAPL",
            "fiscal_year": 2024,
            "fiscal_period": "Q3",
            "retained_earnings_accumulated_deficit": -19_154_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["retained_earnings"] == -19_154_000_000.0

    def test_other_quarterly_configs_unaffected(self) -> None:
        """retained_earnings must NOT leak into quarterly income_statement/cash_flow configs -
        that's the exact 2026-08-26 incident _ANNUAL_BALANCE_EXTRA's comment warns about,
        just for retained_earnings landing in the wrong statement type instead of the wrong
        period."""
        from loaders.load_financial_statements import get_statement_config

        income_config = get_statement_config("income", "quarterly")
        cashflow_config = get_statement_config("cashflow", "quarterly")
        assert "retained_earnings" not in income_config["schema_cols"]
        assert "retained_earnings" not in cashflow_config["schema_cols"]
