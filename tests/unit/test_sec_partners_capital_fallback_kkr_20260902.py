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
"StockholdersEquity") is the parent-only figure and the "...IncludingPortion..." variant
(total consolidated capital including third-party LP capital in KKR's consolidated managed
funds - live-confirmed ~10x larger than the parent-only figure some years) is fallback-only
and only fills years where the parent-only concept is absent entirely.

FIXED 2026-09-16 (CHKP live-confirmed via real SEC companyfacts JSON): "partners_capital"
deliberately stays OUT of the generic fallback-only set (it must still unconditionally win
over its own "...IncludingPortion..." sibling, the KKR case above - a blanket fallback-only
membership breaks that precedence whenever the sibling happens to be processed first). CHKP,
a real corporation, falsified the assumption this family was built on ("a filer tags either
StockholdersEquity or PartnersCapital, never both meaningfully"): its FY2025 20-F tags a
genuine StockholdersEquity ($2,882,100,000) AND, in the same filing, an unrelated $34,800,000
"PartnersCapital" fact (almost certainly a minor joint-venture interest, not CHKP's own
equity) - the unconditional mapping let it clobber the real value regardless of field order.
Fixed with a narrower, targeted guard in sec_base.py's transform() (not the fallback-only
set): "partners_capital" is skipped specifically when the SAME raw row also carries a real
StockholdersEquity-family concept, checked against the raw SEC field dict directly so it's
independent of processing order.
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

    def test_unrelated_partners_capital_does_not_clobber_real_stockholders_equity(self) -> None:
        """FIXED 2026-09-16, CHKP live-confirmed: a real corporation (never an LP) can also
        tag an unrelated, much smaller "PartnersCapital" fact (e.g. a minor joint-venture
        interest) in the same filing - this must never overwrite the filer's own real,
        already-populated StockholdersEquity value, however field iteration order lands."""
        loader = self._make_loader()
        row = {
            "symbol": "CHKP",
            "fiscal_year": 2025,
            "stockholders_equity": 2_882_100_000.0,
            "partners_capital": 34_800_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 2_882_100_000.0
