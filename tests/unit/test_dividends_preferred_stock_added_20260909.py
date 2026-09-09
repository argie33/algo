"""Regression test for adding us-gaap:DividendsPreferredStockCash/DividendsPreferredStock
(utils/external/sec_cash_flow.py), found via the 2026-09-09 xbrl_concept_coverage_scan.py
comment-leak fix (see test_xbrl_concept_coverage_comment_leak_20260909.py) - these two
standard us-gaap concepts were quoted in a comment (explaining what
PaymentsOfCapitalDistribution equals) but never actually fetched. 639 real filers tag
"DividendsPreferredStock" alone (scan-confirmed post-fix), e.g. preferred-only distributors
(mortgage REITs/BDCs with no common dividend at all) that previously got NULL dividends_paid.

Fallback-only (_SBC_BUYBACK_FALLBACK_ONLY_FIELDS) so a filer that also tags a real
DividendsCommonStock*/PaymentsOfDividends* total keeps that fuller combined-distribution
figure unchanged - this must never overwrite it (would silently understate total
distributions to just the preferred component).
"""

import inspect

from loaders.helpers.financial_statements_cashflow_config import (
    _CASHFLOW_FIELD_MAPPING,
    _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
)
from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_cash_flow_config
from utils.external import sec_statements
from utils.external.sec_statements import _to_snake


class TestDividendsPreferredStockAdded:
    def test_concepts_map_to_dividends_paid(self) -> None:
        for concept in ("DividendsPreferredStockCash", "DividendsPreferredStock"):
            target_key = _to_snake(concept)
            assert _CASHFLOW_FIELD_MAPPING[target_key] == "dividends_paid"
            assert target_key in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_concepts_are_actually_fetched(self) -> None:
        source = inspect.getsource(sec_statements.get_cash_flow)
        assert "DividendsPreferredStockCash" in source
        assert "DividendsPreferredStock" in source

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

    def test_preferred_only_distributor_fills_dividends_paid(self) -> None:
        """A filer with no common dividend concept tagged at all (e.g. a mortgage REIT with
        only preferred stock outstanding) previously got NULL dividends_paid despite having
        real preferred distribution data."""
        loader = self._make_loader()
        row = {"symbol": "TEST", "fiscal_year": 2025, "dividends_preferred_stock_cash": 5_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["dividends_paid"] == 5_000_000.0

    def test_never_overwrites_real_common_stock_dividend_total(self) -> None:
        """Fallback-only: a filer reporting BOTH concepts keeps the (fuller) common-stock
        total unchanged, regardless of dict iteration order."""
        loader = self._make_loader()
        row = {
            "symbol": "TEST",
            "fiscal_year": 2025,
            "dividends_preferred_stock_cash": 5_000_000.0,
            "dividends_common_stock_cash": 50_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["dividends_paid"] == 50_000_000.0
