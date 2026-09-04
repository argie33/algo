"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, follow-up to the AGNC/ARR repo-agreement debt fix in 08c8c7f43): some commercial
mortgage REITs tag their real repo financing under a DIFFERENT standard us-gaap concept,
"SecuredDebtRepurchaseAgreements", not the "SecuritiesSoldUnderAgreementsToRepurchase"
concept AGNC/ARR use.

Live-confirmed via real SEC companyconcept API data: Seven Hills Realty Trust (SEVN, CIK
0001452477) $417,796,000 FY2024 / $487,657,000 FY2025 - previously NULL for every debt-
component column. SEVN's companyfacts has no "SecuritiesSoldUnderAgreementsToRepurchase"
fact at all, so no overwrite-collision risk between the two concepts. Same short-duration
rolling-financing semantics as the AGNC/ARR concept, so this also targets short_term_debt.
Fallback-only since a filer reporting a more specific standard debt concept must always
keep that value.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestSevnSecuredDebtRepurchaseAgreementsFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "short_term_debt": "short_term_debt",
            "commercial_paper": "short_term_debt",
            "secured_debt_repurchase_agreements": "short_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"secured_debt_repurchase_agreements"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_secured_debt_repurchase_agreements_to_short_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["secured_debt_repurchase_agreements"] == "short_term_debt"
        assert "secured_debt_repurchase_agreements" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_sevn_style_repo_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SEVN",
            "fiscal_year": 2025,
            "secured_debt_repurchase_agreements": 487_657_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 487_657_000.0

    def test_never_overwrites_a_real_short_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "commercial_paper": 7_980_000_000.0,
            "secured_debt_repurchase_agreements": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 7_980_000_000.0
