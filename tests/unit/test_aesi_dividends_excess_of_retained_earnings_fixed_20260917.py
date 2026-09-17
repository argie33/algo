"""Regression test for the 2026-09-17 fix (goal session: data-coverage-metrics accuracy sweep,
xbrl_yfinance_line_item_report dividends_paid audit): AESI (Atlas Energy Solutions) real,
cash-paid return-of-capital-in-excess-of-earnings distribution.

Live-confirmed via real SEC companyfacts JSON: AdjustmentsToAdditionalPaidInCapitalDividends
InExcessOfRetainedEarnings=$92,281,000 FY2025, EXACT match to the yfinance-flagged value,
consistent with the filer's own CommonStockDividendsPerShareCashPaid=$0.75/share fact on file
the same year. No DividendsCommonStock*/PaymentsOfDividends* concept tagged at all for this
filer - this is its only dividend-shaped cash outflow concept, so dividends_paid stayed 0.

Fallback-only (_SBC_BUYBACK_FALLBACK_ONLY_FIELDS), same never-overwrite-a-real-standard-
dividend-total convention as every other entry in that set (see
test_tpg_dividends_bare_concept_fallback_20260910.py's equivalent tests).
"""

import inspect

from loaders.helpers.financial_statements_cashflow_config import (
    _CASHFLOW_FIELD_MAPPING,
    _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
)
from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_cash_flow_config
from utils.external import sec_statements


class TestAesiDividendsExcessOfRetainedEarningsFixed:
    _TARGET_KEY = "adjustments_to_additional_paid_in_capital_dividends_in_excess_of_retained_earnings"

    def test_concept_maps_to_dividends_paid_and_is_fallback_only(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING[self._TARGET_KEY] == "dividends_paid"
        assert self._TARGET_KEY in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_concept_is_actually_fetched(self) -> None:
        source = inspect.getsource(sec_statements.get_cash_flow)
        assert "AdjustmentsToAdditionalPaidInCapitalDividendsInExcessOfRetainedEarnings" in source

    def _make_loader(self) -> ConsolidatedFinancialStatementsLoader:
        loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
        config = get_cash_flow_config("annual")
        loader.table_name = config["table_name"]
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = config["schema_cols"]
        loader._field_mapping = config["field_mapping"]
        loader._fallback_only_fields = config.get("fallback_only_fields", frozenset())
        return loader

    def test_aesi_style_fills_dividends_paid_when_nothing_else_tagged(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "AESI", "fiscal_year": 2025, self._TARGET_KEY: 92_281_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["dividends_paid"] == 92_281_000.0

    def test_never_overwrites_real_standard_concept_dividend_total(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "TEST",
            "fiscal_year": 2025,
            self._TARGET_KEY: 92_281_000.0,
            "dividends_common_stock_cash": 50_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["dividends_paid"] == 50_000_000.0
