"""Regression test for the 2026-09-17 divergence-repair follow-up: VOYG (Voyager
Technologies, CIK 0001788060) tags its real long-term debt only under
"ConvertibleDebtNoncurrent" - live-confirmed via real SEC companyfacts JSON, FY2025
$447,634,000 (exact match to the yfinance-flagged value) - and never tags plain
LongTermDebt/LongTermDebtNoncurrent/SecuredDebt/NotesPayable at all, which is why
long_term_debt sat wrong/stale despite the real filed fact existing.

Fallback-only (utils/external/sec_balance_sheet.py's get_balance_sheet() comment has the
full live evidence) - must never win over a real value the standard debt concepts already
found.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestVoygConvertibleDebtNoncurrentConcept:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "long_term_debt", "data_unavailable", "reason"})
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "convertible_debt_noncurrent": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"convertible_debt_noncurrent"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_new_concept(self) -> None:
        assert _BALANCE_FIELD_MAPPING["convertible_debt_noncurrent"] == "long_term_debt"
        assert "convertible_debt_noncurrent" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_voyg_style_convertible_debt_noncurrent_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "VOYG", "fiscal_year": 2025, "convertible_debt_noncurrent": 447_634_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 447_634_000.0

    def test_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMECORP",
            "fiscal_year": 2025,
            "long_term_debt": 500_000_000.0,
            "convertible_debt_noncurrent": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 500_000_000.0
