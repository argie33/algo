"""Regression test for adding us-gaap:Dividends (utils/external/sec_cash_flow.py), found
while investigating quality_metrics.payout_ratio_unavailable_reason='missing_sec_data' rows
for real dividend-paying companies as part of the "missing SEC/XBRL data under 300" push.

TPG (TPG Inc., the alternative-asset manager, CIK 1880661) tags neither "PaymentsOfDividends"
nor any DividendsCommonStock*/DividendsPreferredStock*/PaymentsOfCapitalDistribution variant -
live-confirmed via real companyfacts JSON its only dividend-shaped concept at all is the bare
standard us-gaap:Dividends tag, reported every fiscal year with real, growing duration facts
($656.8M FY2023, $833.4M FY2024).

Fallback-only (_SBC_BUYBACK_FALLBACK_ONLY_FIELDS) since a bare "Dividends" tag is ambiguous
enough (dividends declared vs. paid, or dividend income received for an investment-company-
shaped filer) that it must never overwrite a real standard-concept value.
"""

import inspect

from loaders.helpers.financial_statements_cashflow_config import (
    _CASHFLOW_FIELD_MAPPING,
    _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
)
from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_cash_flow_config
from utils.external import sec_statements
from utils.external.sec_statements import _to_snake


class TestTpgDividendsBareConceptFallback:
    def test_concept_maps_to_dividends_paid(self) -> None:
        target_key = _to_snake("Dividends")
        assert target_key == "dividends"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "dividends_paid"
        assert target_key in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_concept_is_actually_fetched(self) -> None:
        source = inspect.getsource(sec_statements.get_cash_flow)
        assert '"Dividends"' in source

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

    def test_bare_concept_fills_dividends_paid_when_nothing_else_tagged(self) -> None:
        """A filer with no standard dividend concept tagged at all (e.g. TPG) previously got
        NULL dividends_paid despite having real bare-"Dividends" distribution data."""
        loader = self._make_loader()
        row = {"symbol": "TEST", "fiscal_year": 2025, "dividends": 833_380_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["dividends_paid"] == 833_380_000.0

    def test_never_overwrites_real_standard_concept_dividend_total(self) -> None:
        """Fallback-only: a filer reporting BOTH concepts keeps the standard-concept total
        unchanged, regardless of dict iteration order."""
        loader = self._make_loader()
        row = {
            "symbol": "TEST",
            "fiscal_year": 2025,
            "dividends": 833_380_000.0,
            "dividends_common_stock_cash": 50_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["dividends_paid"] == 50_000_000.0
