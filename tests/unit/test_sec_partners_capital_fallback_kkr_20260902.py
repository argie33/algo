"""Regression test for the limited-partnership stockholders_equity gap found live
2026-09-02 investigating KKR (a real filer): KKR & Co. L.P. was structured as a limited
partnership until its 2018 conversion to a corporation, so its FY2009-2017 10-Ks tag
total partner capital under "PartnersCapital"/"PartnersCapitalIncludingPortionAttributable
ToNoncontrollingInterest" instead of any "StockholdersEquity" concept -
annual_balance_sheet.stockholders_equity was NULL for every one of those years despite
total_assets/current_liabilities/etc. all being populated, since neither concept had a
database column mapping.

Fixed by adding both concepts to sec_statements.py's get_balance_sheet() concept list and
mapping them to the "stockholders_equity" column, mirroring the existing
StockholdersEquity/StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest
precedence: "partners_capital" (parent-only, the direct partnership analogue of plain
"StockholdersEquity") is NOT fallback-only and always wins; the "...IncludingPortion..."
variant (total consolidated capital including third-party LP capital in KKR's consolidated
managed funds - live-confirmed ~10x larger than the parent-only figure some years) is
fallback-only and only fills years where the parent-only concept is absent entirely.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestPartnersCapitalFallbackForLimitedPartnershipFilers:
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

    def test_partnership_filer_parent_only_capital_recovered(self) -> None:
        # KKR-shaped FY2014 data: no StockholdersEquity concept at all, only the
        # partnership pair. The parent-only "partners_capital" figure must win over the
        # much larger consolidated-fund "...IncludingPortion..." figure.
        loader = self._make_loader()
        row = {
            "symbol": "KKR",
            "fiscal_year": 2014,
            "partners_capital_including_portion_attributable_to_noncontrolling_interest": 51_403_963_000.0,
            "partners_capital": 5_382_691_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 5_382_691_000.0

    def test_partnership_fallback_only_fills_when_parent_only_concept_absent(self) -> None:
        # A partnership filer that only ever tags the consolidated figure (no separate
        # parent-only concept some year) must still get a value, not NULL.
        loader = self._make_loader()
        row = {
            "symbol": "KKR",
            "fiscal_year": 2009,
            "partners_capital_including_portion_attributable_to_noncontrolling_interest": 40_942_890_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 40_942_890_000.0

    def test_corporation_filer_stockholders_equity_unaffected(self) -> None:
        # Sanity check: an ordinary corporation filer with a real StockholdersEquity
        # concept must be completely unaffected by the new partnership fallback fields.
        loader = self._make_loader()
        row = {
            "symbol": "WEC",
            "fiscal_year": 2019,
            "stockholders_equity": 10_186_400_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 10_186_400_000.0
