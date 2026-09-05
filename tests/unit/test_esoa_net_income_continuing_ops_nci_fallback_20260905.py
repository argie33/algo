"""Regression test for the 2026-09-05 fix (goal session: "SEC/XBRL missing data" sweep,
net_income_not_reported/eps_scale_mismatch investigation): ESOA (Energy Services of America,
CIK 0001357971) stopped tagging both "NetIncomeLoss" and "ProfitLoss" after FY2022 - live-
confirmed via real SEC companyfacts JSON, its real FY2025 bottom line ($379,708, fiscal year
ending 2025-09-30) is tagged solely under
"IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest"
instead. Without this fallback, net_income (and everything derived from it: ROA/ROE, EPS-based
ratios) was NULL for ESOA every fiscal year 2023-2025 despite it filing real, complete 10-Ks.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS

_NCI_KEY = "income_loss_from_continuing_operations_including_portion_attributable_to_noncontrolling_interest"


class TestEsoaNetIncomeContinuingOpsNciFallback:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "net_income", "data_unavailable", "reason"})
        loader._field_mapping = dict(_INCOME_FIELD_MAPPING)
        loader._fallback_only_fields = _REVENUE_FALLBACK_ONLY_FIELDS
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_the_concept_to_net_income(self) -> None:
        assert _INCOME_FIELD_MAPPING[_NCI_KEY] == "net_income"
        assert _NCI_KEY in _REVENUE_FALLBACK_ONLY_FIELDS

    def test_esoa_style_net_income_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "ESOA", "fiscal_year": 2025, _NCI_KEY: 379_708.0}

        transformed = loader.transform([row])

        assert transformed[0]["net_income"] == 379_708.0

    def test_never_overwrites_a_real_net_income_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "net_income_loss": 100_000_000_000.0,
            _NCI_KEY: 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["net_income"] == 100_000_000_000.0
