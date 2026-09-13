"""Regression test for a 2026-09-13 fix (goal session: quarterly-revenue-identity backlog)
to loaders/helpers/sec_base.py's transform() - the `_reit_exclusive_fields` branch had no
scale-sanity check at all.

Live-confirmed via MKZR (a real-estate/property-management filer, CIK 0001550913): its real
FY2025 Q2 10-Q genuinely tags us-gaap:OperatingLeaseLeaseIncome at exactly 1,000,000x its own
correctly-scaled RevenueFromContractWithCustomerExcludingAssessedTax value for the identical
period ($8,030,316,000,000 vs $8,030,316) - a filer-side XBRL scale-tagging error present
verbatim in SEC's own companyfacts JSON, not an extraction-side bug (same bug CLASS as the
TYGO case _reject_scale_mismatched_revenue already guards against in the general priority
chain, just via a different concept and a 1,000,000x rather than 1,000x multiple).

Because OperatingLeaseLeaseIncome is REIT-exclusive and processed BEFORE its ASC-606 sibling
(sorted to the end of `ordered_fields` as a `_reit_only_fallback_fields` member), the garbage
value won "revenue" first - then the REIT-fallback magnitude guard (which protects "existing
value already larger" on the assumption a bigger number is a more complete total) backwards
protected the 1,000,000x-inflated garbage from ever being corrected by the real, smaller,
correct ASC-606 value.

Fix: before letting a `_reit_exclusive_fields` concept write "revenue", check it against any
other same-row raw concept that also targets "revenue" - a clean power-of-10 (100x-1,000,000x)
mismatch is rejected as a scale-tagging error rather than stored.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestReitExclusiveFieldScaleMismatchGuard:
    def _make_loader(self, reit_symbols: frozenset[str]) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "operating_lease_lease_income": "revenue",
            "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset({"revenue_from_contract_with_customer_excluding_assessed_tax"})
        loader._reit_exclusive_fields = frozenset({"operating_lease_lease_income"})
        loader._reit_symbols = reit_symbols
        return loader

    def test_mkzr_shaped_million_x_scale_error_rejected_not_stored(self) -> None:
        loader = self._make_loader(reit_symbols=frozenset({"MKZR"}))
        row = {
            "symbol": "MKZR",
            "fiscal_year": 2024,
            "operating_lease_lease_income": 8_030_316_000_000.0,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 8_030_316.0,
        }

        transformed = loader.transform([row])

        # The correct, smaller ASC-606 value must win - the 1,000,000x-inflated lease-income
        # figure must never reach "revenue" at all.
        assert transformed[0]["revenue"] == 8_030_316.0

    def test_genuine_lease_income_recovery_still_works_without_a_scale_mismatch(self) -> None:
        """Guard against over-fixing: AMH-style genuine lease-income recovery (no sibling
        concept present at all, or a sibling that isn't a clean power-of-10 multiple) must be
        completely unaffected."""
        loader = self._make_loader(reit_symbols=frozenset({"AMH"}))
        row = {
            "symbol": "AMH",
            "fiscal_year": 2025,
            "operating_lease_lease_income": 1_850_234_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_850_234_000.0

    def test_real_close_values_not_falsely_flagged_as_scale_mismatch(self) -> None:
        """Two genuinely close (non-power-of-10) values on the same row must not trip the
        guard - only a clean 100x-1,000,000x ratio counts as a scale-tagging signature."""
        loader = self._make_loader(reit_symbols=frozenset({"CPT"}))
        row = {
            "symbol": "CPT",
            "fiscal_year": 2025,
            "operating_lease_lease_income": 1_574_000_000.0,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 12_967_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_574_000_000.0
