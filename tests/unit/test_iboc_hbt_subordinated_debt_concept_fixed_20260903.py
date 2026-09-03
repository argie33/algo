"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, total_debt_not_itemized investigation): small/mid-cap bank and thrift holding
companies carry no conventional LongTermDebt/NotesPayable/SeniorNotes at all - their only
real debt instruments are trust-preferred securities, tagged under concepts never in our
concept list.

Live-confirmed via real SEC companyfacts JSON: IBOC (International Bancshares, CIK 315709)
real $108,868,000 "JuniorSubordinatedDebentureOwedToUnconsolidatedSubsidiaryTrust" balance,
continuous through FY2025-2026, no LongTermDebt/NotesPayable/SeniorNotes concept present at
all. HBT (HBT Financial, CIK 775215) real $84,003,000-$84,026,000 "SubordinatedDebt" (new
2026 issuance) plus a separate, real $52,894,000-$52,939,000
"JuniorSubordinatedDebentureOwedToUnconsolidatedSubsidiaryTrust" balance - two genuinely
distinct instruments, both fallback-only, first-populated-wins (accepted as strictly better
than the prior "not itemized" NULL, same single-figure-not-perfect-sum convention as the
NotesPayable/SeniorNotes fallbacks).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestIbocHbtSubordinatedDebtConceptFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "subordinated_debt": "long_term_debt",
            "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset(
            {"subordinated_debt", "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust"}
        )
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_both_concepts_to_long_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["subordinated_debt"] == "long_term_debt"
        assert (
            _BALANCE_FIELD_MAPPING["junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust"]
            == "long_term_debt"
        )
        assert "subordinated_debt" in _DEBT_FALLBACK_ONLY_FIELDS
        assert "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_iboc_style_trust_preferred_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "IBOC",
            "fiscal_year": 2025,
            "junior_subordinated_debenture_owed_to_unconsolidated_subsidiary_trust": 108_868_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 108_868_000.0

    def test_subordinated_debt_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "JPM",
            "fiscal_year": 2025,
            "long_term_debt": 435_200_000_000.0,
            "subordinated_debt": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 435_200_000_000.0
