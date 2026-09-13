"""Regression test for the 2026-09-13 fix (goal session: MKZR revenue investigation) to the
REIT-only-fallback magnitude check in sec_base.py's transform loop.

That check (see the "WIDENED 2026-09-01" comment above it) only blocked the REIT-fallback
concept from overwriting "revenue" when the existing value was already >= the candidate -
built for CLDT (Chatham Lodging Trust), where "bigger" reliably meant "the real, more-complete
total". Live-confirmed false via MacKenzie Realty Capital (MKZR, SIC 6798): several
OperatingLeaseLeaseIncome facts are themselves a filer-side 1,000,000x decimals-tag error -
e.g. FY2026 Q3 has revenue_from_contract_with_customer_excluding_assessed_tax=$5,441,504
(correct, populates "revenue" first), then the REIT-fallback OperatingLeaseLeaseIncome candidate
reports $5,441,504,000,000 for the IDENTICAL period. "Bigger" there means corrupted, not more
complete. `_is_power_of_ten_scale_outlier` (already trusted for the IPAR/PMT/UPC frame-
preference cases) now also recognizes a clean 1,000,000x ratio and blocks the overwrite,
without touching the CLDT case (295,871,000 vs 51,000 is not a clean power-of-ten ratio, so
that overwrite still proceeds).
"""

from decimal import Decimal

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestMkzrReitLeaseIncomePowerOfTenScaleOutlier:
    def _make_loader(self, reit_symbols: frozenset[str]):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
            "operating_lease_lease_income": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        # Matches the real production config (financial_statements_income_config.py):
        # operating_lease_lease_income is reit_exclusive (fallback-only for REITs, never
        # magnitude-gated), the ASC-606 concepts are reit_only_fallback (magnitude-gated).
        loader._reit_only_fallback_fields = frozenset({"revenue_from_contract_with_customer_excluding_assessed_tax"})
        loader._reit_exclusive_fields = frozenset({"operating_lease_lease_income"})
        loader._reit_symbols = reit_symbols
        loader._insurance_symbols = frozenset()
        return loader

    def test_million_x_scale_outlier_lease_income_does_not_clobber_real_revenue(self) -> None:
        # operating_lease_lease_income is reit_exclusive, so it's processed BEFORE the
        # reit_only_fallback ASC-606 concept regardless of dict order (see the
        # "_reit_only_fallback" stable-sort in sec_base.py) - it lands in "revenue" first
        # with the corrupted 1,000,000x value, and the correct ASC-606 value must then be
        # allowed to replace it.
        loader = self._make_loader(reit_symbols=frozenset({"MKZR"}))
        row = {
            "symbol": "MKZR",
            "fiscal_year": 2026,
            "revenue_from_contract_with_customer_excluding_assessed_tax": Decimal("5441504"),
            "operating_lease_lease_income": Decimal("5441504000000"),
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == Decimal("5441504")

    def test_cldt_style_real_larger_total_still_recovers_revenue(self) -> None:
        # Not a clean power-of-ten ratio (295,871,000 / 51,000 ~= 5,801x) - the real,
        # more-complete ASC-606 total must still win, same as before this fix. CLDT reports
        # no lease-income concept at all; the existing (smaller) value here is the unrelated
        # investment-income fact that happened to be inserted first (see
        # test_sec_reit_lease_revenue_not_overwritten.py / the "WIDENED 2026-09-01" comment
        # in sec_base.py for the live-confirmed CLDT case this guards).
        loader = self._make_loader(reit_symbols=frozenset({"CLDT"}))
        loader._field_mapping["investment_income_interest_and_dividend"] = "revenue"
        row = {
            "symbol": "CLDT",
            "fiscal_year": 2016,
            "investment_income_interest_and_dividend": 51_000.0,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 295_871_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 295_871_000.0

    def test_wafdp_style_bank_interest_income_still_protected(self) -> None:
        # ~23x, not a clean power-of-ten ratio - the real interest-income-derived total
        # must still be protected from the minor ASC-606 fee-income line, same as before
        # this fix (see test_sec_bank_interest_income_revenue_not_overwritten.py).
        loader = self._make_loader(reit_symbols=frozenset())
        loader._field_mapping["interest_and_dividend_income_operating"] = "revenue"
        loader._fallback_only_fields = frozenset({"interest_and_dividend_income_operating"})
        loader._depository_institution_symbols = frozenset({"WAFDP"})
        row = {
            "symbol": "WAFDP",
            "fiscal_year": 2019,
            "interest_and_dividend_income_operating": 671_500_000.0,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 24_900_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 671_500_000.0
