"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep,
our_value=0-vs-real-yfinance-value audit): CMCT (Creative Media & Community Trust, a REIT)
tags its real preferred distributions under the standard us-gaap concept
"PaymentsOfDividendsPreferredStockAndPreferenceStock" (previously never fetched at all) -
$21,959,000 FY2025, exactly matching the yfinance-flagged value - with no
DividendsCommonStock*/PaymentsOfDividends* common-dividend concept tagged that year (its own
"PaymentsOfDividendsCommonStock" fact is a real $0 - CMCT paid no common dividend, only
preferred).

Adding the concept alone was not enough: it resolves dividends_paid correctly as a
fallback-only concept (processed first, since row is empty), but "PaymentsOfDividendsCommon
Stock" - a PLAIN, non-fallback concept processed later in sec_cash_flow.py's concept list -
then unconditionally overwrote it with its own real $0 common-dividend fact via ordinary
last-processed-wins (fallback-only status only protects the FIRST writer, not against a later
PLAIN concept). Common and preferred dividends are additive, not alternatives, and this
loader has no per-field summing mechanism, so `transform()` now blocks a $0 write from
clobbering an already-resolved nonzero value for the affected aggregate fields
(long_term_debt/short_term_debt/capex/dividends_paid), regardless of fallback_only status.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING, _SBC_BUYBACK_FALLBACK_ONLY_FIELDS


class TestCmctPreferredDividendConceptFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "dividends_paid", "data_unavailable", "reason"})
        loader._field_mapping = {
            "dividends_paid": "dividends_paid",
            "payments_of_dividends_preferred_stock_and_preference_stock": "dividends_paid",
            "payments_of_dividends_common_stock": "dividends_paid",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"payments_of_dividends_preferred_stock_and_preference_stock"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_fallback_only(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["payments_of_dividends_preferred_stock_and_preference_stock"] == "dividends_paid"
        assert "payments_of_dividends_preferred_stock_and_preference_stock" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_zero_common_dividend_never_overwrites_the_real_preferred_total(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "CMCT",
            "fiscal_year": 2025,
            "payments_of_dividends_preferred_stock_and_preference_stock": 21_959_000.0,
            "payments_of_dividends_common_stock": 0.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["dividends_paid"] == 21_959_000.0

    def test_nonzero_common_dividend_still_overwrites_as_normal(self) -> None:
        """A genuinely nonzero, more-complete common-dividend concept must still win - this
        fix only blocks a literal $0 from clobbering an already-resolved nonzero value.
        """
        loader = self._make_loader()
        row = {
            "symbol": "TEST",
            "fiscal_year": 2025,
            "payments_of_dividends_preferred_stock_and_preference_stock": 5_000_000.0,
            "payments_of_dividends_common_stock": 100_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["dividends_paid"] == 100_000_000.0
