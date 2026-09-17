"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep,
our_value=0-vs-real-yfinance-value audit):

1. PED (Predictive Oncology) tags its real receivables under plain "AccountsReceivableNet"
   (no "Current" suffix, a distinct concept from "AccountsReceivableNetCurrent" already
   fetched) - $25,666,000 FY2025, exactly matching the yfinance-flagged value, live-
   confirmed via real SEC companyfacts JSON - while its own "ReceivablesNetCurrent" fact is
   a real $0 that resolves first. Before the zero_blocking_real_value guard extension, that
   earlier $0 would have permanently blocked this fallback-only concept's real value.

2. DNLI (Denali Therapeutics) tags its real receivables under
   "AccountsAndOtherReceivablesNetCurrent" instead ($2,177,000 FY2025, also exactly
   matching) - never fetched at all before this fix.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestPedDnliReceivablesConceptsFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "accounts_receivable", "data_unavailable", "reason"})
        loader._field_mapping = {
            "accounts_receivable": "accounts_receivable",
            "receivables_net_current": "accounts_receivable",
            "accounts_receivable_net": "accounts_receivable",
            "accounts_and_other_receivables_net_current": "accounts_receivable",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset(
            {"receivables_net_current", "accounts_receivable_net", "accounts_and_other_receivables_net_current"}
        )
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_new_concepts_fallback_only(self) -> None:
        assert _BALANCE_FIELD_MAPPING["accounts_receivable_net"] == "accounts_receivable"
        assert _BALANCE_FIELD_MAPPING["accounts_and_other_receivables_net_current"] == "accounts_receivable"
        assert "accounts_receivable_net" in _DEBT_FALLBACK_ONLY_FIELDS
        assert "accounts_and_other_receivables_net_current" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_ped_style_zero_from_earlier_concept_does_not_block_the_real_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "PED",
            "fiscal_year": 2025,
            "receivables_net_current": 0.0,
            "accounts_receivable_net": 25_666_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["accounts_receivable"] == 25_666_000.0

    def test_dnli_style_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "DNLI",
            "fiscal_year": 2025,
            "accounts_and_other_receivables_net_current": 2_177_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["accounts_receivable"] == 2_177_000.0
