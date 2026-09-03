"""Regression test for the LLC-structured-filer stockholders_equity gap found live
2026-09-03 investigating the "no_recent_balance_sheet_data_reported" coverage bucket:
domestic (not foreign-private-issuer) LLC filers tag total member capital under
"MembersEquity" instead of any "StockholdersEquity"/"PartnersCapital" concept -
annual_balance_sheet.stockholders_equity was NULL for every one of their fiscal years
despite real, current XBRL data existing, since the concept had no database column
mapping. Live-confirmed via real SEC companyfacts JSON: APGE (Apogee Therapeutics) FY2025
$903,883,000 + current Q2 2026 10-Q $1,194,604,000, ARXS (Arxis) current Q2 2026 10-Q
$3,183,274,000, ITG (ITG, Inc./DE/) current Q2 2026 10-Q $34,376,000 - all real, current,
USD-denominated instant facts, zero StockholdersEquity/PartnersCapital facts of any kind
for any of the three.

Fixed by adding "MembersEquity" to sec_statements.py's get_balance_sheet() concept list
and mapping it to the "stockholders_equity" column in load_financial_statements.py's
_BALANCE_FIELD_MAPPING, mirroring the existing "partners_capital" precedence: direct
legal-structure analogue, not fallback-only (an LLC never also tags StockholdersEquity/
PartnersCapital in practice).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestMembersEquityFallbackForLlcFilers:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "stockholders_equity", "data_unavailable", "reason"})
        loader._field_mapping = {
            "stockholders_equity": "stockholders_equity",
            "stockholders_equity_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity",
            "partners_capital": "stockholders_equity",
            "partners_capital_including_portion_attributable_to_noncontrolling_interest": "stockholders_equity",
            "members_equity": "stockholders_equity",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset(
            {
                "stockholders_equity_including_portion_attributable_to_noncontrolling_interest",
                "partners_capital_including_portion_attributable_to_noncontrolling_interest",
            }
        )
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_llc_filer_members_equity_recovered(self) -> None:
        # APGE-shaped data: no StockholdersEquity/PartnersCapital concept at all, only
        # MembersEquity.
        loader = self._make_loader()
        row = {
            "symbol": "APGE",
            "fiscal_year": 2025,
            "members_equity": 903_883_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 903_883_000.0

    def test_corporation_filer_stockholders_equity_unaffected(self) -> None:
        # Sanity check: an ordinary corporation filer with a real StockholdersEquity
        # concept must be completely unaffected by the new MembersEquity mapping.
        loader = self._make_loader()
        row = {
            "symbol": "WEC",
            "fiscal_year": 2019,
            "stockholders_equity": 10_186_400_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 10_186_400_000.0
