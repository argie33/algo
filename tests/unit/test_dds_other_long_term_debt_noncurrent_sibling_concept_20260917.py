"""Regression test for the 2026-09-17 divergence-repair follow-up fix: DDS (Dillard's) tags
its real long-term debt under "OtherLongTermDebtNoncurrent" - a more specific sibling of the
already-mapped "OtherLongTermDebt" concept (ACHV/BENF).

Live-confirmed via real SEC companyfacts JSON, CIK 0000028917: "OtherLongTermDebtNoncurrent"
$225,674,000 as of 2026-01-31 (DDS's FY2025 10-K, fiscal year ending late January) - never
tags LongTermDebt/NotesPayable/SubordinatedDebt/OtherLongTermDebt/SecuredLongTermDebt for
this period, which is why long_term_debt sat at NULL despite the real filed fact existing.

Fallback-only (utils/external/sec_balance_sheet.py's get_balance_sheet() comment has the full
live evidence) - must never win over a real value the standard debt concepts already found.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestDdsOtherLongTermDebtNoncurrentSiblingConcept:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "long_term_debt", "data_unavailable", "reason"})
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "other_long_term_debt_noncurrent": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"other_long_term_debt_noncurrent"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_new_concept(self) -> None:
        assert _BALANCE_FIELD_MAPPING["other_long_term_debt_noncurrent"] == "long_term_debt"
        assert "other_long_term_debt_noncurrent" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_dds_style_other_long_term_debt_noncurrent_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "DDS", "fiscal_year": 2026, "other_long_term_debt_noncurrent": 225_674_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 225_674_000.0

    def test_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMECORP",
            "fiscal_year": 2025,
            "long_term_debt": 500_000_000.0,
            "other_long_term_debt_noncurrent": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 500_000_000.0
