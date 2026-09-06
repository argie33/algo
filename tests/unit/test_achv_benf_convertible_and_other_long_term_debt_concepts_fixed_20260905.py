"""Regression test for the 2026-09-05 fix (goal session: "missing SEC/XBRL data" continuation,
total_debt_not_itemized investigation): ACHV (Achieve Life Sciences) and BENF (Beneficient) -
both real, active filers with real interest expense on file but zero long_term_debt/
short_term_debt ever - tag their real debt under concepts this loader previously never fetched.

Live-confirmed via real SEC companyfacts JSON:
- ACHV tags real convertible-note debt under the BARE "ConvertibleDebt" concept (a different
  XBRL element from the already-fetched "ConvertibleNotesPayable"/
  "ConvertibleLongTermNotesPayable") - $16.66M FY2023 (single figure), then splits into
  "ConvertibleDebtCurrent"/"ConvertibleDebtNoncurrent" starting FY2024 ($8.80M/$9.84M FY2024,
  $3.70M/$11.19M FY2025).
- BENF tags a separate, larger real long-term debt instrument under "OtherLongTermDebt" -
  $117.9M FY2025/$96.8M FY2026, not tagged under any other debt concept for this filer.
- SCM (Stellus Capital, a BDC) tags a real secured term-debt tranche under "SecuredLongTermDebt"
  - $299M FY2025/$325M FY2024 - a different, much larger real instrument than its own
  "NotesPayable" tag ($122.67M FY2025, its revolving credit facility), both genuinely
  outstanding simultaneously. Single-symbol-verified (not found on GAIN/MAIN/CSWC/NMFC/BCSF/
  ICMB/RWAY/SAR/NCDL, the other BDCs checked the same session).
- KBDC (Kayne Anderson BDC) has a real, current annual_balance_sheet row every fiscal year
  (2022-2025, data_unavailable=FALSE) but long_term_debt was NULL - it only tags
  "LineOfCreditFacilityFairValueOfAmountOutstanding" (a fair-value disclosure, not a
  carrying-value concept), never any standard debt concept. Cross-validated via magnitude:
  FY2025 total_assets - stockholders_equity implies ~$1.177B total liabilities; this
  concept's FY2025 value is $1.130B, a 96% match. KBDC also tags a much smaller "LineOfCredit"
  fact ($135M FY2025) - the new concept is listed BEFORE "LineOfCredit" in the fetch order so
  it wins this loader's "first-populated-wins" fallback precedence (KBDC-specific reordering;
  verified DGICA, the only other "LineOfCredit"-only filer checked, is unaffected).

All fallback-only (utils/external/sec_balance_sheet.py's get_balance_sheet() comment has the
full live evidence) - must never win over a real value the standard debt concepts already found.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestAchvBenfConvertibleAndOtherLongTermDebtConceptsFixed:
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
            "convertible_debt": "long_term_debt",
            "convertible_debt_current": "short_term_debt",
            "convertible_debt_noncurrent": "long_term_debt",
            "other_long_term_debt": "long_term_debt",
            "secured_long_term_debt": "long_term_debt",
            "line_of_credit_facility_fair_value_of_amount_outstanding": "long_term_debt",
            "line_of_credit": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset(
            {
                "convertible_debt",
                "convertible_debt_current",
                "convertible_debt_noncurrent",
                "other_long_term_debt",
                "secured_long_term_debt",
                "line_of_credit_facility_fair_value_of_amount_outstanding",
                "line_of_credit",
            }
        )
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_new_concepts(self) -> None:
        assert _BALANCE_FIELD_MAPPING["convertible_debt"] == "long_term_debt"
        assert _BALANCE_FIELD_MAPPING["convertible_debt_current"] == "short_term_debt"
        assert _BALANCE_FIELD_MAPPING["convertible_debt_noncurrent"] == "long_term_debt"
        assert _BALANCE_FIELD_MAPPING["other_long_term_debt"] == "long_term_debt"
        assert _BALANCE_FIELD_MAPPING["secured_long_term_debt"] == "long_term_debt"
        assert _BALANCE_FIELD_MAPPING["line_of_credit_facility_fair_value_of_amount_outstanding"] == "long_term_debt"
        for field in (
            "convertible_debt",
            "convertible_debt_current",
            "convertible_debt_noncurrent",
            "other_long_term_debt",
            "secured_long_term_debt",
            "line_of_credit_facility_fair_value_of_amount_outstanding",
        ):
            assert field in _DEBT_FALLBACK_ONLY_FIELDS

    def test_achv_style_bare_convertible_debt_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "ACHV", "fiscal_year": 2023, "convertible_debt": 16_662_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 16_662_000.0

    def test_achv_style_split_convertible_debt_recovered(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "ACHV",
            "fiscal_year": 2025,
            "convertible_debt_current": 3_704_000.0,
            "convertible_debt_noncurrent": 11_185_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 3_704_000.0
        assert transformed[0]["long_term_debt"] == 11_185_000.0

    def test_benf_style_other_long_term_debt_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "BENF", "fiscal_year": 2026, "other_long_term_debt": 96_785_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 96_785_000.0

    def test_scm_style_secured_long_term_debt_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "SCM", "fiscal_year": 2025, "secured_long_term_debt": 299_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 299_000_000.0

    def test_kbdc_style_fair_value_credit_facility_recovered(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "KBDC",
            "fiscal_year": 2025,
            "line_of_credit_facility_fair_value_of_amount_outstanding": 1_130_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 1_130_000_000.0

    def test_kbdc_style_fair_value_wins_over_smaller_line_of_credit_fact(self) -> None:
        """KBDC tags BOTH concepts for the same fiscal year - the far more complete
        fair-value figure ($1.13B, 96% cross-validated against implied total liabilities)
        must win over the much smaller line_of_credit fact ($135M), per this loader's
        first-populated-wins fallback precedence and the concept ordering in
        sec_balance_sheet.py (fair-value concept listed before "LineOfCredit")."""
        loader = self._make_loader()
        row = {
            "symbol": "KBDC",
            "fiscal_year": 2025,
            "line_of_credit_facility_fair_value_of_amount_outstanding": 1_130_000_000.0,
            "line_of_credit": 135_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 1_130_000_000.0

    def test_dgica_style_line_of_credit_only_unaffected_by_kbdc_reordering(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "DGICA", "fiscal_year": 2025, "line_of_credit": 35_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 35_000_000.0

    def test_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMECORP",
            "fiscal_year": 2025,
            "long_term_debt": 500_000_000.0,
            "convertible_debt": 1.0,
            "other_long_term_debt": 2.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 500_000_000.0
